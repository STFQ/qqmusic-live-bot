from __future__ import annotations

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
            f"稳定版 V1 已启动 | mode={self.state.mode} | dry_run={self.config.dry_run} | device={self.config.device_addr} | ocr={self.config.flags['enable_ocr_fallback']}"
        )

        while True:
            try:
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
                success = sender.send_message(text)
                if success:
                    now_ts = time.time()
                    self.state.mark_sent(action.event_type, now_ts)
                    dedupe_key = action.raw or f"{action.event_type}:{action.user}:{text}"
                    self.state.sent_fingerprints[dedupe_key] = now_ts
                    if action.user:
                        self.memory.touch_user(action.user, action.event_type, action.raw or text)
                    self.logger.info(f"发送成功 [{action.reason}] -> {text}")
                    time.sleep(float(self.config.limits["post_send_cooldown"]))
                else:
                    self.logger.info(f"发送失败 [{action.reason}] -> {text}")
                    time.sleep(1.5)
            except KeyboardInterrupt:
                self.logger.info("已手动停止")
                break
            except Exception as exc:
                self.logger.info(f"主循环异常: {exc}")
                time.sleep(2)


def main() -> None:
    LiveBotApp().run()


if __name__ == "__main__":
    main()
