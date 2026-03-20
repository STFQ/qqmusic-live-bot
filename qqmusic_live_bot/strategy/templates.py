from __future__ import annotations

import random

WELCOME_TEMPLATES = [
    "欢迎 {user}",
]

GIFT_TEMPLATES = [
    "谢谢 @{user} {gift}",
]

CHAT_REPLY_TEMPLATES = [
    "你这句有点东西",
    "别说，还真像那么回事",
    "这梗我先收下了",
    "今天状态挺在线啊",
    "笑死，谁教你这么说的",
    "这句接得漂亮",
]

CHAT_QUESTION_TEMPLATES = [
    "这题我先站你这边",
    "你这个问题有点会问",
    "这句我听进去了",
]

WARMUP_TEMPLATES = [
    "弹幕别停，气氛接上",
    "今天这场状态不错",
    "有想听的直接说",
    "气氛可以，再热一点",
]

PK_ITEM_TEMPLATES = [
    "快抢道具",
]

PK_FINAL_TEMPLATES = [
    "pk快结束了，快上分",
]


def pick(templates: list[str], **kwargs: str) -> str:
    template = random.choice(templates)
    return template.format(**kwargs)
