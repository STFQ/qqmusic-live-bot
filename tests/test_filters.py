import unittest

from qqmusic_live_bot.strategy.filters import trim_gift_reply, trim_reply


class TrimReplyTests(unittest.TestCase):
    def test_trim_reply_handles_non_positive_limit(self) -> None:
        self.assertEqual(trim_reply("hello", 0), "")

    def test_trim_gift_reply_keeps_gift_visible(self) -> None:
        text = trim_gift_reply("特别特别长的用户名", "超级火箭", 18)

        self.assertLessEqual(len(text), 18)
        self.assertTrue(text.startswith("感谢 @"))
        self.assertIn("超级火箭", text)

    def test_trim_gift_reply_keeps_count_suffix(self) -> None:
        text = trim_gift_reply("阿", "银河战舰 x12", 12)

        self.assertLessEqual(len(text), 12)
        self.assertTrue(text.endswith("x12"))


if __name__ == "__main__":
    unittest.main()
