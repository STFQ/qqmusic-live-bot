FEATURE_FLAGS = {
    "enable_welcome": True,
    "enable_gift_thanks": True,
    "enable_auto_reply": False,
    "enable_warmup": False,
    "enable_pk_remind": True,
    "enable_ocr_fallback": False,
}

# LIMITS = {
#     "main_loop_interval": 0.35,
#     "welcome_interval": 1.2,
#     "gift_thank_interval": 3.0,
#     "chat_reply_interval": 10.0,
#     "warmup_interval": 45.0,
#     "post_send_cooldown": 1.0,
#     "dedupe_ttl": 120.0,
#     "collector_line_ttl": 8.0,
#     "ocr_interval": 3.0,
#     "ocr_trigger_line_count": 2.0,
#     "gift_merge_window": 4.0,
# }

LIMITS = {
    "main_loop_interval": 0.2,  # 【极致抓取】0.2秒看一次屏幕，比眨眼还快
    "welcome_interval": 1.0,
    "gift_thank_interval": 2.0,
    "chat_reply_interval": 10.0,
    "warmup_interval": 45.0,

    "post_send_cooldown": 0.1,  # 【取消发送冷却】原来是1.0秒，现在只要打字发出去，0.1秒后立刻发下一条！
    "dedupe_ttl": 120.0,
    "collector_line_ttl": 8.0,
    "ocr_interval": 3.0,
    "ocr_trigger_line_count": 2.0,

    "gift_merge_window": 0.5,  # 【取消礼物等待】看到礼物只等 0.5 秒，没连击就瞬间感谢！(副作用是如果他连点10下，机器人可能会感谢10次)
}

TRIGGERS = {
    "names": ["Cavalier", "@Cavalier", "骑士", "小骑士"],
    "keywords": ["主播", "点歌", "在吗", "人呢", "陪我", "唱歌", "整活", "?", "？"],
}

PK_RULES = {
    "item_remind_at": 250,
    "final_remind_at": 30,
    "reset_at": 280,
}

SENDER_RULES = {
    "send_prepare_delay": 0.12,
    "send_after_set_delay": 0.10,
    "send_after_send_delay": 0.10,
    "verify_retry": 2,
}


