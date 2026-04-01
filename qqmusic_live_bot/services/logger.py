from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class BotLogger:
    def __init__(self, log_dir: Path, console_output: bool = True):
        self.log_dir = log_dir
        self.console_output = console_output
        self.log_dir.mkdir(parents=True, exist_ok=True)
        date_name = time.strftime("%Y%m%d")
        self.text_log = self.log_dir / f"run_{date_name}.log"
        self.json_log = self.log_dir / f"events_{date_name}.jsonl"

    def info(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        if self.console_output:
            print(line)
        with self.text_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def warning(self, message: str) -> None:
        self.info(f"[WARN] {message}")

    def region(self, name: str, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        date_name = time.strftime("%Y%m%d")
        region_log = self.log_dir / f"{name}_{date_name}.log"
        with region_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def event(self, payload: dict[str, Any]) -> None:
        with self.json_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
