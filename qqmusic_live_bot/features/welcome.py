from __future__ import annotations

from ..core.events import Event, EventType, ReplyAction
from ..core.state import BotState
from ..strategy.rules import LIMITS
from ..strategy.templates import WELCOME_TEMPLATES, pick


class WelcomeFeature:
    def __init__(self) -> None:
        # 🚀 [新增] 候客室：用来临时存放瞬间涌入的大量新人，保证一个都不漏！
        self.pending_welcomes: list[str] = []

    def select(self, events: list[Event], state: BotState, now_ts: float) -> ReplyAction | None:
        # 1. 把这一瞬间进来的所有人，全部拉进候客室排队！
        for event in events:
            if event.type == EventType.WELCOME:
                dedupe_key = f"welcome:{event.user}"
                # 如果没在这个会话里欢迎过，且还没在候客室里排队，就加进去
                if dedupe_key not in state.sent_fingerprints and event.user not in self.pending_welcomes:
                    self.pending_welcomes.append(event.user)

        # 2. 速度控制：如果还在 CD 冷却中，就等一会（现在我们在 rules 里设的是 0.0，所以瞬间放行）
        if now_ts - state.last_welcome_time < LIMITS.get("welcome_interval", 0.0):
            return None

        # 3. 如果候客室没人，直接返回
        if not self.pending_welcomes:
            return None

        # 4. 🔪 [核心修复] 按先来后到的顺序（FIFO），请出第一位客人！不再只看最后一个！
        target_user = self.pending_welcomes.pop(0)
        
        dedupe_key = f"welcome:{target_user}"
        text = pick(WELCOME_TEMPLATES, user=target_user)
        
        return ReplyAction(
            text=text, 
            reason="welcome", 
            event_type="welcome", 
            user=target_user, 
            raw=dedupe_key
        )