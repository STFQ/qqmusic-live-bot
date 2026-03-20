from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS
from ..strategy.templates import GIFT_TEMPLATES, pick


class GiftFeature:
    def __init__(self) -> None:
        # [修改] 彻底干掉了 seen_gifts（防重指纹池），因为 collector 已经在物理层面帮我们去重了！
        # 现在只保留 pending，用来等待大哥的连击合并
        self.pending: dict[tuple[str, str], dict[str, object]] = {}

    def _cleanup(self, now_ts: float) -> None:
        # [修改] 不再依赖容易引发血案的 dedupe_ttl。
        # 这里仅仅作为一个底层的内存泄漏保护：如果有个礼物卡在队列里 15 秒还没处理掉，才会被清理。
        self.pending = {
            key: value
            for key, value in self.pending.items()
            if now_ts - float(value["last_seen"]) < 15.0
        }

    def _ingest(self, events: list[Event], now_ts: float) -> None:
        for event in events:
            if event.type != EventType.GIFT:
                continue

            # 🔪 [核心删除] 以前这里有一行 if event.fingerprint in self.seen_gifts: continue
            # 已经被彻底删除了！我们 100% 信任传进来的都是新弹幕！

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

            # 【完美保留】：大哥连击礼物（如 x2, x3）依然会在这里合并！
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

        # 频率控制：距离上次感谢必须大于设定的间隔
        if now_ts - state.last_gift_time < LIMITS.get("gift_thank_interval", 0.0):
            return None

        if not self.pending:
            return None

        # 【核心拦截】：筛选出度过“合并窗口期”（比如 1.5 秒内没有再连击）的礼物
        ready_items = []
        for key, payload in self.pending.items():
            wait_time = now_ts - float(payload["last_seen"])
            if wait_time >= LIMITS.get("gift_merge_window", 1.0):
                ready_items.append((key, payload))

        if not ready_items:
            return None

        # 优先感谢最早送出的那个
        key, payload = sorted(ready_items, key=lambda item: float(item[1]["first_seen"]))[0]
        count = int(payload["count"])
        gift = str(payload["gift"])
        user = str(payload["user"])

        gift_label = gift if count <= 1 else f"{gift} x{count}"
        text = pick(GIFT_TEMPLATES, user=user, gift=gift_label)
        raw = f"gift:{user}:{gift}:{count}"

        # 处理完毕，移出队列
        self.pending.pop(key, None)

        return ReplyAction(
            text=text,
            reason="gift_thanks",
            event_type="gift",
            user=user,
            raw=raw,
            meta={"gift": gift_label},
        )