from __future__ import annotations

import time
from dataclasses import dataclass

from .events import Frame
from ..strategy.filters import normalize_text

CHROME_NOISE_TEXTS = {
    "ATX",
    "LibChecker",
    "QQ音乐",
    "图库",
    "应用分身",
    "文件",
    "设置",
}

NOISE_SUBSTRINGS = (
    "MVP",
    "No.",
    "PK结果",
    "结果展示",
    "抢到了",
    "抢头条",
    "抢红包",
    "热门榜",
    "积分",
    "已集满",
    "微博挂件",
    "红包挂件",
    "礼物殿堂",
    "礼物卡",
    "本场MVP",
    "热门活动",
    "助力粉丝宝箱",
    "助力主播胜利",
    "合成",
    "魔法",
    "白银礼物卡",
    "赠 给",
    "赠给",
)


@dataclass
class TextNode:
    text: str
    bounds: tuple[int, int, int, int]

    @property
    def center_x(self) -> float:
        return (self.bounds[0] + self.bounds[2]) / 2

    @property
    def center_y(self) -> float:
        return (self.bounds[1] + self.bounds[3]) / 2


@dataclass
class CollectorState:
    recent_items: dict[str, list[dict[str, float]]]


class TextCollector:
    def __init__(self, line_ttl: float = 12.0, y_tolerance: float = 20.0):
        self.line_ttl = line_ttl
        self.y_tolerance = y_tolerance
        self.state = CollectorState(recent_items={})

    def _cleanup(self, now_ts: float) -> None:
        cleaned: dict[str, list[dict[str, float]]] = {}
        for text, records in self.state.recent_items.items():
            alive = [record for record in records if now_ts - record["ts"] < self.line_ttl]
            if alive:
                cleaned[text] = alive
        self.state.recent_items = cleaned

    def _device_window_size(self, device) -> tuple[int, int]:
        try:
            width, height = device.window_size()
            return int(width), int(height)
        except Exception:
            return (1080, 1920)

    def _is_noise_text(self, text: str) -> bool:
        if text in CHROME_NOISE_TEXTS:
            return True
        lowered = text.lower()
        if lowered in {"qqmusic", "libchecker"}:
            return True
        compact = text.replace(" ", "")
        return any(token in text or token in compact for token in NOISE_SUBSTRINGS)

    def _in_live_region(self, bounds: tuple[int, int, int, int], window_size: tuple[int, int]) -> bool:
        width, height = window_size
        left, top, right, bottom = bounds
        if width <= 0 or height <= 0:
            return False
        if right <= left or bottom <= top:
            return False

        center_x = (left + right) / 2
        center_y = (top + bottom) / 2

        in_pk_band = height * 0.06 <= center_y <= height * 0.26 and width * 0.24 <= center_x <= width * 0.78
        in_message_band = height * 0.22 <= center_y <= height * 0.80 and center_x <= width * 0.78
        return in_pk_band or in_message_band

    def _collect_textview_nodes(self, device) -> list[TextNode]:
        window_size = self._device_window_size(device)

        try:
            nodes = device.xpath("//android.widget.TextView").all()
        except Exception:
            return []

        candidates: list[TextNode] = []

        for node in nodes:
            text = normalize_text(getattr(node, "text", ""))
            if not text or self._is_noise_text(text):
                continue
            bounds = getattr(node, "bounds", (0, 0, 0, 0))
            if not self._in_live_region(bounds, window_size):
                continue
            candidates.append(TextNode(text=text, bounds=bounds))

        return sorted(candidates, key=lambda item: (item.center_y, item.center_x))

    def _extract_new_lines_by_spatial(self, current_nodes: list[TextNode], now_ts: float) -> list[str]:
        new_lines: list[str] = []

        for node in current_nodes:
            text = node.text
            current_y = node.center_y
            history = self.state.recent_items.get(text, [])

            appears_lower = bool(history) and current_y > max(record["y"] for record in history) + self.y_tolerance

            if not history or appears_lower:
                new_lines.append(text)

            updated_history = history + [{"y": current_y, "ts": now_ts}]
            self.state.recent_items[text] = updated_history[-20:]

        return new_lines

    def collect(self, device) -> Frame:
        now_ts = time.time()
        self._cleanup(now_ts)

        current_nodes = self._collect_textview_nodes(device)
        raw_lines = [node.text for node in current_nodes]
        real_new_lines = self._extract_new_lines_by_spatial(current_nodes, now_ts)
        return Frame(ts=now_ts, raw_lines=raw_lines, lines=real_new_lines)
