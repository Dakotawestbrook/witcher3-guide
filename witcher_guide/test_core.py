import tempfile
import unittest
from pathlib import Path

from witcher_guide import core


class TestCore(unittest.TestCase):
    def setUp(self):
        self.data = core.load_data()
        self.ids = {q["id"] for q in self.data["quests"]}

    def test_data_integrity(self):
        self.assertEqual(len(self.ids), len(self.data["quests"]), "duplicate ids")
        for q in self.data["quests"]:
            self.assertIn(q["region"], self.data["regions"])
            for r in q["requires"]:
                self.assertIn(r, self.ids)
            if q.get("expires_before"):
                self.assertIn(q["expires_before"], self.ids)
            if q.get("missable"):
                self.assertTrue(q.get("warn"), q["id"])

    def test_no_dependency_cycles(self):
        by_id = {q["id"]: q for q in self.data["quests"]}
        def walk(i, seen):
            self.assertNotIn(i, seen)
            for r in by_id[i]["requires"]:
                walk(r, seen | {i})
        for i in by_id:
            walk(i, set())

    def test_next_up_follows_order(self):
        self.assertEqual(core.next_up(self.data, set(), "White Orchard")[0]["id"], "lilac")
        names = [q["id"] for q in core.next_up(self.data, {"lilac"}, "White Orchard")]
        self.assertEqual(names, ["beast_wo"])

    def test_blocked_and_missing_prereqs(self):
        q = {x["id"]: x for x in core.annotate(self.data, set())}["imperial"]
        self.assertEqual(q["status"], core.BLOCKED)
        self.assertEqual(core.missing_prereqs(q, self.data, set()), ["The Beast of White Orchard"])

    def test_missed_after_point_of_no_return(self):
        by = {x["id"]: x for x in core.annotate(self.data, {"prep"})}
        self.assertEqual(by["gwent"]["status"], core.MISSED)
        self.assertIn("gwent", [a["id"] for a in core.alerts(self.data, {"prep"})])

    def test_progress_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = core.Progress(Path(d) / "sub" / "p.json")
            self.assertTrue(p.toggle("lilac"))
            self.assertEqual(core.Progress(p.path).done, {"lilac"})
            self.assertFalse(p.toggle("lilac"))

    def test_search_filters(self):
        rows = core.search(self.data, set(), text="baron", missable_only=False)
        self.assertTrue(all("baron" in (r["name"] + r.get("notes", "")).lower() for r in rows))
        self.assertTrue(all(r.get("missable") for r in core.search(self.data, set(), missable_only=True)))


if __name__ == "__main__":
    unittest.main()
