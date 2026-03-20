from __future__ import annotations

import time


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
                self.recover_ui()
                return False

            # 2. 极速注入文本
            self.device.clear_text()
            self.device.send_keys(str(text))

            # 3. 触发发送 (优先点发送，找不到就秒敲回车)
            if not self.device(text="发送").click_exists(timeout=0):
                self.device.press("enter")

            # 4. 【核心灵魂：ACK 动态回执锁】
            # 我们告诉 uiautomator2：死死盯住那个里面装着我们刚才发的话的输入框。
            # 最多盯 1.5 秒。只要它消失了（或者被清空了），说明 QQ音乐 已经成功把消息发出来了！
            # 这一步的耗时完全取决于你手机当时的流畅度，可能是 0.05 秒，也可能是 0.8 秒。
            ack_success = self.device(className="android.widget.EditText", text=text).wait_gone(timeout=1.5)

            if ack_success:
                # 回执拿到！立刻收尾！
                self.recover_ui()
                return True
            else:
                self.logger.warning(f"发送超时，未收到文本消失回执: {text}")
                self.recover_ui()
                return False

        except Exception as exc:
            self.logger.warning(f"send_message 异常: {exc}")
            self.recover_ui()
            return False

    # def recover_ui(self) -> None:
    #     try:
    #         width, height = self.device.window_size()
    #         # self.device.click(width * 0.9, height * 0.8)
    #         # 收起键盘后极其短暂的缓冲，确保下一条盲点不会点歪
    #         time.sleep(0.05)
    #     except Exception:
    #         return