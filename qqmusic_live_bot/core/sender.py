from __future__ import annotations

import time

from ..strategy.rules import SENDER_RULES


class MessageSender:
    def __init__(self, device, input_x: int, input_y: int, logger, dry_run: bool = True, log_dry_run: bool = True):
        self.device = device
        self.input_x = input_x
        self.input_y = input_y
        self.logger = logger
        self.dry_run = dry_run
        self.log_dry_run = log_dry_run

    def focus_input(self) -> bool:
        try:
            self.device.click(self.input_x, self.input_y)
            time.sleep(SENDER_RULES["send_prepare_delay"])
            return self.device(className="android.widget.EditText").exists
        except Exception as exc:
            self.logger.info(f"focus_input 失败: {exc}")
            return False

    def set_text(self, text: str) -> bool:
        try:
            edit = self.device(className="android.widget.EditText")
            if not edit.exists:
                return False
            edit.set_text(str(text))
            time.sleep(SENDER_RULES["send_after_set_delay"])
            return True
        except Exception as exc:
            self.logger.info(f"set_text 失败: {exc}")
            return False

    def click_send(self) -> bool:
        try:
            if self.device(text="发送").exists:
                self.device(text="发送").click()
            else:
                self.device.press("enter")
            time.sleep(SENDER_RULES["send_after_send_delay"])
            return True
        except Exception as exc:
            self.logger.info(f"click_send 失败: {exc}")
            return False

    def verify_sent(self, expected_text: str) -> bool:
        try:
            edit = self.device(className="android.widget.EditText")
            if not edit.exists:
                return True
            info = edit.info if hasattr(edit, "info") else {}
            current_text = info.get("text", "") if isinstance(info, dict) else ""
            return current_text != expected_text
        except Exception:
            return True

    def recover_ui(self) -> None:
        try:
            width, height = self.device.window_size()
            self.device.click(width * 0.5, height * 0.3)
        except Exception:
            return

    def send_message(self, text: str) -> bool:
        if not text:
            return False
        if self.dry_run:
            if self.log_dry_run:
                self.logger.info(f"[DRY_RUN] {text}")
            return True
        if not self.focus_input():
            self.recover_ui()
            return False
        if not self.set_text(text):
            self.recover_ui()
            return False
        for _ in range(SENDER_RULES["verify_retry"]):
            self.click_send()
            if self.verify_sent(text):
                self.recover_ui()
                return True
        self.recover_ui()
        return False
