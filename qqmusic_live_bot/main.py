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
from .strategy.filters import trim_gift_reply, trim_reply


class LiveBotApp:
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parent
        self.config = load_runtime_config(self.root)
        self.logger = BotLogger(
            self.root / "data" / "logs",
            console_output=bool(self.config.logging["console_output"]),
        )
        self.memory = MemoryService(self.root / "data" / "memory.json")
        self.collector = TextCollector(
            line_ttl=float(self.config.limits["collector_line_ttl"]),
            y_tolerance=float(self.config.limits["collector_y_tolerance"]),
        )
        self.parser = EventParser()
        self.scheduler = Scheduler(self.config.flags, self.config.limits)
        self.state = BotState(mode=self.config.mode)

        # 消息队列：用于主抓取线程和发送线程之间传递要发送的弹幕
        self.action_queue = queue.Queue(maxsize=int(self.config.limits["queue_maxsize"]))
        self.is_running = False
        self._last_queue_warn_ts = 0.0

    def _action_priority(self, event_type: str) -> int:
        if event_type == "gift":
            return 1
        if event_type == "pk_timer":
            return 2
        if event_type == "welcome":
            return 3
        if event_type == "chat":
            return 4
        return 5

    def _dedupe_key(self, action, text: str) -> str:
        return action.raw or f"{action.event_type}:{action.user}:{text}"

    def _log_queue_pressure(self, now_ts: float) -> None:
        warn_size = int(self.config.limits["queue_warn_size"])
        if self.action_queue.qsize() < warn_size:
            return
        if now_ts - self._last_queue_warn_ts < 5.0:
            return
        self._last_queue_warn_ts = now_ts
        self.logger.info(f"发送队列积压告警: size={self.action_queue.qsize()} / {self.action_queue.maxsize}")

    def _enqueue_action(self, action, text: str, now_ts: float, retry_count: int = 0) -> bool:
        dedupe_key = self._dedupe_key(action, text)
        if self.state.is_recently_handled(dedupe_key):
            return False

        priority = self._action_priority(action.event_type)
        if self.action_queue.full() and priority >= 3:
            self.logger.info(f"队列已满，丢弃低优先级消息 [{action.reason}] -> {text}")
            return False

        task = {
            "priority": priority,
            "enqueue_time": now_ts,
            "action": action,
            "text": text,
            "dedupe_key": dedupe_key,
            "retry_count": retry_count,
        }
        try:
            self.action_queue.put_nowait(task)
        except queue.Full:
            self.logger.info(f"队列已满，入队失败 [{action.reason}] -> {text}")
            return False

        self.state.mark_queued(dedupe_key, now_ts)
        self._log_queue_pressure(now_ts)
        self.logger.info(
            f"准备发送(加入队列) [{action.reason}] priority={priority} retry={retry_count} size={self.action_queue.qsize()} -> {text}"
        )
        return True

    def _sender_thread_worker(self, sender: MessageSender) -> None:
        self.logger.info("后台发送线程已启动，待命完毕！")
        while self.is_running or not self.action_queue.empty():
            try:
                task = self.action_queue.get(timeout=1.0)

            except queue.Empty:
                continue

            action = task["action"]
            text = task["text"]
            priority = int(task["priority"])
            enqueue_time = float(task["enqueue_time"])
            dedupe_key = str(task["dedupe_key"])
            retry_count = int(task["retry_count"])

            try:
                if priority >= 3 and (time.time() - enqueue_time > float(self.config.limits["low_priority_ttl"])):
                    self.logger.info(f"消息已过期积压，触发自动丢弃 [{action.reason}] -> {text}")
                    self.state.unmark_queued(dedupe_key)
                    continue

                success = sender.send_message(text)

                if success:
                    now_ts = time.time()
                    self.state.mark_sent(action.event_type, now_ts, dedupe_key)

                    if action.user:
                        self.memory.touch_user(action.user, action.event_type, action.raw or text)

                    self.logger.info(f"发送成功 [{action.reason}] -> {text}")
                else:
                    retry_limit = int(self.config.limits["send_retry_limit"])
                    self.state.unmark_queued(dedupe_key)
                    if retry_count < retry_limit and self._enqueue_action(action, text, time.time(), retry_count + 1):
                        self.logger.info(f"发送失败，已重新入队 [{action.reason}] retry={retry_count + 1} -> {text}")
                    else:
                        self.logger.info(f"发送失败，已放弃 [{action.reason}] -> {text}")
                    time.sleep(0.3)

            except Exception as e:
                self.state.unmark_queued(dedupe_key)
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
            send_x=1154.5,
            send_y=2540.3,
            fallback_send_x=1147.5,
            fallback_send_y=2697.5,
        )
        self.logger.info(
            f"稳定版 V1 已启动(双线程极速版) | mode={self.state.mode} | dry_run={self.config.dry_run} | device={self.config.device_addr}"
        )

        # 启动后台发送线程
        self.is_running = True
        sender_thread = threading.Thread(target=self._sender_thread_worker, args=(sender,), daemon=True)
        sender_thread.start()

        try:
            while self.is_running:
                try:
                    frame = self.collector.collect(device)
                    for index, line in enumerate(frame.gift_lines):
                        self.logger.gift_lines(
                            {
                                "ts": frame.ts,
                                "type": "gift_region_text",
                                "index": index,
                                "text": line,
                            }
                        )
                    self.state.cleanup(frame.ts, ttl=float(self.config.limits["dedupe_ttl"]))

                    events = self.parser.parse(frame)
                    if not events:
                        time.sleep(float(self.config.limits["main_loop_interval"]))
                        continue
                    fresh_events = []
                    latest_pk_event = None
                    for event in events:
                        if event.type.value == "pk_timer":
                            latest_pk_event = event
                        if event.fingerprint in self.state.seen_event_fingerprints:
                            continue
                        self.state.seen_event_fingerprints[event.fingerprint] = frame.ts
                        fresh_events.append(event)
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

                    scheduler_events = list(fresh_events)
                    if latest_pk_event and all(event.type.value != "pk_timer" for event in scheduler_events):
                        scheduler_events.append(latest_pk_event)

                    action = self.scheduler.next_action(frame, scheduler_events, self.state)
                    if not action:
                        time.sleep(float(self.config.limits["main_loop_interval"]))
                        continue

                    max_reply_len = int(self.config.profile["max_reply_len"])
                    if action.event_type == "gift":
                        text = trim_gift_reply(action.user, str(action.meta.get("gift", "")), max_reply_len)
                    else:
                        text = trim_reply(action.text, max_reply_len)

                    self._enqueue_action(action, text, time.time())

                except KeyboardInterrupt:
                    self.logger.info("已手动停止，正在关闭...")
                    self.is_running = False
                    break
                except Exception as exc:
                    self.logger.info(f"主循环异常: {exc}")
                    time.sleep(2)
        finally:
            self.is_running = False
            sender_thread.join(timeout=3.0)
            self.memory.flush()


def main() -> None:
    LiveBotApp().run()


if __name__ == "__main__":
    main()
