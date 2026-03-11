import unittest

from qqmusic_live_bot.core.events import EventType, Frame
from qqmusic_live_bot.core.parser import EventParser


class EventParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = EventParser()

    def test_parses_gift_line_from_screenshot_format(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["幽幽留香(清心儿子爵)ᴸ²：送 灌篮高手 X 1[ICON]"],
            lines=["幽幽留香(清心儿子爵)ᴸ²：送 灌篮高手 X 1[ICON]"],
        )

        events = self.parser.parse(frame)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, EventType.GIFT)
        self.assertEqual(events[0].user, "幽幽留香(清心儿子爵)ᴸ²")
        self.assertEqual(events[0].content, "灌篮高手")
        self.assertEqual(events[0].count, 1)

    def test_does_not_treat_normal_send_chat_as_gift(self) -> None:
        frame = Frame(ts=1.0, raw_lines=["散：送你一首歌"], lines=["散：送你一首歌"])

        events = self.parser.parse(frame)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, EventType.CHAT)
        self.assertEqual(events[0].user, "散")
        self.assertEqual(events[0].content, "送你一首歌")


if __name__ == "__main__":
    unittest.main()
