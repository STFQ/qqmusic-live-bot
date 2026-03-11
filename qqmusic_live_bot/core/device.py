from __future__ import annotations

import uiautomator2 as u2


class DeviceSession:
    def __init__(self, device_addr: str):
        self.device_addr = device_addr

    def connect(self) -> u2.Device:
        device = u2.connect(self.device_addr)
        device.set_fastinput_ime(True)
        return device
