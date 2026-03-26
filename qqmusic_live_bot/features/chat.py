from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.templates import CHAT_QUESTION_TEMPLATES, CHAT_REPLY_TEMPLATES, pick


class ChatFeature:
    def __init__(self, limits: dict[str, float], triggers: dict[str, list[str]]) -> None:
        self.limits = limits
        self.triggers = triggers

    def _is_triggered(self, event: Event) -> bool:
        content = event.content or event.raw
        lowered = content.lower()
        if any(name.lower() in lowered for name in self.triggers["names"]):
            return True
        return any(keyword.lower() in lowered for keyword in self.triggers["keywords"])

    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        if now_ts - state.last_chat_time < self.limits["chat_reply_interval"]:
            return None
        chats = [event for event in events if event.type == EventType.CHAT]
        for target in reversed(chats):
            if not self._is_triggered(target):
                continue
            if state.is_recently_handled(target.fingerprint):
                continue
            template_pool = CHAT_QUESTION_TEMPLATES if ("?" in target.content or "？" in target.content) else CHAT_REPLY_TEMPLATES
            text = pick(template_pool)
            return ReplyAction(text=text, reason="chat_trigger", event_type="chat", user=target.user, raw=target.fingerprint)
        return None
