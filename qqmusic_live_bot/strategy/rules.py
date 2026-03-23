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
    # 1. 【眼睛看屏幕的速度】：保持 0.2 ~ 0.3 即可，太快会卡死模拟器
    "main_loop_interval": 0.5,

    # 2. 【大脑塞任务的速度：彻底解除限流！】
    # 把这些原来动辄 1.5、2.5 秒的间隔，全部改成 0.0！
    # 意思是：只要看到有人进来、有人送礼，0毫秒犹豫，瞬间全部砸进队列里让 Sender 去排队发！
    "welcome_interval": 0.0,
    "gift_thank_interval": 0.0,
    "chat_reply_interval": 0.0,

    # 3. 【嘴巴的死板间隔：正式宣告作废】
    # 因为我们在 main.py 里已经把 time.sleep(post_send_cooldown) 删掉了，全靠 ACK 回执。
    # 这里改成 0.0 只是为了让配置表看起来名副其实。
    "post_send_cooldown": 0.0,

    # 4. 【唯一需要保留的防刷屏保护】
    # 等待大哥连击的时间。如果你觉得 4.0 秒太久，可以改成 1.0 或 1.5。
    # 意思是：看到礼物先憋 1.5 秒，1.5 秒后大哥没连击了，再瞬间扔进队列感谢。
    "gift_merge_window": 0.5,

    # ... 其他的参数保持你原来的不变即可
    "dedupe_ttl": 120.0,
    "collector_line_ttl": 8.0,
    "ocr_interval": 3.0,
    "ocr_trigger_line_count": 2.0,
    "warmup_interval": 45.0
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


