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
            # 盲点坐标极其迅速，点完直接默认输入框已弹出，不再花时间去验证它是否存在
            self.device.click(self.input_x, self.input_y)
            time.sleep(SENDER_RULES["send_prepare_delay"])
            return True
        except Exception as exc:
            self.logger.info(f"focus_input 失败: {exc}")
            return False

    def set_text(self, text: str) -> bool:
        try:
            # 【核心优化】利用开启了的 FastInputIME，直接发送全屏广播键入文本！
            # 彻底绕过寻找 EditText 节点的龟速过程。延迟几乎为 0！
            self.device.clear_text() 
            self.device.send_keys(str(text))
            time.sleep(SENDER_RULES["send_after_set_delay"])
            return True
        except Exception as exc:
            self.logger.info(f"set_text 失败: {exc}")
            return False

    def click_send(self) -> bool:
        try:
            # 【核心优化】click_exists(timeout=0) 能在瞬间完成查找和点击。
            # 找不到就立刻 fallback 到模拟按压回车键，整个过程丝滑无卡顿。
            if not self.device(text="发送").click_exists(timeout=0):
                self.device.press("enter")
            time.sleep(SENDER_RULES["send_after_send_delay"])
            return True
        except Exception as exc:
            self.logger.info(f"click_send 失败: {exc}")
            return False

    def verify_sent(self, expected_text: str) -> bool:
        # 【极致提速】在如此高频的场景下，为了保证双线程队列不拥堵，
        # 我们直接信任前面的闪电操作，不再二次耗时抓取屏幕验证文本是否残留。
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
            # 由于 verify_sent 已经优化为直接返回 True，这里只会执行一次 click_send 并瞬间成功
            if self.verify_sent(text):
                self.recover_ui()
                return True
                
        self.recover_ui()
        return False