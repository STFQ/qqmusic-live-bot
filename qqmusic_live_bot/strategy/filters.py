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
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    return text[: max_len - 1].rstrip("，。！？,.!?:： ") + "…"


def _trim_segment(text: str, max_len: int) -> str:
    text = normalize_text(text)
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return text[:1]
    return text[: max_len - 1].rstrip("，。！？,.!?:： ") + "…"


def _trim_gift_label(text: str, max_len: int) -> str:
    text = normalize_text(text)
    if len(text) <= max_len:
        return text

    match = re.search(r"(\s[xX×]\d+)$", text)
    if not match:
        return _trim_segment(text, max_len)

    suffix = match.group(1)
    if max_len <= len(suffix) + 1:
        return _trim_segment(text, max_len)

    base = text[: match.start()].rstrip()
    head = _trim_segment(base, max_len - len(suffix))
    if not head:
        return _trim_segment(text, max_len)
    return f"{head}{suffix}"


def trim_gift_reply(user: str, gift: str, max_len: int) -> str:
    user = normalize_text(user)
    gift = normalize_text(gift)
    if not user or not gift:
        return trim_reply(f"谢谢 @{user} {gift}".strip(), max_len)

    prefix = "谢谢 @"
    separator = " "
    full_text = f"{prefix}{user}{separator}{gift}"
    if len(full_text) <= max_len:
        return full_text

    dynamic_budget = max_len - len(prefix) - len(separator)
    if dynamic_budget <= 0:
        return trim_reply("谢谢", max_len)

    user_budget = 0
    gift_budget = 0

    user_budget = 1
    dynamic_budget -= 1
    if gift and dynamic_budget > 0:
        gift_budget = 1
        dynamic_budget -= 1

    while dynamic_budget > 0:
        progressed = False
        if gift_budget < len(gift):
            gift_budget += 1
            dynamic_budget -= 1
            progressed = True
            if dynamic_budget == 0:
                break
        if user_budget < len(user):
            user_budget += 1
            dynamic_budget -= 1
            progressed = True
        if not progressed:
            break

    user_text = _trim_segment(user, user_budget)
    gift_text = _trim_gift_label(gift, gift_budget)
    return trim_reply(f"{prefix}{user_text}{separator}{gift_text}".strip(), max_len)
