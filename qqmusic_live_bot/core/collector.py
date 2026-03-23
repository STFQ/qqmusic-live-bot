from __future__ import annotations

import tempfile
import time
import difflib  # [新增] 引入核心比对算法库
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
    "赠 给",
    "赠给",
)


@dataclass
class TextNode:
    text: str
    bounds: tuple[int, int, int, int]


@dataclass
class CollectorState:
    # [修改] 彻底删除 recent_lines (TTL缓存)，换成 last_screen_sequence
    last_screen_sequence: list[str]
    last_ocr_at: float = 0.0


class TextCollector:
    def __init__(
            self,
            line_ttl: float = 8.0,  # 这里的参数保留是为了兼容外部调用，但内部已弃用
            ocr_interval: float = 3.0,
            ocr_trigger_line_count: int = 2,
            enable_ocr_fallback: bool = False,
    ):
        self.ocr_interval = ocr_interval
        self.ocr_trigger_line_count = ocr_trigger_line_count
        # [修改] 初始化全新的记忆状态
        self.state = CollectorState(last_screen_sequence=[])
        self.ocr = OCRFallback(enabled=enable_ocr_fallback)

    # [删除] 彻底移除了 _cleanup(self, now_ts) 函数，再也不需要去管过期时间了！

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

        return self._merge_row_nodes(candidates)

    def _collect_ocr_lines(self, device, now_ts: float) -> list[str]:
        if not self.ocr.available():
            return []
        if now_ts - self.state.last_ocr_at < self.ocr_interval:
            return []

        try:
            image = device.screenshot()
            img_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            lines = self.ocr.scan_image(img_array)
            self.state.last_ocr_at = now_ts
            return lines
        except Exception:
            return []

    # 🔪 [新增] 降维打击：提取全新弹幕的核心算法
    def _extract_new_lines(self, current_sequence: list[str]) -> list[str]:
        """使用滑动窗口序列比对，抛弃死板的 TTL"""
        if not self.state.last_screen_sequence:
            self.state.last_screen_sequence = current_sequence
            return current_sequence

        # 寻找与上一帧画面的差异
        sm = difflib.SequenceMatcher(None, self.state.last_screen_sequence, current_sequence)
        new_items = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            # 只有新增(insert)或替换(replace)的部分，才是刚滚出或者新刷出来的弹幕
            if tag in ('insert', 'replace'):
                new_items.extend(current_sequence[j1:j2])

        # 更新记忆，为下一帧做准备
        self.state.last_screen_sequence = current_sequence
        return new_items

    def collect(self, device) -> Frame:
        now_ts = time.time()

        # 1. 抓取屏幕上的所有文字（按从上到下顺序排好）
        raw_lines = self._collect_textview_lines(device)
        if len(raw_lines) <= self.ocr_trigger_line_count:
            raw_lines.extend(self._collect_ocr_lines(device, now_ts))

        # 2. 帧内简单去重，保持物理顺序
        current_frame_lines: list[str] = []
        seen: set[str] = set()
        for line in raw_lines:
            if line in seen:
                continue
            seen.add(line)
            current_frame_lines.append(line)

        # 3. 🔪 核心介入：调用序列比对，过滤出真正的"新内容"
        real_new_lines = self._extract_new_lines(current_frame_lines)

        # 4. 只把真·新内容装进 Frame 往下传！大脑再也不会收到旧弹幕的骚扰了
        return Frame(ts=now_ts, raw_lines=current_frame_lines, lines=real_new_lines)