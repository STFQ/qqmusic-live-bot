from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class BotState:
    mode: str = "auto"
    last_send_time: float = 0.0
    last_welcome_time: float = 0.0
    last_gift_time: float = 0.0
    last_chat_time: float = 0.0
    last_warmup_time: float = 0.0
    last_pk_time: float = 0.0
    room_heat: str = "normal"
    pk_active: bool = False
    queued_fingerprints: dict[str, float] = field(default_factory=dict)
    sent_fingerprints: dict[str, float] = field(default_factory=dict)
    seen_event_fingerprints: dict[str, float] = field(default_factory=dict)
    last_pk_seconds: int | None = None
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def cleanup(self, now_ts: float, ttl: float = 120.0) -> None:
        with self._lock:
            self.queued_fingerprints = {
                key: ts for key, ts in self.queued_fingerprints.items() if now_ts - ts < ttl
            }
            self.sent_fingerprints = {
                key: ts for key, ts in self.sent_fingerprints.items() if now_ts - ts < ttl
            }
            self.seen_event_fingerprints = {
                key: ts for key, ts in self.seen_event_fingerprints.items() if now_ts - ts < ttl
            }

    def mark_queued(self, fingerprint: str, now_ts: float) -> None:
        if not fingerprint:
            return
        with self._lock:
            self.queued_fingerprints[fingerprint] = now_ts

    def unmark_queued(self, fingerprint: str) -> None:
        if not fingerprint:
            return
        with self._lock:
            self.queued_fingerprints.pop(fingerprint, None)

    def is_recently_handled(self, fingerprint: str) -> bool:
        if not fingerprint:
            return False
        with self._lock:
            return fingerprint in self.queued_fingerprints or fingerprint in self.sent_fingerprints

    def mark_sent(self, event_type: str, now_ts: float, fingerprint: str = "") -> None:
        with self._lock:
            self.last_send_time = now_ts
            if fingerprint:
                self.queued_fingerprints.pop(fingerprint, None)
                self.sent_fingerprints[fingerprint] = now_ts

            if event_type == "welcome":
                self.last_welcome_time = now_ts
            elif event_type == "gift":
                self.last_gift_time = now_ts
            elif event_type == "chat":
                self.last_chat_time = now_ts
            elif event_type == "warmup":
                self.last_warmup_time = now_ts
            elif event_type == "pk_timer":
                self.last_pk_time = now_ts
