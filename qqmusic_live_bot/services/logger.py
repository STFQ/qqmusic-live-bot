from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class BotLogger:
    def __init__(self, log_dir: Path, console_output: bool = True, file_output: bool = False):
        self.log_dir = log_dir
        self.console_output = console_output
        self.file_output = file_output

        if self.file_output:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_name = time.strftime("%Y%m%d")
            self.text_log = self.log_dir / f"run_{date_name}.log"
            self.json_log = self.log_dir / f"events_{date_name}.jsonl"
            self.gift_lines_log = self.log_dir / f"gift_lines_{date_name}.jsonl"

    def info(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        if self.console_output:
            print(line)
        if self.file_output:
            with self.text_log.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def warning(self, message: str) -> None:
        self.info(f"[WARN] {message}")

    def event(self, payload: dict[str, Any]) -> None:
        if self.file_output:
            with self.json_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def gift_lines(self, payload: dict[str, Any]) -> None:
        if self.file_output:
            with self.gift_lines_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")