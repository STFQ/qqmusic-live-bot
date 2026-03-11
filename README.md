# QQMusic Live Bot

一个从原工作区中抽离出来的独立项目，用于在 QQ 音乐直播间里做基础自动互动。

当前默认保留的功能：
- 入场欢迎
- 送礼感谢
- PK 道具提醒
- PK 最后 30 秒提醒

当前默认关闭的功能：
- 自动聊天回复
- 暖场消息
- OCR 回退

## 目录结构

```text
qqmusic_live_bot_standalone/
|- run_v1_bot.py
|- requirements.txt
|- .gitignore
|- qqmusic_live_bot/
|  |- main.py
|  |- config.py
|  |- core/
|  |- features/
|  |- services/
|  |- strategy/
|  `- data/
|     |- config.json
|     |- blacklist.json
|     |- memory.json
|     `- logs/
```

## 运行环境

- Windows
- Python 3.10+
- 已安装并可用的 ADB / Android 模拟器
- QQ 音乐直播间已经打开在目标设备上

## 安装

在项目根目录执行：

```powershell
python -m venv .env
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.env\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

如果你后面要开启 OCR 回退，再额外安装：

```powershell
pip install paddleocr
```

## 启动方式

不要直接运行 `qqmusic_live_bot/main.py`。

正确启动：

```powershell
python run_v1_bot.py
```

或者：

```powershell
python -m qqmusic_live_bot.main
```

## 配置说明

主要配置文件：
- `qqmusic_live_bot/data/config.json`

关键配置项：

```json
{
  "device_addr": "127.0.0.1:5555",
  "input_box_x": 159,
  "input_box_y": 1418,
  "dry_run": true,
  "logging": {
    "console_output": false,
    "pk_time": false,
    "dry_run": false
  }
}
```

说明：
- `device_addr`: Android 设备地址
- `input_box_x` / `input_box_y`: 直播间输入框点击坐标
- `dry_run`: `true` 为只模拟发送，`false` 为真实发送
- `logging.console_output`: 是否把运行日志打印到控制台
- `logging.pk_time`: 是否打印 PK 倒计时调试日志
- `logging.dry_run`: 在 `dry_run=true` 时是否打印待发送内容

## 当前默认行为

`flags` 当前默认如下：

```json
{
  "enable_welcome": true,
  "enable_gift_thanks": true,
  "enable_auto_reply": false,
  "enable_warmup": false,
  "enable_pk_remind": true,
  "enable_ocr_fallback": false
}
```

消息模板当前为最简版：
- 欢迎：`欢迎 {用户名}`
- 感谢送礼：`感谢 @{用户名} {礼物名}`
- PK 抢道具：`快抢道具`
- PK 最后提醒：`最后30秒，快上分`

## 日志文件

运行日志默认会写入：
- `qqmusic_live_bot/data/logs/run_YYYYMMDD.log`
- `qqmusic_live_bot/data/logs/events_YYYYMMDD.jsonl`

即使关闭控制台输出，文件日志仍然会保留，方便排查问题。

## 坐标调整

如果机器人没点到输入框，优先修改：
- `qqmusic_live_bot/data/config.json` 里的 `input_box_x`
- `qqmusic_live_bot/data/config.json` 里的 `input_box_y`

发送按钮本身不是固定坐标：
- 程序会优先查找文字为 `发送` 的按钮
- 如果没找到，就退回到按回车发送

## 注意事项

- 首次连接设备时，`uiautomator2` 可能会往设备里安装辅助 APK，这通常是正常现象。
- 如果 `config.json` 带 UTF-8 BOM，本项目已经兼容读取。
- 如果你要真实发送消息，记得把 `dry_run` 改成 `false`。

## 初始化 GitHub 私有仓库

如果本机已经安装并登录了 `git` 和 `gh`，可在本项目目录执行：

```powershell
git init
git add .
git commit -m "Initial commit"
gh repo create qqmusic-live-bot --private --source . --remote origin --push
```

如果 `git` 或 `gh` 不在 PATH，先安装 Git 与 GitHub CLI，或者把它们加入 PATH 后再执行。
