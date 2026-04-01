from __future__ import annotations

import time


class MessageSender:
    def __init__(
        self,
        device,
        input_x: int,
        input_y: int,
        logger,
        dry_run: bool = True,
        log_dry_run: bool = True,
        send_x: float | None = None,
        send_y: float | None = None,
        fallback_send_x: float | None = None,
        fallback_send_y: float | None = None,
    ):
        self.device = device
        self.input_x = input_x
        self.input_y = input_y
        self.logger = logger
        self.dry_run = dry_run
        self.log_dry_run = log_dry_run
        self.send_x = send_x
        self.send_y = send_y
        self.fallback_send_x = fallback_send_x
        self.fallback_send_y = fallback_send_y

    def focus_input(self) -> bool:
        try:
            # 盲点坐标唤起输入框
            self.device.click(self.input_x, self.input_y)
            # 唤起输入法确实需要一点点物理时间，给个极短的 0.1s 缓冲
            time.sleep(0.1)
            return True
        except Exception as exc:
            self.logger.info(f"focus_input 失败: {exc}")
            return False

    def send_message(self, text: str) -> bool:
        if not text:
            return False

        if self.dry_run:
            if self.log_dry_run:
                self.logger.info(f"[DRY_RUN] {text}")
            return True

        try:
            # 1. 点击唤起输入法
            if not self.focus_input():
                return False

            # 2. 极速注入文本
            self.device.clear_text()
            self.device.send_keys(str(text))

            # 3. 触发发送：优先点击发送按钮坐标，避免 adbkeyboard 二次触发
            ack_success = self._try_send_with_coords(self.send_x, self.send_y, text)

            # 兜底坐标：首次失败时再尝试一次
            if not ack_success and self.fallback_send_x is not None and self.fallback_send_y is not None:
                ack_success = self._try_send_with_coords(self.fallback_send_x, self.fallback_send_y, text)

            if ack_success:
                # 回执拿到！立刻收尾！
                return True
            else:
                self.logger.warning(f"发送超时，未收到文本消失回执: {text}")
                return False

        except Exception as exc:
            self.logger.warning(f"send_message 异常: {exc}")
            return False

    def _try_send_with_coords(self, send_x: float | None, send_y: float | None, text: str) -> bool:
        if send_x is not None and send_y is not None:
            self.device.click(int(send_x), int(send_y))
        else:
            self.device.shell("input keyevent 66")

        # 【核心灵魂：ACK 动态回执锁】
        # 输入框消失/清空/文本变化都算成功，避免误判导致重发。
        start_ts = time.time()
        while time.time() - start_ts < 0.6:
            current_text = self._read_input_text()
            if current_text is None or current_text == "" or current_text != text:
                return True
            time.sleep(0.12)
        return False

    def _read_input_text(self) -> str | None:
        try:
            widget = self.device(className="android.widget.EditText")
            if not widget.exists:
                return None
            return widget.get_text()
        except Exception:
            return None

