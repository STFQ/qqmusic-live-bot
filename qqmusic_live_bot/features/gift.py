from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.templates import GIFT_TEMPLATES, pick


class GiftFeature:
    def __init__(self, limits: dict[str, float]) -> None:
        self.limits = limits
        self.pending: dict[tuple[str, str], dict[str, object]] = {}
        # Independent gift dedupe cache to avoid re-thanking old sticky gift lines.
        self.seen: dict[tuple[str, str], dict[str, float]] = {}
        self.seen_ttl = float(self.limits.get("gift_seen_ttl", 1800.0))
        self.same_key_gap = float(self.limits.get("gift_same_key_gap", 30.0))

    def _cleanup(self, now_ts: float) -> None:
        self.pending = {
            key: value
            for key, value in self.pending.items()
            if now_ts - float(value["last_seen"]) < 15.0
        }
        self.seen = {
            key: value
            for key, value in self.seen.items()
            if now_ts - float(value["last_seen"]) < self.seen_ttl
        }

    def _should_accept_gift(self, event: Event, now_ts: float) -> bool:
        key = (event.user, event.content)
        record = self.seen.get(key)
        if record is None:
            self.seen[key] = {"last_count": float(event.count), "last_seen": now_ts}
            return True

        last_count = int(record.get("last_count", 0))
        last_seen = float(record.get("last_seen", 0.0))

        # Same user+gift after a gap should be treated as a new gift instance.
        if now_ts - last_seen > self.same_key_gap:
            self.seen[key] = {"last_count": float(event.count), "last_seen": now_ts}
            return True

        # Continuous combo increments should be accepted.
        if int(event.count) > last_count:
            self.seen[key] = {"last_count": float(event.count), "last_seen": now_ts}
            return True

        return False

    def _ingest(self, events: list[Event], now_ts: float) -> None:
        for event in events:
            if event.type != EventType.GIFT:
                continue
            if not self._should_accept_gift(event, now_ts):
                continue

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

            current_count = int(bucket["count"])
            if event.count > 1:
                bucket["count"] = max(current_count, event.count)
            else:
                bucket["count"] = current_count + event.count

            bucket["last_seen"] = now_ts
            raw_items = list(bucket["raw_items"])
            raw_items.append(event.raw)
            bucket["raw_items"] = raw_items[-5:]

    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        self._cleanup(now_ts)
        self._ingest(events, now_ts)

        if now_ts - state.last_gift_time < self.limits.get("gift_thank_interval", 0.0):
            return None

        if not self.pending:
            return None

        ready_items = []
        for key, payload in self.pending.items():
            wait_time = now_ts - float(payload["last_seen"])
            if wait_time >= self.limits.get("gift_merge_window", 1.0):
                ready_items.append((key, payload))

        if not ready_items:
            return None

        key, payload = sorted(ready_items, key=lambda item: float(item[1]["first_seen"]))[0]
        count = int(payload["count"])
        gift = str(payload["gift"])
        user = str(payload["user"])

        gift_label = gift if count <= 1 else f"{gift} x{count}"
        text = pick(GIFT_TEMPLATES, user=user, gift=gift_label)
        raw = f"gift:{user}:{gift}:{count}"

        self.pending.pop(key, None)

        return ReplyAction(
            text=text,
            reason="gift_thanks",
            event_type="gift",
            user=user,
            raw=raw,
            meta={"gift": gift_label},
        )
