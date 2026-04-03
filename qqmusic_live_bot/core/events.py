from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    WELCOME = "welcome"
    GIFT = "gift"
    CHAT = "chat"
    PK_TIMER = "pk_timer"
    SYSTEM = "system"


@dataclass
class Event:
    type: EventType
    raw: str
    ts: float
    user: str = ""
    content: str = ""
    count: int = 1
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return f"{self.type}|{self.user}|{self.content}|{self.count}|{self.raw}"


@dataclass
class Frame:
    ts: float
    raw_lines: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    gift_lines: list[str] = field(default_factory=list)
    welcome_nodes: list[dict[str, Any]] = field(default_factory=list)
    pk_status_text: str = ""
    pk_seconds: int | None = None


@dataclass
class ReplyAction:
    text: str
    reason: str
    event_type: str
    user: str = ""
    raw: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
