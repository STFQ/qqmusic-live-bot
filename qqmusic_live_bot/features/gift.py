from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS
from ..strategy.templates import GIFT_TEMPLATES, pick


class GiftFeature:
    def __init__(self) -> None:
        self.pending: dict[tuple[str, str], dict[str, object]] = {}
        self.seen_gifts: dict[str, float] = {}

    def _cleanup(self, now_ts: float) -> None:
        ttl = max(LIMITS["dedupe_ttl"], LIMITS["gift_merge_window"] * 3)
        self.seen_gifts = {
            key: ts for key, ts in self.seen_gifts.items() if now_ts - ts < ttl
        }
        self.pending = {
            key: value
            for key, value in self.pending.items()
            if now_ts - float(value["last_seen"]) < LIMITS["dedupe_ttl"]
        }

    def _ingest(self, events: list[Event], now_ts: float) -> None:
        for event in events:
            if event.type != EventType.GIFT:
                continue
            if event.fingerprint in self.seen_gifts:
                continue
            self.seen_gifts[event.fingerprint] = now_ts
            key = (event.user, event.content)
            bucket = self.pending.get(key)
            if bucket is None:
                self.pending[key] = {
                    "user": event.user,
                    "gift": event.content,
                    "count": event.count,
                    "first_seen": now_ts,
                    "last_seen": now_ts,
                    "raw_items": [event.raw],
                }
                continue
            bucket["count"] = int(bucket["count"]) + event.count
            bucket["last_seen"] = now_ts
            raw_items = list(bucket["raw_items"])
            raw_items.append(event.raw)
            bucket["raw_items"] = raw_items[-5:]

    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        self._cleanup(now_ts)
        self._ingest(events, now_ts)
        if now_ts - state.last_gift_time < LIMITS["gift_thank_interval"]:
            return None
        if not self.pending:
            return None

        ready_items = []
        for key, payload in self.pending.items():
            wait_time = now_ts - float(payload["last_seen"])
            if wait_time >= LIMITS["gift_merge_window"]:
                ready_items.append((key, payload))
        if not ready_items:
            ready_items = list(self.pending.items())

        key, payload = sorted(ready_items, key=lambda item: float(item[1]["first_seen"]))[0]
        count = int(payload["count"])
        gift = str(payload["gift"])
        user = str(payload["user"])
        gift_label = gift if count <= 1 else f"{gift} x{count}"
        text = pick(GIFT_TEMPLATES, user=user, gift=gift_label)
        raw = f"gift:{user}:{gift}:{count}"
        self.pending.pop(key, None)
        return ReplyAction(text=text, reason="gift_thanks", event_type="gift", user=user, raw=raw)
