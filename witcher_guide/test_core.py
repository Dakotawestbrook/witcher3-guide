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

    def _play(self, region):
        done = set()
        for _ in range(200):
            nxt = [q for q in core.next_up(self.data, done, region) if q["type"] == "main"]
            if not nxt:
                break
            done.add(nxt[0]["id"])
        return done

    def test_hearts_of_stone_is_playable(self):
        self.assertIn("hos_whatsoever_a_man_soweth", self._play("Hearts of Stone"))

    def test_blood_and_wine_needs_base_game_then_is_playable(self):
        self.assertEqual(self.by_id["baw_envoys_wineboys"]["requires"], ["poet"])
        done = {"poet"}
        for _ in range(200):
            nxt = [q for q in core.next_up(self.data, done, "Blood and Wine") if q["type"] == "main"]
            if not nxt:
                break
            done.add(nxt[0]["id"])
        self.assertIn("baw_be_it_ever_so_humble", done)

    def test_dlc_missed_and_urgent(self):
        # Mill's Grist lives between La Cage au Fou and Wine is Sacred.
        chain = {"poet", "baw_envoys_wineboys", "baw_the_beast_of_toussaint", "baw_blood_run", "baw_la_cage_au_fou",
                 "baw_where_children_toil_toys_waste_away"}
        urgent = {a["id"] for a in core.alerts(self.data, chain) if a["urgent"]}
        self.assertIn("baw_amidst_the_mills_grist", urgent)
        lost = {a["id"] for a in core.alerts(self.data, chain | {"baw_wine_is_sacred"}) if a["status"] == core.MISSED}
        self.assertIn("baw_amidst_the_mills_grist", lost)
        self.assertEqual({a["id"] for a in core.alerts(self.data, {"hos_evils_soft_first_touches"}) if a["urgent"]},
                         {"hos_a_midnight_clear"})

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

    def test_tracked_quest_that_closes_missables_is_flagged(self):
        risks = core.tracked_risks(self.data, set(), frozenset(), {"imperial"})
        self.assertEqual({q["name"] for q in risks}, {"Twisted Firestarter", "Missing in Action", "On Death's Bed"})
        self.assertTrue(all(q["expires_before"] == "imperial" for q in risks))

    def test_tracked_risks_ignore_finished_lost_and_unrelated(self):
        names = {q["name"]: q["id"] for q in self.data["quests"]}
        done = {names["Missing in Action"]}
        risks = {q["id"] for q in core.tracked_risks(self.data, done, frozenset(), {"imperial"})}
        self.assertNotIn(names["Missing in Action"], risks)  # already finished: nothing to lose
        self.assertEqual(len(risks), 2)
        lost = frozenset({names["Twisted Firestarter"]})      # the game already failed it
        self.assertEqual(len(core.tracked_risks(self.data, done, lost, {"imperial"})), 1)
        self.assertEqual(core.tracked_risks(self.data, set(), frozenset(), {"lilac"}), [])  # closes nothing
        self.assertEqual(core.tracked_risks(self.data, set(), frozenset(), set()), [])
        self.assertEqual(core.tracked_risks(self.data, set(), frozenset(), None), [])

    def test_isle_of_mists_puts_many_quests_at_risk(self):
        self.assertGreaterEqual(len(core.tracked_risks(self.data, set(), frozenset(), {"isle"})), 15)

    def test_every_cutoff_quest_triggers_a_warning(self):
        for cutoff in {q["expires_before"] for q in self.data["quests"] if q.get("expires_before")}:
            self.assertTrue(core.tracked_risks(self.data, set(), frozenset(), {cutoff}), cutoff)

    # ---- Decisions ----
    def test_decisions_data_integrity(self):
        decs = core.load_decisions()
        self.assertGreaterEqual(len(decs), 40)
        self.assertEqual(len({d["id"] for d in decs}), len(decs), "duplicate decision ids")
        for d in decs:
            self.assertTrue(d["source"], d["id"])
            self.assertGreaterEqual(len(d["options"]), 2, d["id"])
            self.assertTrue(d["quests"], d["id"])
            for qid in d["quests"]:
                self.assertIn(qid, self.by_id, f'{d["id"]} links to a missing quest {qid}')
            for o in d["options"]:
                self.assertIn(o["type"], ("dialogue", "action"), d["id"])
                self.assertTrue(o["label"] and o["result"], d["id"])
            for field in ("best_rewards", "best_moral", "best_outcome"):
                pk = d.get(field)
                if pk:
                    self.assertTrue(pk["pick"] and pk["why"], (d["id"], field))
                    self.assertIn(pk["basis"], ("stated", "judgement"), (d["id"], field))

    def test_bloody_baron_decisions(self):
        decs = {d["id"]: d for d in core.load_decisions()}
        baron = [d for d in decs.values() if d["id"].startswith("baron_")]
        self.assertEqual(len(baron), 7)
        for d in baron:  # all happen in Velen main quests
            self.assertTrue(all(self.by_id[q]["region"] == "Velen" for q in d["quests"]), d["id"])
        hill = decs["baron_hillock"]
        self.assertEqual(len(hill["options"]), 2)
        text = " ".join(o["result"] for o in hill["options"])
        for fact in ("incurably sick", "violet flower", "hangs himself", "Downwarren"):
            self.assertIn(fact, text)
        self.assertEqual(hill["best_moral"]["basis"], "judgement")  # my inference, so it is labelled as such
        self.assertIn("baron_hillock", {d["id"] for d in core.decisions_for(core.load_decisions(), {"whisper"})})
        self.assertTrue(core.has_conflict(decs["baron_pellar"]))    # rewards: Axii, morals: offer to heal
        self.assertEqual(decs["baron_barn"]["best_rewards"]["basis"], "stated")
        self.assertIn("50 crowns", decs["baron_tamara"]["best_rewards"]["why"])

    def test_decisions_cover_the_dlcs_and_endings(self):
        kinds = {d["kind"] for d in core.load_decisions()}
        self.assertTrue({"ending", "romance", "side", "dlc"} <= kinds)

    def test_rewards_vs_morals_conflicts_are_found(self):
        decs = {d["id"]: d for d in core.load_decisions()}
        self.assertTrue(core.has_conflict(decs["hos_ending"]))      # rewards: bad ending, morals: good ending
        self.assertTrue(core.has_conflict(decs["nithing"]))
        self.assertTrue(core.has_conflict(decs["baw_basilisk"]))
        self.assertFalse(core.has_conflict(decs["romance"]))        # only an outcome pick

    def test_goal_filter_only_lists_decisions_with_that_pick(self):
        decs = core.load_decisions()
        for goal, field in (("rewards", "best_rewards"), ("morals", "best_moral"), ("outcome", "best_outcome")):
            rows = core.filter_decisions(decs, goal=goal)
            self.assertTrue(rows, goal)
            self.assertTrue(all(d[field] for d in rows), goal)
        self.assertEqual(len(core.filter_decisions(decs, goal="all")), len(decs))

    def test_decision_search_covers_options_and_notes(self):
        decs = core.load_decisions()
        names = {d["id"] for d in core.filter_decisions(decs, "aerondight")}
        self.assertIn("baw_virtues", names)
        self.assertIn("skellige", {d["id"] for d in core.filter_decisions(decs, "Hjalmar")})
        self.assertEqual(core.filter_decisions(decs, "zzzz-nothing"), [])

    def test_decisions_for_a_tracked_quest(self):
        decs = core.load_decisions()
        self.assertEqual({d["id"] for d in core.decisions_for(decs, {"the_nithing"})}, {"nithing"})
        self.assertIn("ciri_skjall", {d["id"] for d in core.decisions_for(decs, ["child_eb"])})
        self.assertEqual(core.decisions_for(decs, set()), [])
        self.assertEqual(core.decisions_for(decs, None), [])

    def test_format_puts_the_chosen_goal_first(self):
        d = {x["id"]: x for x in core.load_decisions()}["hos_ending"]
        lines = core.format_decision(d, "morals").split("\n")
        self.assertTrue(lines[1].startswith("Best for morals"))
        lines = core.format_decision(d, "rewards").split("\n")
        self.assertTrue(lines[1].startswith("Best for rewards"))
        text = core.format_decision(d, "all")
        self.assertIn("Rewards and morals point different ways", text)
        self.assertIn("(source says so)", text)
        self.assertIn("(action)", text)
        j = core.format_decision({x["id"]: x for x in core.load_decisions()}["nithing"], "all")
        self.assertIn("my judgement", j)
        self.assertIn("nothing in my sources", core.format_decision(d, "outcome"))

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
