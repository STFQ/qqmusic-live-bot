from __future__ import annotations

import queue
import sys
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
from .strategy.filters import trim_gift_reply, trim_reply


class LiveBotApp:
    def __init__(self) -> None:
        if getattr(sys, 'frozen', False):
            self.root = Path(sys.executable).parent / "qqmusic_live_bot"
        else:
            self.root = Path(__file__).resolve().parent

        self.config = load_runtime_config(self.root)

        self.logger = BotLogger(
            self.root / "data" / "logs",
            console_output=bool(self.config.logging.get("console_output", True)),
            file_output=bool(self.config.logging.get("file_output", False)),
        )

        self.collector = TextCollector(
            line_ttl=float(self.config.limits["collector_line_ttl"]),
            y_tolerance=float(self.config.limits["collector_y_tolerance"]),
        )
        self.parser = EventParser()
        self.scheduler = Scheduler(self.config.flags, self.config.limits)
        self.state = BotState(mode=self.config.mode)

        self.action_queue = queue.Queue(maxsize=int(self.config.limits["queue_maxsize"]))
        self.is_running = False
        self._last_queue_warn_ts = 0.0

    def _action_priority(self, event_type: str) -> int:
        if event_type == "gift": return 1
        if event_type == "pk_timer": return 2
        if event_type == "welcome": return 3
        if event_type == "chat": return 4
        return 5

    def _dedupe_key(self, action, text: str) -> str:
        return action.raw or f"{action.event_type}:{action.user}:{text}"

    def _enqueue_action(self, action, text: str, now_ts: float, retry_count: int = 0) -> bool:
        dedupe_key = self._dedupe_key(action, text)
        if self.state.is_recently_handled(dedupe_key): return False

        priority = self._action_priority(action.event_type)
        task = {
            "priority": priority, "enqueue_time": now_ts, "action": action,
            "text": text, "dedupe_key": dedupe_key, "retry_count": retry_count,
        }
        try:
            self.action_queue.put_nowait(task)
        except queue.Full:
            return False

        self.state.mark_queued(dedupe_key, now_ts)
        self.logger.info(f"加入队列 [{action.reason}] -> {text}")
        return True

    def _sender_thread_worker(self, sender: MessageSender) -> None:
        while self.is_running or not self.action_queue.empty():
            try:
                task = self.action_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            action, text, dedupe_key = task["action"], task["text"], task["dedupe_key"]
            try:
                success = sender.send_message(text)
                if success:
                    self.state.mark_sent(action.event_type, time.time(), dedupe_key)
                    self.logger.info(f"发送成功: {text}")
                else:
                    self.state.unmark_queued(dedupe_key)
            except Exception as e:
                self.state.unmark_queued(dedupe_key)
                self.logger.info(f"发送异常: {e}")
            finally:
                self.action_queue.task_done()

    def run(self) -> None:
        device = DeviceSession(self.config.device_addr).connect()
        sender = MessageSender(
            device=device,
            input_x=self.config.input_box_x, input_y=self.config.input_box_y,
            logger=self.logger, dry_run=self.config.dry_run,
            log_dry_run=bool(self.config.logging["dry_run"]),
            send_x=1154.5, send_y=2540.3, fallback_send_x=1147.5, fallback_send_y=2697.5,
        )
        self.is_running = True
        threading.Thread(target=self._sender_thread_worker, args=(sender,), daemon=True).start()

        try:
            while self.is_running:
                frame = self.collector.collect(device)
                self.state.cleanup(frame.ts, ttl=float(self.config.limits["dedupe_ttl"]))
                events = self.parser.parse(frame)

                for event in events:
                    if event.fingerprint in self.state.seen_event_fingerprints: continue
                    self.state.seen_event_fingerprints[event.fingerprint] = frame.ts

                    action = self.scheduler.next_action(frame, [event], self.state)
                    if action:
                        max_len = int(self.config.profile["max_reply_len"])
                        text = trim_gift_reply(action.user, str(action.meta.get("gift", "")),
                                               max_len) if action.event_type == "gift" else trim_reply(action.text,
                                                                                                       max_len)
                        self._enqueue_action(action, text, time.time())
                time.sleep(float(self.config.limits["main_loop_interval"]))
        except KeyboardInterrupt:
            self.is_running = False
        finally:
            self.is_running = False


def main() -> None: LiveBotApp().run()


if __name__ == "__main__": main()