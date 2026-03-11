FEATURE_FLAGS = {
    "enable_welcome": True,
    "enable_gift_thanks": True,
    "enable_auto_reply": False,
    "enable_warmup": False,
    "enable_pk_remind": True,
    "enable_ocr_fallback": False,
}

LIMITS = {
    "main_loop_interval": 0.35,
    "welcome_interval": 1.2,
    "gift_thank_interval": 3.0,
    "chat_reply_interval": 10.0,
    "warmup_interval": 45.0,
    "post_send_cooldown": 1.0,
    "dedupe_ttl": 120.0,
    "collector_line_ttl": 8.0,
    "ocr_interval": 3.0,
    "ocr_trigger_line_count": 2.0,
    "gift_merge_window": 4.0,
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


