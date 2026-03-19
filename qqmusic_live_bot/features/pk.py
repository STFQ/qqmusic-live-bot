from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS, PK_RULES
from ..strategy.templates import PK_FINAL_TEMPLATES, PK_ITEM_TEMPLATES, pick


class PKFeature:
    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        pk_events = [event for event in events if event.type == EventType.PK_TIMER]

        # 优化：没看到倒计时的时候，只判定当前不在 PK，但绝对不要清空 last_pk_seconds 历史记忆！
        if not pk_events:
            state.pk_active = False
            return None

        seconds = int(pk_events[-1].meta.get("seconds", 0))
        state.pk_active = True

        # 自然重置机制：倒计时回到 280 秒左右（PK新开局），重新记录时间
        if seconds >= PK_RULES["reset_at"]:
            state.last_pk_seconds = seconds
            return None

        if now_ts - state.last_pk_time < LIMITS["gift_thank_interval"]:
            return None

        # 1. 冲刺提醒
        if seconds <= PK_RULES["final_remind_at"] and (
                state.last_pk_seconds is None or state.last_pk_seconds > PK_RULES["final_remind_at"]):
            state.last_pk_seconds = seconds
            return ReplyAction(text=pick(PK_FINAL_TEMPLATES), reason="pk_final", event_type="pk_timer")

        # 2. 抢道具提醒：增加 240 秒防呆下限（过期不提醒）
        if 240 <= seconds <= PK_RULES["item_remind_at"] and (
                state.last_pk_seconds is None or state.last_pk_seconds > PK_RULES["item_remind_at"]):
            state.last_pk_seconds = seconds
            return ReplyAction(text=pick(PK_ITEM_TEMPLATES), reason="pk_item", event_type="pk_timer")

        # 无论有没有触发动作，都要持续更新记忆，防止漏掉时间点
        state.last_pk_seconds = seconds
        return None