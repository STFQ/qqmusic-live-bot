from __future__ import annotations

from pathlib import Path

from ..strategy.filters import normalize_text


class OCRFallback:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._engine = None
        self._ready = False
        if enabled:
            self._ready = self._bootstrap()

    def _bootstrap(self) -> bool:
        try:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
            return True
        except Exception:
            return False

    def available(self) -> bool:
        return self.enabled and self._ready and self._engine is not None

    def scan(self, image_path: Path) -> list[str]:
        if not self.available():
            return []
        try:
            result = self._engine.ocr(str(image_path), cls=False)
        except Exception:
            return []

        lines: list[str] = []
        if result and result[0]:
            for item in result[0]:
                text = normalize_text(item[1][0])
                if len(text) > 1:
                    lines.append(text)
        return lines
