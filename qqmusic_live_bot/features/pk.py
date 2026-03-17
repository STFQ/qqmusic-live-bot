from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS, PK_RULES
from ..strategy.templates import PK_FINAL_TEMPLATES, PK_ITEM_TEMPLATES, pick


class PKFeature:
    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        if not pk_events:
            state.pk_active = False
            state.last_pk_seconds = None
            return None
            
        seconds = int(pk_events[-1].meta.get("seconds", 0))
        state.pk_active = True
        
        if seconds >= PK_RULES["reset_at"]:
            state.last_pk_seconds = seconds
            return None
            
        if now_ts - state.last_pk_time < LIMITS["gift_thank_interval"]:
            return None
            
        # 1. 冲刺提醒：判断逻辑不变
        if seconds <= PK_RULES["final_remind_at"] and (state.last_pk_seconds is None or state.last_pk_seconds > PK_RULES["final_remind_at"]):
            state.last_pk_seconds = seconds
            return ReplyAction(text=pick(PK_FINAL_TEMPLATES), reason="pk_final", event_type="pk_timer")
            
        # 2. [核心修复] 抢道具提醒：增加 240 秒（4分钟）的强制下限门槛
        # 只有在 4 分钟到预定提醒时间之间的这个窗口期，才允许发抢道具弹幕
        if 240 <= seconds <= PK_RULES["item_remind_at"] and (state.last_pk_seconds is None or state.last_pk_seconds > PK_RULES["item_remind_at"]):
            state.last_pk_seconds = seconds
            return ReplyAction(text=pick(PK_ITEM_TEMPLATES), reason="pk_item", event_type="pk_timer")
            
        state.last_pk_seconds = seconds
        return None