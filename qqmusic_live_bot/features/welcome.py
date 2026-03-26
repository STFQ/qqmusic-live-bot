from __future__ import annotations

from collections import deque

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.templates import WELCOME_TEMPLATES, pick


class WelcomeFeature:
    def __init__(self, limits: dict[str, float]) -> None:
        self.limits = limits
        self.pending_welcomes: deque[str] = deque()
        self.seen_users: set[str] = set()
        self.seen_order: deque[str] = deque()
        self.max_seen_users = 500

    def _remember_user(self, user: str) -> None:
        if user in self.seen_users:
            return
        self.seen_users.add(user)
        self.seen_order.append(user)
        while len(self.seen_order) > self.max_seen_users:
            oldest = self.seen_order.popleft()
            self.seen_users.discard(oldest)

    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        for event in events:
            if event.type != EventType.WELCOME:
                continue
            user = (event.user or "").strip()
            if not user:
                continue
            dedupe_key = f"welcome:{user}"
            if state.is_recently_handled(dedupe_key):
                continue
            if user in self.seen_users:
                continue
            self.pending_welcomes.append(user)
            self._remember_user(user)

        if now_ts - state.last_welcome_time < self.limits.get("welcome_interval", 0.0):
            return None

        if not self.pending_welcomes:
            return None

        target_user = self.pending_welcomes.popleft()
        dedupe_key = f"welcome:{target_user}"
        text = pick(WELCOME_TEMPLATES, user=target_user)

        return ReplyAction(
            text=text,
            reason="welcome",
            event_type="welcome",
            user=target_user,
            raw=dedupe_key,
        )
