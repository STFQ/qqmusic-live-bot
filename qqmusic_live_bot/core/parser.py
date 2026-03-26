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

# 🔪 [修复] 加入血包炸弹，防止带冒号的系统提示被当成用户聊天
SYSTEM_KEYWORDS = ["系统", "欢迎来到", "直播间", "已关注", "分享了直播间", "血包", "炸弹", "宝箱"]
GIFT_EXCLUDE_PATTERNS = [
    re.compile(r"抢到了.*?送出的红包"),
]
PK_CONTEXT_KEYWORDS = ["排位赛"]
PK_EXCLUDE_KEYWORDS = [
    "结果展示", "胜负已分", "胜利", "失败", "本场MVP", "MVP",
    "魔法合成", "热门榜", "抢头条", "排位置", "抢血包", "抢炸弹"
]
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

    def _parse_line(self, line: str, ts: float) -> Event | None:
        cleaned_line = self._strip_icon_placeholders(line)

        if TIMER_PATTERN.match(cleaned_line):
            return None

        for pattern in WELCOME_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
                user = self._clean_user_name(match.group(1))
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

        # 系统词拦截
        if any(keyword in cleaned_line for keyword in SYSTEM_KEYWORDS):
            return Event(type=EventType.SYSTEM, raw=line, ts=ts, content=cleaned_line)

        for pattern in CHAT_PATTERNS:
            match = pattern.search(cleaned_line)
            if match:
                user = self._clean_user_name(match.group(1))
                content = match.group(2).strip()
                if not user or not content or "系统" in user:
                    return None
                return Event(type=EventType.CHAT, raw=line, ts=ts, user=user, content=content)

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

        # 🔪 [核心修复1] 定义假倒计时危险词
        FAKE_TIMER_KEYWORDS = ["血包", "炸弹", "宝箱", "红包"]

        for index, line in enumerate(source_lines):
            match = TIMER_PATTERN.match(line)
            if not match:
                continue

            minute = int(match.group(1))
            second = int(match.group(2))
            if not (0 <= minute <= 10 and 0 <= second < 60):
                continue
            total = minute * 60 + second

            # 🔪 [核心修复2] 扩大侦察范围（上下文窗口），看上下2行
            window_start = max(0, index - 2)
            window_end = min(len(source_lines), index + 3)
            context_window = source_lines[window_start:window_end]

            # 判断窗口里有没有排位赛，有没有血包炸弹
            window_has_context = any(self._is_pk_context_line(item) for item in context_window)
            window_has_fake = any(self._has_keywords(item, FAKE_TIMER_KEYWORDS) for item in context_window)

            # 只要自身或附近出现了血包炸弹，不管三七二十一直接枪毙！
            if self._has_keywords(line, FAKE_TIMER_KEYWORDS) or window_has_fake:
                continue

            # 如果附近有排位赛，且通过了上面的安全检查，加入候选
            if self._is_pk_context_line(line) or window_has_context:
                candidates.append(total)

        if not candidates:
            return None

        # 🔪 [核心修复3] 神级兜底，取最大值！真PK是几分钟，血包只有十几秒。
        seconds = max(candidates)
        return Event(type=EventType.PK_TIMER, raw=f"pk:{seconds}", ts=ts, content=str(seconds),
                     meta={"seconds": seconds})