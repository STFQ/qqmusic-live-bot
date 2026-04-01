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
    def __init__(
        self,
        line_ttl: float = 12.0,
        y_tolerance: float = 20.0,
        gift_region: tuple[float, float, float, float] | None = None,
    ):
        self.line_ttl = line_ttl
        self.y_tolerance = y_tolerance
        self.gift_region = gift_region
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

    def _in_region(self, bounds: tuple[int, int, int, int], region: tuple[float, float, float, float]) -> bool:
        left, top, right, bottom = bounds
        x1, y1, x2, y2 = region
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        return x1 <= center_x <= x2 and y1 <= center_y <= y2

    def _merge_inline_nodes(self, nodes: list[TextNode]) -> list[TextNode]:
        if len(nodes) < 2:
            return nodes

        merged: list[TextNode] = []
        used = [False] * len(nodes)
        y_tol = max(12.0, float(self.y_tolerance))
        gift_markers = ("送", "赠", "×", "x", "X")
        inline_gap_limit = max(6.0, float(self.y_tolerance) * 0.6)

        for i, left in enumerate(nodes):
            if used[i]:
                continue
            best_j = None
            for j in range(i + 1, len(nodes)):
                if used[j]:
                    continue
                right = nodes[j]
                # same-line merge
                # vertical alignment: center close or enough vertical overlap
                left_top, left_bottom = left.bounds[1], left.bounds[3]
                right_top, right_bottom = right.bounds[1], right.bounds[3]
                overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
                min_height = max(1, min(left_bottom - left_top, right_bottom - right_top))
                if overlap <= 0 and abs(left.center_y - right.center_y) > y_tol:
                    continue
                if overlap > 0 and overlap < min_height * 0.4 and abs(left.center_y - right.center_y) > y_tol:
                    continue
                if left.center_x >= right.center_x:
                    continue
                if not any(marker in right.text for marker in gift_markers):
                    continue
                best_j = j
                break

            if best_j is None:
                merged.append(left)
                used[i] = True
                continue

            right = nodes[best_j]
            combined_text = f"{left.text}：{right.text}"
            bounds = (
                min(left.bounds[0], right.bounds[0]),
                min(left.bounds[1], right.bounds[1]),
                max(left.bounds[2], right.bounds[2]),
                max(left.bounds[3], right.bounds[3]),
            )
            merged.append(TextNode(text=combined_text, bounds=bounds))
            used[i] = True
            used[best_j] = True

        for i, node in enumerate(nodes):
            if not used[i]:
                merged.append(node)

        return merged

    def _merge_stacked_gift_nodes(self, nodes: list[TextNode]) -> list[TextNode]:
        if len(nodes) < 2:
            return nodes

        merged: list[TextNode] = []
        used = [False] * len(nodes)
        gift_markers = ("送", "赠", "×", "x", "X")
        max_gap = max(10.0, float(self.y_tolerance) * 2.0)

        for i, top in enumerate(nodes):
            if used[i]:
                continue
            best_j = None
            for j in range(i + 1, len(nodes)):
                if used[j]:
                    continue
                bottom = nodes[j]
                if bottom.center_y <= top.center_y:
                    continue
                gap = bottom.bounds[1] - top.bounds[3]
                if gap < -2 or gap > max_gap:
                    continue
                if abs(top.center_x - bottom.center_x) > 40:
                    continue
                if not any(marker in bottom.text for marker in gift_markers):
                    continue
                best_j = j
                break

            if best_j is None:
                merged.append(top)
                used[i] = True
                continue

            bottom = nodes[best_j]
            combined_text = f"{top.text}：{bottom.text}"
            bounds = (
                min(top.bounds[0], bottom.bounds[0]),
                min(top.bounds[1], bottom.bounds[1]),
                max(top.bounds[2], bottom.bounds[2]),
                max(top.bounds[3], bottom.bounds[3]),
            )
            merged.append(TextNode(text=combined_text, bounds=bounds))
            used[i] = True
            used[best_j] = True

        for i, node in enumerate(nodes):
            if not used[i]:
                merged.append(node)

        return merged

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

        ordered = sorted(candidates, key=lambda item: (item.center_y, item.center_x))
        inline_merged = self._merge_inline_nodes(ordered)
        return self._merge_stacked_gift_nodes(inline_merged)

    def _extract_new_lines_by_spatial(
        self, current_nodes: list[TextNode], now_ts: float
    ) -> tuple[list[TextNode], list[TextNode]]:
        new_nodes: list[TextNode] = []
        repeated_nodes: list[TextNode] = []

        for node in current_nodes:
            text = node.text
            current_y = node.center_y
            history = self.state.recent_items.get(text, [])

            appears_lower = bool(history) and current_y > max(record["y"] for record in history) + self.y_tolerance

            if not history or appears_lower:
                new_nodes.append(node)
            else:
                repeated_nodes.append(node)

            updated_history = history + [{"y": current_y, "ts": now_ts}]
            self.state.recent_items[text] = updated_history[-20:]

        return new_nodes, repeated_nodes

    def collect(self, device) -> Frame:
        now_ts = time.time()
        self._cleanup(now_ts)

        current_nodes = self._collect_textview_nodes(device)
        raw_lines = [node.text for node in current_nodes]
        real_new_nodes, repeated_nodes = self._extract_new_lines_by_spatial(current_nodes, now_ts)
        real_new_lines = [node.text for node in real_new_nodes]
        gift_lines: list[str] | None = None
        gift_repeated_lines: list[str] | None = None
        gift_log_lines: list[dict[str, object]] | None = None
        gift_repeated_log_lines: list[dict[str, object]] | None = None
        if self.gift_region:
            gift_nodes = [node for node in real_new_nodes if self._in_region(node.bounds, self.gift_region)]
            repeated_gift_nodes = [node for node in repeated_nodes if self._in_region(node.bounds, self.gift_region)]
            gift_lines = [node.text for node in gift_nodes]
            gift_repeated_lines = [node.text for node in repeated_gift_nodes]
            gift_log_lines = [
                {
                    "ts": now_ts,
                    "text": node.text,
                    "bounds": node.bounds,
                    "center": (round(node.center_x, 1), round(node.center_y, 1)),
                }
                for node in gift_nodes
            ]
            gift_repeated_log_lines = [
                {
                    "ts": now_ts,
                    "text": node.text,
                    "bounds": node.bounds,
                    "center": (round(node.center_x, 1), round(node.center_y, 1)),
                }
                for node in repeated_gift_nodes
            ]
        return Frame(
            ts=now_ts,
            raw_lines=raw_lines,
            lines=real_new_lines,
            gift_lines=gift_lines,
            gift_repeated_lines=gift_repeated_lines,
            gift_log_lines=gift_log_lines,
            gift_repeated_log_lines=gift_repeated_log_lines,
        )
