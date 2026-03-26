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

    def test_does_not_treat_position_timer_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位置", "4:19"],
            lines=["排位置", "4:19"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_does_not_treat_blood_pack_timer_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["抢血包", "4:19"],
            lines=["抢血包", "4:19"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_does_not_treat_bomb_timer_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["抢炸弹", "4:19"],
            lines=["抢炸弹", "4:19"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_still_recognizes_real_pk_timer(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["PK倒计时", "0:21"],
            lines=["PK倒计时", "0:21"],
        )

        events = self.parser.parse(frame)

        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        self.assertEqual(len(pk_events), 1)
        self.assertEqual(pk_events[0].meta["seconds"], 21)

    def test_recognizes_rank_match_timer_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位赛", "4:19"],
            lines=["排位赛", "4:19"],
        )

        events = self.parser.parse(frame)

        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        self.assertEqual(len(pk_events), 1)
        self.assertEqual(pk_events[0].meta["seconds"], 259)

    def test_does_not_pick_bomb_timer_when_pk_text_exists_elsewhere(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位赛", "4:19", "抢炸弹", "0:33"],
            lines=["排位赛", "4:19", "抢炸弹", "0:33"],
        )

        events = self.parser.parse(frame)

        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        self.assertEqual(len(pk_events), 1)
        self.assertEqual(pk_events[0].meta["seconds"], 259)

    def test_does_not_treat_standalone_countdown_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["0:38"],
            lines=["0:38"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_only_immediate_pk_context_can_claim_timer(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位赛", "快乐星球", "0:38"],
            lines=["排位赛", "快乐星球", "0:38"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_does_not_treat_prop_timer_when_time_is_above_label(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["5:00", "抢炸弹"],
            lines=["5:00", "抢炸弹"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_does_not_treat_prop_timer_when_time_is_below_label(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["抢炸弹", "0:59"],
            lines=["抢炸弹", "0:59"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_does_not_treat_item_timer_as_pk(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["抢道具", "0:05"],
            lines=["抢道具", "0:05"],
        )

        events = self.parser.parse(frame)

        self.assertFalse(any(event.type == EventType.PK_TIMER for event in events))

    def test_keeps_pk_timer_but_filters_prop_timer_in_same_frame(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位赛", "5:00", "抢炸弹", "0:59"],
            lines=["排位赛", "5:00", "抢炸弹", "0:59"],
        )

        events = self.parser.parse(frame)

        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        self.assertEqual(len(pk_events), 1)
        self.assertEqual(pk_events[0].meta["seconds"], 300)

    def test_keeps_pk_timer_but_filters_item_timer_in_same_frame(self) -> None:
        frame = Frame(
            ts=1.0,
            raw_lines=["排位赛", "4:06", "抢道具", "0:05"],
            lines=["排位赛", "4:06", "抢道具", "0:05"],
        )

        events = self.parser.parse(frame)

        pk_events = [event for event in events if event.type == EventType.PK_TIMER]
        self.assertEqual(len(pk_events), 1)
        self.assertEqual(pk_events[0].meta["seconds"], 246)


if __name__ == "__main__":
    unittest.main()
