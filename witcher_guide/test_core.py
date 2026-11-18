import tempfile
import unittest
from pathlib import Path

from witcher_guide import core


class TestCore(unittest.TestCase):
    def setUp(self):
        self.data = core.load_data()
        self.by_id = {q["id"]: q for q in self.data["quests"]}

    def test_data_integrity(self):
        self.assertEqual(len(self.by_id), len(self.data["quests"]), "duplicate ids")
        for q in self.data["quests"]:
            self.assertIn(q["region"], self.data["regions"], q["id"])
            self.assertTrue(q.get("source"), q["id"])
            for r in q["requires"]:
                self.assertIn(r, self.by_id, q["id"])
            if q.get("expires_before"):
                self.assertIn(q["expires_before"], self.by_id, q["id"])
                self.assertTrue(q.get("missable"), q["id"])
            if q.get("missable"):
                self.assertTrue(q.get("warn"), q["id"])

    def test_no_dependency_cycles(self):
        def walk(i, seen):
            self.assertNotIn(i, seen)
            for r in self.by_id[i]["requires"]:
                walk(r, seen | {i})
        for i in self.by_id:
            walk(i, set())

    def test_main_story_is_playable_in_order(self):
        """Completing whatever is available, repeatedly, must reach the ending."""
        done = set()
        for _ in range(500):
            nxt = [q for q in core.next_up(self.data, done) if q["type"] == "main"
                   and q["region"] not in ("Hearts of Stone", "Blood and Wine")]
            if not nxt:
                break
            done.add(nxt[0]["id"])
        self.assertIn("ending", done)

    def test_next_up_follows_order(self):
        first = core.next_up(self.data, set(), "White Orchard")
        self.assertEqual(first[0]["id"], "lilac")
        self.assertNotIn("beast", [q["id"] for q in first])
        self.assertIn("beast", [q["id"] for q in core.next_up(self.data, {"lilac"}, "White Orchard")])

    def test_blocked_and_missing_prereqs(self):
        q = {x["id"]: x for x in core.annotate(self.data, set())}["beast"]
        self.assertEqual(q["status"], core.BLOCKED)
        self.assertEqual(core.missing_prereqs(q, self.data, set()), ["Lilac and Gooseberries"])

    def test_isle_of_mists_is_the_big_cutoff(self):
        by = {x["id"]: x for x in core.annotate(self.data, {"isle"})}
        for qid in ("ciris_room", "an_invitation_from_keira_metz", "now_or_never", "kings_gambit"):
            self.assertEqual(by[qid]["status"], core.MISSED, qid)

    def test_urgent_alert_when_cutoff_becomes_available(self):
        # Before Imperial Audience is reachable, nothing is urgent for it.
        early = {a["id"] for a in core.alerts(self.data, {"lilac"}) if a["urgent"]}
        self.assertNotIn("missing_in_action", early)
        # Once Incident at White Orchard is done, Imperial Audience is available.
        now = {a["id"] for a in core.alerts(self.data, {"lilac", "beast", "incident"}) if a["urgent"]}
        self.assertIn("missing_in_action", now)
        # After it is done the quest is reported as MISSED, not urgent.
        lost = [a for a in core.alerts(self.data, {"lilac", "beast", "incident", "imperial"})
                if a["id"] == "missing_in_action"]
        self.assertEqual(lost[0]["status"], core.MISSED)
        self.assertFalse(lost[0]["urgent"])

    def test_no_noise_at_game_start(self):
        self.assertEqual(core.alerts(self.data, set()), [])

    def test_reason_of_state_prereqs(self):
        q = self.by_id["reason_of_state"]
        self.assertEqual(len(q["requires"]), 4)

    def test_progress_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = core.Progress(Path(d) / "sub" / "p.json")
            self.assertTrue(p.toggle("lilac"))
            self.assertEqual(core.Progress(p.path).done, {"lilac"})
            self.assertFalse(p.toggle("lilac"))

    def test_search_filters(self):
        rows = core.search(self.data, set(), text="baron")
        self.assertTrue(rows)
        self.assertTrue(all("baron" in (r["name"] + r.get("notes", "")).lower() for r in rows))
        self.assertTrue(all(r.get("missable") for r in core.search(self.data, set(), missable_only=True)))


if __name__ == "__main__":
    unittest.main()
