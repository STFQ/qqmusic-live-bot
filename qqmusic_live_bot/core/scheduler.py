from __future__ import annotations

from ..core.events import Event, Frame, ReplyAction
from ..core.state import BotState
from ..features.chat import ChatFeature
from ..features.gift import GiftFeature
from ..features.pk import PKFeature
from ..features.warmup import WarmupFeature
from ..features.welcome import WelcomeFeature
from ..strategy.rules import PK_RULES, TRIGGERS


class Scheduler:
    def __init__(
        self,
        flags: dict[str, bool],
        limits: dict[str, float],
        triggers: dict[str, list[str]] | None = None,
        pk_rules: dict[str, int] | None = None,
    ):
        self.flags = flags
        self.limits = limits
        self.gift = GiftFeature(limits)
        self.pk = PKFeature(limits, pk_rules or PK_RULES)
        self.welcome = WelcomeFeature(limits)
        self.chat = ChatFeature(limits, triggers or TRIGGERS)
        self.warmup = WarmupFeature(limits)

    def next_action(self, frame: Frame, events: list[Event], state: BotState) -> ReplyAction | None:
        now_ts = frame.ts
        if state.mode == "mute":
            return None
        if state.mode == "thanks_only":
            if self.flags.get("enable_gift_thanks"):
                return self.gift.select(events, state, now_ts)
            return None
        if state.mode == "warmup_only":
            if self.flags.get("enable_warmup"):
                return self.warmup.select(frame, state, now_ts)
            return None

        if self.flags.get("enable_gift_thanks"):
            action = self.gift.select(events, state, now_ts)
            if action:
                return action
        if self.flags.get("enable_pk_remind") and state.mode in {"auto", "semi"}:
            action = self.pk.select(events, state, now_ts)
            if action:
                return action
        if self.flags.get("enable_welcome") and state.mode in {"auto", "semi"}:
            action = self.welcome.select(events, state, now_ts)
            if action:
                return action
        if self.flags.get("enable_auto_reply") and state.mode == "auto":
            action = self.chat.select(events, state, now_ts)
            if action:
                return action
        if self.flags.get("enable_warmup") and state.mode in {"auto", "semi"}:
            return self.warmup.select(frame, state, now_ts)
        return None
