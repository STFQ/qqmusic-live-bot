from __future__ import annotations

import re
import time

from .events import Frame
from ..strategy.filters import normalize_text

GIFT_THANKS_REGION = (52, 1543, 855, 2565)
COMMENT_RESOURCE_ID = "com.tencent.qqmusic:id/mlive_comment_item_content"
PK_STATUS_RESOURCE_ID = "com.tencent.qqmusic:id/mlive_audio_link_pk_status_view"
WELCOME_RESOURCE_ID = "com.tencent.qqmusic:id/mlive_item_join_room_content"
PK_TIME_PATTERN = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
PK_STATUS_EXCLUDE_KEYWORDS = ("结果展示",)


class TextCollector:
    def __init__(self, line_ttl: float = 12.0, y_tolerance: float = 20.0):
        self.line_ttl = line_ttl
        self.y_tolerance = y_tolerance

    def _collect_comment_nodes(self, device):
        try:
            return device.xpath(f'//*[@resource-id="{COMMENT_RESOURCE_ID}"]').all()
        except Exception:
            return []

    def _collect_region_texts(self, device, region: tuple[int, int, int, int]) -> list[str]:
        nodes = self._collect_comment_nodes(device)

        left_limit, top_limit, right_limit, bottom_limit = region
        texts: list[str] = []
        seen: set[tuple[str, tuple[int, int, int, int]]] = set()

        for node in nodes:
            text = normalize_text(getattr(node, "text", ""))
            if not text:
                continue
            bounds = getattr(node, "bounds", (0, 0, 0, 0))
            left, top, right, bottom = bounds
            if right <= left or bottom <= top:
                continue
            intersects = not (
                right <= left_limit
                or right_limit <= left
                or bottom <= top_limit
                or bottom_limit <= top
            )
            if not intersects:
                continue
            key = (text, (left, top, right, bottom))
            if key in seen:
                continue
            seen.add(key)
            texts.append(text)

        return texts

    def _collect_pk_status(self, device) -> tuple[str, int | None]:
        try:
            node = device.xpath(f'//*[@resource-id="{PK_STATUS_RESOURCE_ID}"]').get(timeout=2)
        except Exception:
            return "", None

        text = normalize_text(getattr(node, "text", ""))
        if not text:
            return "", None
        if any(keyword in text for keyword in PK_STATUS_EXCLUDE_KEYWORDS):
            return text, None

        match = PK_TIME_PATTERN.search(text)
        if not match:
            return text, None

        minute = int(match.group(1))
        second = int(match.group(2))
        if not (0 <= minute <= 10 and 0 <= second < 60):
            return text, None
        return text, minute * 60 + second

    def _collect_welcome_nodes(self, device) -> list[dict[str, object]]:
        try:
            nodes = device.xpath(f'//*[@resource-id="{WELCOME_RESOURCE_ID}"]').all()
        except Exception:
            return []

        items: list[dict[str, object]] = []
        seen: set[tuple[str, tuple[int, int, int, int], str]] = set()

        for node in nodes:
            text = normalize_text(getattr(node, "text", ""))
            if not text:
                continue
            bounds = getattr(node, "bounds", (0, 0, 0, 0))
            left, top, right, bottom = bounds
            if right <= left or bottom <= top:
                continue
            info = getattr(node, "info", None) or {}
            resource_id = info.get("resourceName") or info.get("resourceId") or ""
            class_name = info.get("className") or info.get("class") or "android.widget.TextView"
            key = (text, (left, top, right, bottom), resource_id)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "text": text,
                    "bounds": [left, top, right, bottom],
                    "resource_id": resource_id,
                    "class": class_name,
                }
            )

        return items

    def collect(self, device) -> Frame:
        now_ts = time.time()
        gift_lines = self._collect_region_texts(device, GIFT_THANKS_REGION)
        welcome_nodes = self._collect_welcome_nodes(device)
        pk_status_text, pk_seconds = self._collect_pk_status(device)
        return Frame(
            ts=now_ts,
            gift_lines=gift_lines,
            welcome_nodes=welcome_nodes,
            pk_status_text=pk_status_text,
            pk_seconds=pk_seconds,
        )
