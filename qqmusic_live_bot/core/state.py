from __future__ import annotations

from dataclasses import dataclass, field


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
    sent_fingerprints: dict[str, float] = field(default_factory=dict)
    seen_event_fingerprints: dict[str, float] = field(default_factory=dict)
    last_pk_seconds: int | None = None

    def cleanup(self, now_ts: float, ttl: float = 120.0) -> None:
        self.sent_fingerprints = {
            key: ts for key, ts in self.sent_fingerprints.items() if now_ts - ts < ttl
        }
        self.seen_event_fingerprints = {
            key: ts for key, ts in self.seen_event_fingerprints.items() if now_ts - ts < ttl
        }

    def mark_sent(self, event_type: str, now_ts: float) -> None:
        self.last_send_time = now_ts
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
