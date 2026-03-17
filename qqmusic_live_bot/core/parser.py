from __future__ import annotations

import re
from typing import Iterable

from .events import Event, EventType, Frame

WELCOME_PATTERNS = [
    re.compile(r"^(.*?)(?:\s来了|\s进入了直播间|\s加入了直播间)$"),
    re.compile(r"^(.*?)\s(?:进入|来到)直播间$"),
]

GIFT_PATTERNS = [
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送出\s*(.+?)\s*[xX×]\s*(\d+)\s*$"),
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送出\s*(.+?)\s*$"),
    re.compile(r"^\s*(.*?)\s*[:：]?\s*送\s*(.+?)\s*[xX×]\s*(\d+)\s*$"),
    re.compile(r"^(.*?)\s(?:赠送了|投喂了|送来了)\s(.+)$"),
]

CHAT_PATTERNS = [
    re.compile(r"^\s*([^:：]{1,24})\s*[:：]\s*(.+)$"),
    re.compile(r"^\s*@?([^ ]{1,24})\s+说\s+(.+)$"),
]

SYSTEM_KEYWORDS = ["系统", "欢迎来到", "直播间", "已关注", "分享了直播间"]
GIFT_EXCLUDE_PATTERNS = [
    re.compile(r"抢到了.*?送出的红包"),
]
PK_CONTEXT_KEYWORDS = ["PK", "pk", "倒计时", "排位赛", "抢道具", "送礼", "助力", "上分"]
PK_EXCLUDE_KEYWORDS = ["结果展示", "胜负已分", "胜利", "失败", "本场MVP", "MVP", "魔法合成", "热门榜", "抢头条"]
ICON_PLACEHOLDER_PATTERN = re.compile(r"\[(?:ICON)+\]")

# 严格匹配倒计时格式的正则
TIMER_PATTERN = re.compile(r"^\s*(?:(?:PK|pk|倒计时|排位赛|距结束|剩余)\s*)?(\d{1,2})\s*[:：]\s*(\d{2})\s*$")


class EventParser:
    def parse(self, frame: Frame) -> list[Event]:
        events: list[Event] = []
        for line in frame.lines:
            event = self._parse_line(line, frame.ts)
            if event:
                events.append(event)
        pk_event = self._extract_pk(frame.lines, frame.ts)
        if pk_event:
            events.append(pk_event)
        return events

    def _clean_user_name(self, user: str) -> str:
        user = user.strip()
        cleaned = re.sub(r"^\d+\s*", "", user)
        result = cleaned if cleaned else user

        # [新增] 纯符号/表情包屏蔽过滤
        # 如果名字里连一个中文、英文字母或数字都没有（比如全是 "...." 或 "-_-")
        # 认为它是无意义的纯符号名字，直接清空。
        if not re.search(r"[a-zA-Z0-9\u4e00-\u9fa5]", result):
            return ""

        return result

    def _parse_line(self, line: str, ts: float) -> Event | None:
        cleaned_line = self._strip_icon_placeholders(line)
        
        if TIMER_PATTERN.match(cleaned_line):
            return None
            
        for pattern in WELCOME_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
                user = self._clean_user_name(match.group(1))
                # [优化] 如果用户名经过清洗后变为空（纯符号人），直接拦截返回 None，假装没看见他
                if not user or "系统" in user:
                    return None
                return Event(type=EventType.WELCOME, raw=line, ts=ts, user=user, content="enter")
                
        if any(pattern.search(cleaned_line) for pattern in GIFT_EXCLUDE_PATTERNS):
            return Event(type=EventType.SYSTEM, raw=line, ts=ts, content=cleaned_line)
            
        for pattern in GIFT_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
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
                
        for pattern in CHAT_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
                user = self._clean_user_name(match.group(1))
                content = match.group(2).strip()
                # [优化] 如果是纯符号人发的聊天，也直接无视掉
                if not user or not content or "系统" in user:
                    return None
                return Event(type=EventType.CHAT, raw=line, ts=ts, user=user, content=content)
                
        if any(keyword in cleaned_line for keyword in SYSTEM_KEYWORDS):
            return Event(type=EventType.SYSTEM, raw=line, ts=ts, content=cleaned_line)
        return Event(type=EventType.CHAT, raw=line, ts=ts, content=cleaned_line)

    def _strip_icon_placeholders(self, text: str) -> str:
        return re.sub(r"\s+", " ", ICON_PLACEHOLDER_PATTERN.sub("", text or "")).strip()

    def _has_keywords(self, line: str, keywords: Iterable[str]) -> bool:
        return any(keyword in line for keyword in keywords)

    def _is_pk_context_line(self, line: str) -> bool:
        return self._has_keywords(line, PK_CONTEXT_KEYWORDS) and not self._has_keywords(line, PK_EXCLUDE_KEYWORDS)

    def _extract_pk(self, lines: Iterable[str], ts: float) -> Event | None:
        source_lines = list(lines)
        candidates: list[int] = []

        for index, line in enumerate(source_lines):
            context_window = source_lines[max(0, index - 2): min(len(source_lines), index + 3)]
            window_has_context = any(self._is_pk_context_line(item) for item in context_window)
            window_has_excluded = any(self._has_keywords(item, PK_EXCLUDE_KEYWORDS) for item in context_window)

            match = TIMER_PATTERN.match(line)
            if match:
                minute = int(match.group(1))
                second = int(match.group(2))
                if not (0 <= minute <= 10 and 0 <= second < 60):
                    continue
                total = minute * 60 + second
                line_has_context = self._is_pk_context_line(line)
                if line_has_context or (window_has_context and not window_has_excluded):
                    candidates.append(total)

        if not candidates:
            return None
        seconds = min(candidates)
        return Event(type=EventType.PK_TIMER, raw=f"pk:{seconds}", ts=ts, content=str(seconds), meta={"seconds": seconds})