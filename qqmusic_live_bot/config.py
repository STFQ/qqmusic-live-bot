from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .strategy.persona import BOT_PROFILE
from .strategy.rules import FEATURE_FLAGS, LIMITS


DEFAULT_LOGGING = {
    "console_output": True,  # 建议控制台输出开着，不然你不知道机器人在干嘛
    "file_output": False,    # 🔪 [新增] 默认不把日志写到硬盘里
    "pk_time": False,
    "dry_run": False,
}


@dataclass
class RuntimeConfig:
    device_addr: str = "127.0.0.1:7555"
    input_box_x: int = 159
    input_box_y: int = 1418
    dry_run: bool = True
    mode: str = "auto"
    profile: dict[str, Any] = field(default_factory=lambda: dict(BOT_PROFILE))
    flags: dict[str, bool] = field(default_factory=lambda: dict(FEATURE_FLAGS))
    limits: dict[str, float] = field(default_factory=lambda: dict(LIMITS))
    logging: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_LOGGING))


DEFAULT_CONFIG = {
    "device_addr": "127.0.0.1:5565",
    "input_box_x": 174,
    "input_box_y": 2649,
    "dry_run": False,
    "mode": "auto",
    "profile": BOT_PROFILE,
    "flags": FEATURE_FLAGS,
    "limits": LIMITS,
    "logging": DEFAULT_LOGGING,
}


def load_runtime_config(root: Path) -> RuntimeConfig:
    config_path = root / "data" / "config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        data = DEFAULT_CONFIG
    else:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))

    return RuntimeConfig(
        device_addr=data.get("device_addr", DEFAULT_CONFIG["device_addr"]),
        input_box_x=int(data.get("input_box_x", DEFAULT_CONFIG["input_box_x"])),
        input_box_y=int(data.get("input_box_y", DEFAULT_CONFIG["input_box_y"])),
        dry_run=bool(data.get("dry_run", DEFAULT_CONFIG["dry_run"])),
        mode=data.get("mode", DEFAULT_CONFIG["mode"]),
        profile={**BOT_PROFILE, **data.get("profile", {})},
        flags={**FEATURE_FLAGS, **data.get("flags", {})},
        limits={**LIMITS, **data.get("limits", {})},
        logging={**DEFAULT_LOGGING, **data.get("logging", {})},
    )
