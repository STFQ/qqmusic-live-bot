from __future__ import annotations

import re
import subprocess
import time

from .events import Frame
from ..strategy.filters import normalize_text

PK_STATUS_RESOURCE_ID = "com.tencent.qqmusic:id/mlive_audio_link_pk_status_view"
PK_TIME_PATTERN = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
PK_STATUS_INCLUDE_KEYWORDS = ("排位赛", "鎺掍綅璧")
PK_STATUS_EXCLUDE_KEYWORDS = (
    "结果展示",
    "缁撴灉灞曠ず",
    "抢道具",
    "抢血包",
    "鎶㈤亾鍏",
    "鎶㈣鍖",
)

NETWORK_LOG_GLOB = "/data/data/com.tencent.qqmusic/files/log/network/NI_*"
WELCOME_URL_PATTERN = re.compile(
    r"(?:\x01\u0545F|\x01ՅF)?([^\x00\r\n]{1,36})\s*https?://(?:thirdwx\.qlogo\.cn/mmopen/vi_32|thirdqq\.qlogo\.cn/g\?b=sdk|pic6\.y\.qq\.com/qqmusic/avatar)/[^ \r\n]+/(?:132f|140f|1400)\x12([^\x00\r\n]{2,24})"
)
BARRAGE_STRUCT_PATTERN = re.compile(
    r"(?:\x01\u0545F|\x01ՅF)([^\x00\r\n]{1,36})\s*(https?://[^ \r\n]+/(?:132f|140f|1400))([^\x00\r\n]{1,120})\}",
    re.S,
)
BARRAGE_FALLBACK_PATTERN = re.compile(
    r"([A-Za-z0-9_\u4e00-\u9fff🦋✨😄😎🤗💞'@#·]{2,36})\s*[Vv][LlTt]?\s*https?://[^ \r\n]+/(?:132f|140f|1400)([^\x00\r\n]{1,140})\}",
    re.S,
)

WELCOME_HINT_KEYWORDS = (
    "进入了直播间",
    "加入了直播间",
    "通过关注进入直播间",
    "来了",
)
GIFT_HINT_KEYWORDS = ("送", "礼物", "x", "X", "×", "MVP", "点赞")
# Common mojibake markers when UTF-8 text was decoded as GBK.
MOJIBAKE_HINT_CHARS = "杩涘叆鎺掍綅缁撴灉鎶㈤亾鍏鏅琛屼綔"


class TextCollector:
    def __init__(self, line_ttl: float = 12.0, y_tolerance: float = 20.0, device_addr: str = "127.0.0.1:7555"):
        self.line_ttl = line_ttl
        self.y_tolerance = y_tolerance
        self.device_addr = device_addr
        self._network_log_path = ""
        self._network_offset = 0
        self._last_network_refresh = 0.0

    def _run_adb_bytes(self, shell_command: str) -> bytes:
        cp = subprocess.run(
            ["adb", "-s", self.device_addr, "shell", shell_command],
            capture_output=True,
        )
        if cp.returncode != 0:
            return b""
        return cp.stdout

    def _refresh_network_log_path(self, now_ts: float) -> None:
        if now_ts - self._last_network_refresh < 2.0:
            return
        self._last_network_refresh = now_ts
        out = self._run_adb_bytes(f"ls -t {NETWORK_LOG_GLOB} 2>/dev/null | head -n 1")
        if not out:
            return
        latest = out.decode("utf-8", errors="ignore").strip()
        if not latest:
            return
        if latest != self._network_log_path:
            self._network_log_path = latest
            # Start from EOF to avoid replaying historical backlog when switching files.
            size_out = self._run_adb_bytes(f"wc -c < {self._network_log_path}")
            try:
                self._network_offset = int(size_out.decode("utf-8", errors="ignore").strip() or "0")
            except ValueError:
                self._network_offset = 0

    @staticmethod
    def _recover_mojibake(text: str) -> str:
        s = text or ""
        if not s:
            return ""
        if not any(ch in s for ch in MOJIBAKE_HINT_CHARS):
            return s
        try:
            fixed = s.encode("gb18030", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            return s
        if not fixed:
            return s
        old_cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
        new_cjk = len(re.findall(r"[\u4e00-\u9fff]", fixed))
        return fixed if new_cjk >= old_cjk else s

    @staticmethod
    def _sanitize_user(user: str) -> str:
        user = re.sub(r"[\x00-\x1f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", user)
        user = user.strip().strip(":：")
        user = re.sub(r"\s+", "", user)
        user = re.sub(r"[Vv][LlTt]?$", "", user).strip()
        if (
            len(user) >= 3
            and re.match(r"^[A-Za-z][\u4e00-\u9fff]", user)
            and not re.search(r"[A-Za-z0-9]", user[1:])
        ):
            user = user[1:]
        if not user or "http" in user.lower() or "/" in user or "&" in user:
            return ""
        if "**" in user:
            return ""
        if len(user) < 2 or len(user) > 24:
            return ""
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", user):
            return ""
        if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", user):
            return ""
        return user

    @staticmethod
    def _sanitize_msg(msg: str) -> str:
        msg = re.sub(r"[\x00-\x1f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", msg or "")
        msg = normalize_text(msg).strip().strip(":：")
        msg = re.sub(r"\s+", "", msg)
        return msg

    def _extract_welcome(self, text: str) -> list[dict[str, object]]:
        welcome_nodes: list[dict[str, object]] = []
        seen: set[str] = set()
        for m in WELCOME_URL_PATTERN.finditer(text):
            user = self._sanitize_user(self._recover_mojibake(m.group(1)))
            message = self._sanitize_msg(self._recover_mojibake(m.group(2)))
            if not user or not message:
                continue
            if not any(k in message for k in WELCOME_HINT_KEYWORDS):
                continue
            line = f"{user} 进入了直播间"
            if line in seen:
                continue
            seen.add(line)
            welcome_nodes.append(
                {
                    "text": line,
                    "bounds": [0, 0, 0, 0],
                    "resource_id": "network:mlive.room_im.getmsg_small0",
                    "class": "network",
                }
            )
        return welcome_nodes

    def _iter_barrage_records(self, text: str):
        seen: set[tuple[str, str]] = set()

        for m in BARRAGE_STRUCT_PATTERN.finditer(text):
            user = self._sanitize_user(self._recover_mojibake(m.group(1)))
            msg = self._sanitize_msg(self._recover_mojibake(m.group(3)))
            if not user or not msg:
                continue
            if len(msg) < 2 or len(msg) > 48:
                continue
            if any(k in msg for k in WELCOME_HINT_KEYWORDS):
                continue
            trailing = text[m.end() : m.end() + 220]
            if "IMBarrageInfo" not in trailing:
                continue
            key = (user, msg)
            if key in seen:
                continue
            seen.add(key)
            yield user, msg

        # Fallback for payloads without the explicit marker prefix.
        for m in BARRAGE_FALLBACK_PATTERN.finditer(text):
            user = self._sanitize_user(self._recover_mojibake(m.group(1)))
            msg = self._sanitize_msg(self._recover_mojibake(m.group(2)))
            if not user or not msg:
                continue
            if len(msg) < 2 or len(msg) > 48:
                continue
            if any(k in msg for k in WELCOME_HINT_KEYWORDS):
                continue
            if any(k in msg for k in ("IMJoinAnimation", "IMJoinBubble", "treasureLevel", "join-room-bgpic")):
                continue
            key = (user, msg)
            if key in seen:
                continue
            seen.add(key)
            yield user, msg

    def _extract_gift_like_from_barrage(self, text: str) -> list[str]:
        gift_lines: list[str] = []
        for user, msg in self._iter_barrage_records(text):
            if not any(keyword in msg for keyword in GIFT_HINT_KEYWORDS):
                continue
            gift_lines.append(f"{user}：{msg}")
        return gift_lines

    def _collect_network_messages(self, now_ts: float) -> tuple[list[str], list[dict[str, object]]]:
        self._refresh_network_log_path(now_ts)
        if not self._network_log_path:
            return [], []

        start = self._network_offset + 1
        data = self._run_adb_bytes(f"tail -c +{start} {self._network_log_path}")
        if not data:
            return [], []
        self._network_offset += len(data)

        text = data.decode("utf-8", errors="ignore")
        welcome_nodes = self._extract_welcome(text)
        gift_lines = self._extract_gift_like_from_barrage(text)
        return gift_lines, welcome_nodes

    def _collect_pk_status(self, device) -> tuple[str, int | None]:
        try:
            node = device.xpath(f'//*[@resource-id="{PK_STATUS_RESOURCE_ID}"]').get(timeout=2)
        except Exception:
            return "", None

        text = self._recover_mojibake(normalize_text(getattr(node, "text", "")))
        if not text:
            return "", None
        if any(keyword in text for keyword in PK_STATUS_EXCLUDE_KEYWORDS):
            return text, None
        if not any(keyword in text for keyword in PK_STATUS_INCLUDE_KEYWORDS):
            return text, None

        match = PK_TIME_PATTERN.search(text)
        if not match:
            return text, None

        minute = int(match.group(1))
        second = int(match.group(2))
        if not (0 <= minute <= 10 and 0 <= second < 60):
            return text, None
        return text, minute * 60 + second

    def collect(self, device) -> Frame:
        now_ts = time.time()
        gift_lines, welcome_nodes = self._collect_network_messages(now_ts)
        pk_status_text, pk_seconds = self._collect_pk_status(device)
        return Frame(
            ts=now_ts,
            gift_lines=gift_lines,
            welcome_nodes=welcome_nodes,
            pk_status_text=pk_status_text,
            pk_seconds=pk_seconds,
        )
