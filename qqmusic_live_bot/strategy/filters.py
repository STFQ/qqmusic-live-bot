from __future__ import annotations

import re
from pathlib import Path

DEFAULT_BLACKLIST = [
    "加微信",
    "私聊",
    "返利",
    "代充",
    "兼职",
    "代理",
    "关注私信",
]


def load_blacklist(path: Path) -> list[str]:
    if not path.exists():
        return DEFAULT_BLACKLIST[:]
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data.get("keywords", DEFAULT_BLACKLIST[:])
    except Exception:
        return DEFAULT_BLACKLIST[:]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def should_skip_text(text: str, blacklist: list[str]) -> bool:
    if not text:
        return True
    return any(keyword in text for keyword in blacklist)


def trim_reply(text: str, max_len: int) -> str:
    text = normalize_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("，。！？,.!?:： ") + "…"

