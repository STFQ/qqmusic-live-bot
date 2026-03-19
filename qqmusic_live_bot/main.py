from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from .config import load_runtime_config
from .core.collector import TextCollector
from .core.device import DeviceSession
from .core.parser import EventParser
from .core.scheduler import Scheduler
from .core.sender import MessageSender
from .core.state import BotState
from .services.logger import BotLogger
from .services.storage import MemoryService
from .strategy.filters import load_blacklist, should_skip_text, trim_gift_reply, trim_reply


class LiveBotApp:
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parent
        self.config = load_runtime_config(self.root)
        self.logger = BotLogger(
            self.root / "data" / "logs",
            console_output=bool(self.config.logging["console_output"]),
        )
        self.memory = MemoryService(self.root / "data" / "memory.json")
        self.blacklist = load_blacklist(self.root / "data" / "blacklist.json")
        self.collector = TextCollector(
            line_ttl=float(self.config.limits["collector_line_ttl"]),
            ocr_interval=float(self.config.limits["ocr_interval"]),
            ocr_trigger_line_count=int(self.config.limits["ocr_trigger_line_count"]),
            enable_ocr_fallback=bool(self.config.flags["enable_ocr_fallback"]),
        )
        self.parser = EventParser()
        self.scheduler = Scheduler(self.config.flags)
        self.state = BotState(mode=self.config.mode)
        
        # [新增] 消息队列：用于主抓取线程和发送线程之间传递要发送的弹幕
        self.action_queue = queue.Queue()
        self.is_running = False

    def _sender_thread_worker(self, sender: MessageSender) -> None:
        """[新增] 独立的发送线程：基于 ACK 回执驱动的高并发消费者"""
        self.logger.info("后台发送线程已启动，待命完毕！")
        while self.is_running:
            try:
                # 1. 从队列获取任务
                # 这里做了一个兼容：如果你用的是普通 Queue，就是 action, text
                # 如果你按我之前说的升了级，换成了 PriorityQueue，那就是 priority, enqueue_time, action, text
                task = self.action_queue.get(timeout=1.0)

                if len(task) == 4:
                    priority, enqueue_time, action, text = task
                    # 【VIP 队列专属：超时丢弃机制】
                    # 如果是优先级最低的欢迎/聊天（priority >= 3），并且在队列里堵了超过 5 秒，直接扔掉！
                    if priority >= 3 and (time.time() - enqueue_time > 5.0):
                        self.logger.info(f"消息已过期积压，触发自动丢弃: {text}")
                        self.action_queue.task_done()
                        continue
                else:
                    action, text = task

            except queue.Empty:
                continue

            try:
                # 2. 【核心执行】调用带 ACK 回执锁的发送模块
                # 注意：这里的 sender.send_message 现在是“智能阻塞”的。
                # 它不依赖时间，而是眼睁睁看着输入框消失了，才会返回 True！
                success = sender.send_message(text)

                if success:
                    # ==========================================
                    # 下面这些是极其宝贵的业务状态更新，必须原封不动保留！
                    # ==========================================
                    now_ts = time.time()
                    self.state.mark_sent(action.event_type, now_ts)
                    dedupe_key = action.raw or f"{action.event_type}:{action.user}:{text}"
                    self.state.sent_fingerprints[dedupe_key] = now_ts

                    if action.user:
                        self.memory.touch_user(action.user, action.event_type, action.raw or text)

                    self.logger.info(f"发送成功 [{action.reason}] -> {text}")

                    # 🚀【极致提速的核心改动】
                    # 以前这里有一个 time.sleep(post_send_cooldown)，我们现在【彻底把它删掉】！
                    # 因为 Sender 那边的 ACK 回执确认只要一拿到，就意味着 UI 已经完全准备好接收下一条了。
                    # 0 毫秒等待，光速放行！

                else:
                    self.logger.info(f"发送失败 [{action.reason}] -> {text}")
                    # 失败时给个极短的缓冲，防止在 UI 真出 Bug 卡死的时候，瞬间爆刷异常日志
                    time.sleep(0.3)

            except Exception as e:
                self.logger.info(f"发送动作异常: {e}")
                time.sleep(0.3)

            finally:
                self.action_queue.task_done()

    def run(self) -> None:
        device = DeviceSession(self.config.device_addr).connect()
        sender = MessageSender(
            device=device,
            input_x=self.config.input_box_x,
            input_y=self.config.input_box_y,
            logger=self.logger,
            dry_run=self.config.dry_run,
            log_dry_run=bool(self.config.logging["dry_run"]),
        )
        self.logger.info(
            f"稳定版 V1 已启动(双线程极速版) | mode={self.state.mode} | dry_run={self.config.dry_run} | device={self.config.device_addr}"
        )

        # 启动后台发送线程
        self.is_running = True
        sender_thread = threading.Thread(target=self._sender_thread_worker, args=(sender,), daemon=True)
        sender_thread.start()

        while self.is_running:
            try:
                # 主线程全速抓取屏幕，绝不停歇
                frame = self.collector.collect(device)
                self.state.cleanup(frame.ts, ttl=float(self.config.limits["dedupe_ttl"]))
                frame.lines = [line for line in frame.lines if not should_skip_text(line, self.blacklist)]
                
                if not frame.lines:
                    time.sleep(float(self.config.limits["main_loop_interval"]))
                    continue

                events = self.parser.parse(frame)
                for event in events:
                    if event.fingerprint in self.state.seen_event_fingerprints:
                        continue
                    self.state.seen_event_fingerprints[event.fingerprint] = frame.ts
                    if event.type.value == "pk_timer" and self.config.logging["pk_time"]:
                        self.logger.info(f"[PK_TIME] seconds={event.meta.get('seconds', event.content)} raw={event.raw}")
                    self.logger.event(
                        {
                            "ts": frame.ts,
                            "type": event.type.value,
                            "user": event.user,
                            "content": event.content,
                            "count": event.count,
                            "raw": event.raw,
                        }
                    )

                action = self.scheduler.next_action(frame, events, self.state)
                if not action:
                    time.sleep(float(self.config.limits["main_loop_interval"]))
                    continue

                max_reply_len = int(self.config.profile["max_reply_len"])
                if action.event_type == "gift":
                    text = trim_gift_reply(action.user, str(action.meta.get("gift", "")), max_reply_len)
                else:
                    text = trim_reply(action.text, max_reply_len)

                # [核心逻辑] 不再直接调用发送，而是推入队列
                self.logger.info(f"准备发送(加入队列) [{action.reason}] -> {text}")
                
                # 乐观预先标记（假装已经发了）：防止由于队列拥挤、发送线程还没发出去期间，
                # 主线程又抓到了同样的事件，导致重复加入队列
                now_ts = time.time()
                self.state.mark_sent(action.event_type, now_ts)
                dedupe_key = action.raw or f"{action.event_type}:{action.user}:{text}"
                self.state.sent_fingerprints[dedupe_key] = now_ts
                
                # 推入队列，主循环立刻进行下一次抓取
                self.action_queue.put((action, text))

            except KeyboardInterrupt:
                self.logger.info("已手动停止，正在关闭...")
                self.is_running = False
                break
            except Exception as exc:
                self.logger.info(f"主循环异常: {exc}")
                time.sleep(2)


def main() -> None:
    LiveBotApp().run()


if __name__ == "__main__":
    main()