from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .events import Frame
from .ocr import OCRFallback
from ..strategy.filters import normalize_text

import cv2
import numpy as np

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
)


@dataclass
class TextNode:
    text: str
    bounds: tuple[int, int, int, int]


@dataclass
class CollectorState:
    recent_lines: dict[str, float]
    last_ocr_at: float = 0.0


class TextCollector:
    def __init__(
        self,
        line_ttl: float = 8.0,
        ocr_interval: float = 3.0,
        ocr_trigger_line_count: int = 2,
        enable_ocr_fallback: bool = False,
    ):
        self.line_ttl = line_ttl
        self.ocr_interval = ocr_interval
        self.ocr_trigger_line_count = ocr_trigger_line_count
        self.state = CollectorState(recent_lines={})
        self.ocr = OCRFallback(enabled=enable_ocr_fallback)

    def _cleanup(self, now_ts: float) -> None:
        self.state.recent_lines = {
            key: ts for key, ts in self.state.recent_lines.items() if now_ts - ts < self.line_ttl
        }

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

    def _merge_row_nodes(self, nodes: list[TextNode]) -> list[str]:
        if not nodes:
            return []

        ordered_nodes = sorted(nodes, key=lambda item: ((item.bounds[1] + item.bounds[3]) / 2, item.bounds[0]))
        row_tolerance = 24
        rows: list[list[TextNode]] = []

        for node in ordered_nodes:
            center_y = (node.bounds[1] + node.bounds[3]) / 2
            if not rows:
                rows.append([node])
                continue

            last_row = rows[-1]
            last_center_y = (last_row[-1].bounds[1] + last_row[-1].bounds[3]) / 2
            if abs(center_y - last_center_y) <= row_tolerance:
                last_row.append(node)
            else:
                rows.append([node])

        lines: list[str] = []
        group_gap = 80
        for row in rows:
            row = sorted(row, key=lambda item: item.bounds[0])
            texts = [item.text for item in row if item.text and not self._is_noise_text(item.text)]
            if not texts:
                continue
            lines.extend(texts)

            groups: list[list[TextNode]] = []
            for item in row:
                if not item.text or self._is_noise_text(item.text):
                    continue
                if not groups:
                    groups.append([item])
                    continue
                last_item = groups[-1][-1]
                gap = item.bounds[0] - last_item.bounds[2]
                if gap <= group_gap:
                    groups[-1].append(item)
                else:
                    groups.append([item])

            for group in groups:
                if len(group) <= 1:
                    continue
                group_texts = [item.text for item in group if item.text and not self._is_noise_text(item.text)]
                if len(group_texts) <= 1:
                    continue
                joined = " ".join(group_texts)
                compact = "".join(group_texts)
                if not self._is_noise_text(joined):
                    lines.append(joined)
                if compact != joined and not self._is_noise_text(compact):
                    lines.append(compact)
        return [line for line in lines if line]

    def _collect_textview_lines(self, device) -> list[str]:
        window_size = self._device_window_size(device)
        nodes = device.xpath("//android.widget.TextView").all()
        candidates: list[TextNode] = []

        for node in nodes:
            text = normalize_text(getattr(node, "text", ""))
            if not text or self._is_noise_text(text):
                continue
            bounds = getattr(node, "bounds", (0, 0, 0, 0))
            if not self._in_live_region(bounds, window_size):
                continue
            candidates.append(TextNode(text=text, bounds=bounds))

        return self._merge_row_nodes(candidates)

    def _collect_ocr_lines(self, device, now_ts: float) -> list[str]:
        if not self.ocr.available():
            return []
        if now_ts - self.state.last_ocr_at < self.ocr_interval:
            return []
        
        try:
            # 直接获取内存中的 PIL Image 或 bytes，不落盘（具体取决于你的 device 库，如 uiautomator2）
            image = device.screenshot() 
            # 将 PIL Image 转换为 numpy 数组供 PaddleOCR 直接读取
            img_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # ocr.scan 也需要相应修改，接收 numpy array 而不是路径
            lines = self.ocr.scan_image(img_array) 
            self.state.last_ocr_at = now_ts
            return lines
        except Exception:
            return []

    def collect(self, device) -> Frame:
        now_ts = time.time()
        self._cleanup(now_ts)
        raw_lines = self._collect_textview_lines(device)
        if len(raw_lines) <= self.ocr_trigger_line_count:
            raw_lines.extend(self._collect_ocr_lines(device, now_ts))

        frame_lines: list[str] = []
        seen: set[str] = set()
        for line in raw_lines:
            if line in seen:
                continue
            seen.add(line)
            frame_lines.append(line)
            self.state.recent_lines[line] = now_ts

        return Frame(ts=now_ts, raw_lines=raw_lines, lines=frame_lines)
