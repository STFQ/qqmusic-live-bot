from __future__ import annotations

import re

from .events import Event, EventType, Frame

WELCOME_PATTERNS = [
    re.compile(r"^(.*?)(?:\s来了|\s进入了直播间|\s加入了直播间)$"),
    re.compile(r"^(.*?)\s(?:进入|来到)直播间$"),
    re.compile(r"^(.*?)\s*进入了直播间$"),
    re.compile(r"^(.*?)\s*加入了直播间$"),
]

GIFT_PATTERNS = [
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送出\s*(.+?)\s*[xX×]\s*(\d+)\s*$"),
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送出\s*(.+?)\s*$"),
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送\s*(.+?)\s*[xX×]\s*(\d+)\s*$"),
    re.compile(r"^(.*?)\s(?:赠送了|投喂了|送来了)\s(.+)$"),
]
GIFT_EXCLUDE_PATTERNS = [
    re.compile(r"抢到了.*?送出的红包"),
]
ICON_PLACEHOLDER_PATTERN = re.compile(r"\[(?:ICON)+\]")


class EventParser:
    def parse(self, frame: Frame) -> list[Event]:
        events: list[Event] = []
        seen_fingerprints: set[str] = set()

        for node in frame.welcome_nodes:
            line = str(node.get("text", ""))
            event = self._parse_welcome_line(line, frame.ts)
            if event:
                seen_fingerprints.add(event.fingerprint)
                events.append(event)

        for line in frame.gift_lines:
            event = self._parse_gift_line(line, frame.ts)
            if event and event.fingerprint not in seen_fingerprints:
                seen_fingerprints.add(event.fingerprint)
                events.append(event)

        pk_event = self._extract_pk_from_frame(frame)
        if pk_event:
            events.append(pk_event)
        return events

    def _clean_user_name(self, user: str) -> str:
        # 🔪 [新增] 1. 清除 Unicode 隐形字符/排版控制字符 (专门对付 ‮..‭ 这类妖魔鬼怪)
        # 包含：零宽空格、从右向左覆盖符(RLO)等
        user = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]', '', user)

        # 2. 去除常规首尾空白
        user = user.strip()

        # 3. 去除名字开头的财富等级数字 (比如 "15 张三" -> "张三")
        cleaned = re.sub(r"^\d+\s*", "", user)
        result = cleaned if cleaned else user

        # 🔪 [新增] 4. 清理名字尾部的无意义残留符号
        # 把名字最后面挂着的点点点、横杠、波浪号全部切掉 (比如 "橙橙橙 .." -> "橙橙橙")
        # 注意：只切尾部，保留名字中间的符号（比如 "A.B.C" 还会是 "A.B.C"）
        result = re.sub(r'[\s\.\-_~\*]+$', '', result)

        # 5. 纯符号/表情包屏蔽过滤
        # 如果清洗完之后，名字里连一个中文、英文字母或数字都没有，直接当空气处理
        if not re.search(r"[a-zA-Z0-9\u4e00-\u9fa5]", result):
            return ""

        return result

    def _parse_welcome_line(self, line: str, ts: float) -> Event | None:
        cleaned_line = self._strip_icon_placeholders(line)

        for pattern in WELCOME_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
                user = self._clean_user_name(match.group(1))
                if not user or "系统" in user:
                    return None
                return Event(type=EventType.WELCOME, raw=line, ts=ts, user=user, content="enter")
        return None

    def _parse_gift_line(self, line: str, ts: float) -> Event | None:
        cleaned_line = self._strip_icon_placeholders(line)

        if any(pattern.search(cleaned_line) for pattern in GIFT_EXCLUDE_PATTERNS):
            return None

        for pattern in GIFT_PATTERNS:
            match = pattern.search(cleaned_line)
            if not match:
                continue
            user = self._clean_user_name(match.group(1))
            gift = self._strip_icon_placeholders(match.group(2))
            if not user or "系统" in user:
                return None
            count = 1
            if match.lastindex and match.lastindex >= 3 and match.group(3):
                try:
                    count = max(1, int(match.group(3)))
                except ValueError:
                    count = 1
            return Event(type=EventType.GIFT, raw=line, ts=ts, user=user, content=gift or "礼物", count=count)

        return None

    def _strip_icon_placeholders(self, text: str) -> str:
        return re.sub(r"\s+", " ", ICON_PLACEHOLDER_PATTERN.sub("", text or "")).strip()

    def _extract_pk_from_frame(self, frame: Frame) -> Event | None:
        if frame.pk_seconds is None:
            return None
        return Event(
            type=EventType.PK_TIMER,
            raw=frame.pk_status_text or f"pk:{frame.pk_seconds}",
            ts=frame.ts,
            content=str(frame.pk_seconds),
            meta={"seconds": frame.pk_seconds, "source": "pk_status_view", "text": frame.pk_status_text},
        )
