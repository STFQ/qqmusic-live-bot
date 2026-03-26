from __future__ import annotations

from ..core.events import Frame, ReplyAction
from ..core.state import BotState
from ..strategy.templates import WARMUP_TEMPLATES, pick


class WarmupFeature:
    def __init__(self, limits: dict[str, float]) -> None:
        self.limits = limits

    def select(self, frame: Frame, state: BotState, now_ts: float) -> ReplyAction | None:
        if state.is_recently_handled("warmup"):
            return None
        if now_ts - state.last_warmup_time < self.limits["warmup_interval"]:
            return None
        non_system_lines = [line for line in frame.lines if "直播间" not in line and "系统" not in line]
        if len(non_system_lines) < 3:
            return None
        return ReplyAction(text=pick(WARMUP_TEMPLATES), reason="warmup", event_type="warmup", raw="warmup")
