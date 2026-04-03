from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from ..strategy.filters import normalize_text


@dataclass
class OCRTextBox:
    text: str
    bounds: tuple[int, int, int, int]
    score: float


class OCRFallback:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._engine: Any | None = None
        self._ready = False
        if enabled:
            self._ready = self._bootstrap()

    def _bootstrap(self) -> bool:
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
            return True
        except Exception:
            return False

    def available(self) -> bool:
        return self.enabled and self._ready and self._engine is not None

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            gray = image
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Lift translucent overlay text while suppressing the background.
        gray = cv2.convertScaleAbs(gray, alpha=1.25, beta=8)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        binary = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def scan_image(self, image: np.ndarray) -> list[OCRTextBox]:
        if not self.available():
            return []

        try:
            result, _ = self._engine(self._preprocess(image))
        except Exception:
            return []

        boxes: list[OCRTextBox] = []
        for item in result or []:
            points, text, score = item
            cleaned = normalize_text(text)
            if len(cleaned) <= 1:
                continue
            xs = [int(point[0]) for point in points]
            ys = [int(point[1]) for point in points]
            boxes.append(
                OCRTextBox(
                    text=cleaned,
                    bounds=(min(xs), min(ys), max(xs), max(ys)),
                    score=float(score),
                )
            )
        return boxes
