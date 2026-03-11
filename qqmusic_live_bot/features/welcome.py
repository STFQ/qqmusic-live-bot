from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS
from ..strategy.templates import WELCOME_TEMPLATES, pick


class WelcomeFeature:
    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        if now_ts - state.last_welcome_time < LIMITS["welcome_interval"]:
            return None
        welcomes = [event for event in events if event.type == EventType.WELCOME]
        if not welcomes:
            return None
        target = welcomes[-1]
        dedupe_key = f"welcome:{target.user}"
        if dedupe_key in state.sent_fingerprints:
            return None
        text = pick(WELCOME_TEMPLATES, user=target.user)
        return ReplyAction(text=text, reason="welcome", event_type="welcome", user=target.user, raw=dedupe_key)
