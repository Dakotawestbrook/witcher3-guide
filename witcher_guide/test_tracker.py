import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path

from witcher_guide import core, tracker


def feed_all(tr, lines):
    return [tr.feed(l) for l in lines]


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = core.load_data()
        self.progress = core.Progress(Path(self.tmp.name) / "p.json")
        self.tr = tracker.Tracker(self.progress, self.data)

    def test_parse_line_ignores_prefix_noise_and_junk(self):
        self.assertEqual(tracker.parse_line("[12:01] [modWG] @@WG@@|q|Royal Audience|success"),
                         ("q", "Royal Audience", "success"))
        self.assertEqual(tracker.parse_line("@@WG@@|snapshot|BEGIN"), ("snapshot", "begin"))
        self.assertEqual(tracker.parse_line("@@WG@@|tracked|Ugly Baby"), ("tracked", "Ugly Baby"))
        self.assertEqual(tracker.parse_line("@@WG@@|tracked|"), ("tracked", ""))
        for junk in ("nothing here", "@@WG@@|q|only two", "@@WG@@|snapshot|middle", "@@WG@@|bogus|x|y"):
            self.assertIsNone(tracker.parse_line(junk), junk)

    def test_matching_titles(self):
        m = tracker.Matcher(self.data, tracker.load_aliases())
        self.assertEqual(m.match("Royal Audience"), ["imperial"])          # alias
        self.assertEqual(m.match("Imperial Audience"), ["imperial"])
        self.assertEqual(m.match("The King is Dead, Long Live the King"), ["king"])
        self.assertEqual(sorted(m.match("Family Matters")), ["family1", "family2"])  # split quest
        self.assertEqual(m.match("Va Fail Elaine"), ["vafail"])
        self.assertEqual(m.match("Not A Real Quest"), [])

    def test_incremental_success_marks_done_and_persists(self):
        self.assertEqual(self.tr.feed("@@WG@@|q|Lilac and Gooseberries|success"), "progress")
        self.assertIn("lilac", self.progress.all_done())
        self.assertIn("lilac", core.Progress(self.progress.path).auto_done)
        self.assertIsNone(self.tr.feed("@@WG@@|q|Lilac and Gooseberries|success"))  # no change

    def test_failed_quest_shows_missed(self):
        self.tr.feed("@@WG@@|q|Missing in Action|failed")
        by = {q["id"]: q for q in core.annotate(self.data, self.progress.all_done(), self.progress.auto_failed)}
        self.assertEqual(by["missing_in_action"]["status"], core.MISSED)

    def test_active_state_changes_nothing(self):
        self.assertIsNone(self.tr.feed("@@WG@@|q|Lilac and Gooseberries|active"))
        self.assertEqual(self.progress.all_done(), set())

    def test_snapshot_replaces_auto_state_so_old_saves_correct_it(self):
        feed_all(self.tr, ["@@WG@@|snapshot|begin", "@@WG@@|q|Lilac and Gooseberries|success",
                           "@@WG@@|q|The Beast of White Orchard|success", "@@WG@@|snapshot|end"])
        self.assertEqual(self.progress.auto_done, {"lilac", "beast"})
        # Player loads an earlier save: only Lilac is finished.
        feed_all(self.tr, ["@@WG@@|snapshot|begin", "@@WG@@|q|Lilac and Gooseberries|success",
                           "@@WG@@|q|The Beast of White Orchard|active", "@@WG@@|snapshot|end"])
        self.assertEqual(self.progress.auto_done, {"lilac"})

    def test_snapshot_is_atomic_until_end(self):
        self.tr.feed("@@WG@@|snapshot|begin")
        self.tr.feed("@@WG@@|q|Lilac and Gooseberries|success")
        self.assertEqual(self.progress.auto_done, set())  # not applied until 'end'
        self.assertEqual(self.tr.feed("@@WG@@|snapshot|end"), "progress")
        self.assertEqual(self.progress.auto_done, {"lilac"})

    def test_empty_snapshot_never_wipes_progress(self):
        self.tr.feed("@@WG@@|q|Lilac and Gooseberries|success")
        feed_all(self.tr, ["@@WG@@|snapshot|begin", "@@WG@@|snapshot|end"])  # journal not loaded yet
        self.assertEqual(self.progress.auto_done, {"lilac"})
        # but a real snapshot with only unfinished quests (earlier save) does reset it
        feed_all(self.tr, ["@@WG@@|snapshot|begin", "@@WG@@|q|Lilac and Gooseberries|active", "@@WG@@|snapshot|end"])
        self.assertEqual(self.progress.auto_done, set())

    def test_manual_ticks_survive_snapshots(self):
        self.progress.toggle("gear_cat")  # an item the game journal doesn't report
        feed_all(self.tr, ["@@WG@@|snapshot|begin", "@@WG@@|snapshot|end"])
        self.assertIn("gear_cat", self.progress.all_done())

    def test_untick_overrides_automatic_completion(self):
        self.tr.feed("@@WG@@|q|Lilac and Gooseberries|success")
        self.assertFalse(self.progress.toggle("lilac"))
        self.assertNotIn("lilac", self.progress.all_done())

    def test_tracked_quest(self):
        self.assertEqual(self.tr.feed("@@WG@@|tracked|Ugly Baby"), "tracked")
        self.assertEqual(self.progress.tracked, "ugly")
        self.assertIsNone(self.tr.feed("@@WG@@|tracked|Ugly Baby"))
        self.assertEqual(self.tr.feed("@@WG@@|tracked|"), "tracked")
        self.assertIsNone(self.progress.tracked)

    def test_tracked_all_holds_every_matching_id(self):
        self.tr.feed("@@WG@@|tracked|Family Matters")  # one game quest, two entries here
        self.assertEqual(self.progress.tracked_all, {"family1", "family2"})
        self.tr.feed("@@WG@@|tracked|")
        self.assertEqual(self.progress.tracked_all, set())

    def test_unmatched_titles_are_recorded_for_the_user(self):
        self.tr.feed("@@WG@@|q|Some Brand New Quest|success")
        out = (self.progress.path.parent / "unmatched_quests.txt").read_text()
        self.assertIn("Some Brand New Quest", out)

    def test_old_progress_format_still_loads(self):
        p = Path(self.tmp.name) / "old.json"
        p.write_text(json.dumps(["lilac", "beast"]))
        self.assertEqual(core.Progress(p).done, {"lilac", "beast"})


class TestTailer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "scriptlog.txt"

    def test_reads_only_new_complete_prefixed_lines(self):
        t = tracker.LogTailer(self.path)
        self.assertEqual(t.read_new_lines(), [])  # file missing
        self.path.write_bytes(b"noise\n@@WG@@|q|A|success\n@@WG@@|q|B|succ")
        self.assertEqual(t.read_new_lines(), ["@@WG@@|q|A|success"])  # partial line held back
        with open(self.path, "ab") as f:
            f.write(b"ess\r\nmore noise\n")
        self.assertEqual(t.read_new_lines(), ["@@WG@@|q|B|success"])
        self.assertEqual(t.read_new_lines(), [])

    def test_restart_truncation_is_detected(self):
        t = tracker.LogTailer(self.path)
        self.path.write_bytes(b"@@WG@@|q|A|success\n" * 5)
        t.read_new_lines()
        self.path.write_bytes(b"@@WG@@|q|B|success\n")  # game relaunched: shorter file
        self.assertEqual(t.read_new_lines(), ["@@WG@@|q|B|success"])

    def test_find_log_prefers_newest_existing(self):
        a, b = Path(self.tmp.name) / "a.txt", Path(self.tmp.name) / "b.txt"
        self.assertIsNone(tracker.find_log([a, b]))
        a.write_text("x"); time.sleep(0.02); b.write_text("y")
        self.assertEqual(tracker.find_log([a, b]), b)

    def test_background_watcher_posts_lines(self):
        self.path.write_text("@@WG@@|q|A|success\n")
        events = queue.Queue()
        stop = tracker.start_tracking(events, [self.path], interval=0.01)
        try:
            kind, lines = events.get(timeout=2)
            self.assertEqual((kind, lines), ("lines", ["@@WG@@|q|A|success"]))
        finally:
            stop.set()


if __name__ == "__main__":
    unittest.main()
