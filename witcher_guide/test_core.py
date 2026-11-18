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
        self.assertGreaterEqual(len(decs), 100)
        self.assertEqual(len({d["id"] for d in decs}), len(decs), "duplicate decision ids")
        for d in decs:
            self.assertTrue(d["source"], d["id"])
            self.assertGreaterEqual(len(d["options"]), 2, d["id"])
            self.assertIn("quests", d)  # may be empty for contracts, which are not in quests.json
            for qid in d["quests"]:
                self.assertIn(qid, self.by_id, f'{d["id"]} links to a missing quest {qid}')
            for o in d["options"]:
                self.assertIn(o["type"], ("dialogue", "action"), d["id"])
                self.assertTrue(o["label"] and o["result"], d["id"])
            for field in ("best_rewards", "best_moral", "best_outcome"):
                pk = d.get(field)
                if pk:
                    self.assertTrue(pk["pick"] and pk["why"], (d["id"], field))
                    self.assertIn(pk["basis"], ("stated", "judgement", "player"), (d["id"], field))

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
        self.assertIn("orphans die", text)                           # killing the tree kills the orphans (player-confirmed)
        self.assertNotIn("orphans' fate is unknown. The military", text)
        self.assertEqual(hill["best_moral"]["pick"], "Kill the spirit")
        self.assertEqual(hill["best_moral"]["basis"], "player")      # your call, so it is not labelled as a source or as my judgement
        self.assertIn("orphans", hill["best_moral"]["why"])          # and it states the cost honestly
        self.assertIn("Both endings are grim", hill["note"])
        self.assertIn("player's call", core.format_decision(hill, "morals"))
        self.assertIn("baron_hillock", {d["id"] for d in core.decisions_for(core.load_decisions(), {"whisper"})})
        self.assertTrue(core.has_conflict(decs["baron_pellar"]))    # rewards: Axii, morals: offer to heal
        self.assertEqual(decs["baron_barn"]["best_rewards"]["basis"], "stated")
        self.assertIn("50 crowns", decs["baron_tamara"]["best_rewards"]["why"])

    def test_more_decisions_with_stated_rewards(self):
        decs = {d["id"]: d for d in core.load_decisions()}
        self.assertEqual(sum(1 for d in decs.values() if d["kind"] == "contract"), 9)
        # reward comparisons that the guides state outright
        self.assertIn("60 crowns", decs["nithing"]["best_rewards"]["why"])
        self.assertEqual(decs["novi_thief"]["best_rewards"]["pick"], "Free him")
        self.assertIn("500 crowns", decs["baw_paperchase"]["best_rewards"]["why"])
        self.assertIn("Josta", decs["wolfs_clothing"]["best_rewards"]["why"])
        self.assertIn("twice", decs["velen_swamp_thing"]["best_rewards"]["why"])
        self.assertEqual(decs["velen_pyres"]["best_rewards"]["basis"], "stated")
        # where reward and morals disagree, both are shown and the row is flagged
        for did in ("velen_missing_brother", "wh_margrit", "novi_woodland", "hos_taxman", "nithing"):
            self.assertTrue(core.has_conflict(decs[did]), did)
        # no recommendation where the sources give none
        self.assertIsNone(decs["velen_wannabe"]["best_rewards"])
        self.assertIsNone(decs["skel_leshen"]["best_moral"])
        # a stated pick must be one a source can back: stated picks all carry the source on the decision
        for d in decs.values():
            for f in ("best_rewards", "best_moral", "best_outcome"):
                if d.get(f) and d[f]["basis"] == "stated":
                    self.assertTrue(d["source"], d["id"])

    def test_latest_decisions_state_their_rewards(self):
        decs = {d["id"]: d for d in core.load_decisions()}
        self.assertIn("50 crowns", decs["fake_papers"]["best_rewards"]["why"])      # Axii: pass for 50 and 40 XP
        self.assertEqual(decs["fake_papers"]["best_rewards"]["basis"], "stated")
        self.assertIn("75 experience", decs["thou_shalt_not_pass"]["best_rewards"]["why"])
        self.assertIn("150 crowns", decs["worthy_of_trust"]["best_rewards"]["why"])
        self.assertIn("Eirlithrad", decs["junior_rico"]["best_rewards"]["why"])
        self.assertEqual(decs["the_volunteer"]["best_outcome"]["basis"], "stated")
        # rewards and the fight record disagree in the Novigrad illegal fights
        self.assertNotEqual(decs["fists_novigrad"]["best_rewards"]["pick"], decs["fists_novigrad"]["best_outcome"]["pick"])
        # decisions with no source-backed pick stay unrated rather than guessed
        self.assertIsNone(decs["eldberg_contract"]["best_rewards"])
        self.assertIsNone(decs["eldberg_contract"]["best_moral"])
        # every contract decision is flagged as a contract
        for did in ("groom_contract", "eldberg_contract"):
            self.assertEqual(decs[did]["kind"], "contract")

    def test_every_missable_gwent_card_on_the_checklist_is_covered(self):
        decs = [d for d in core.load_decisions() if d["kind"] == "gwent"]
        self.assertGreaterEqual(len(decs), 9)
        text = " ".join(" ".join([d["name"], d["situation"], d.get("note", "")] + [o["label"] + " " + o["result"] for o in d["options"]])
                        for d in decs)
        # the 20 base-game cards the Gwent checklist lists as missable (plus the one that depends on Dijkstra)
        for card in ("Sigismund Dijkstra", "Esterad Thyssen", "Geralt of Rivia", "Saesenthessis", "Tibor Eggebracht",
                     "Dandelion", "Milva", "Vampire: Bruxa", "Foltest: The Steel-Forged", "Emhyr var Emreis: The Relentless",
                     "Francesca Findabair: Queen of Dol Blathanna", "Eredin: Bringer of Death", "John Natalis",
                     "Isengrim Faoiltiarna", "Fringilla Vigo", "Iorveth", "Puttkammer", "Sweers",
                     "Black Infantry Archer #2", "Etolian Auxiliary Archers #2", "Francesca Findabair: The Beautiful"):
            self.assertIn(card, text, f"missable card not covered: {card}")
        by = {d["id"]: d for d in decs}
        # each missable entry names the cutoff and says what is lost
        self.assertIn("Family Matters", by["gw_baron"]["best_rewards"]["pick"])
        self.assertIn("Reason of State", by["gw_reason"]["best_rewards"]["pick"])
        self.assertIn("Now or Never", by["gw_olivier"]["best_rewards"]["pick"])
        self.assertIn("one shot", " ".join(o["result"] for o in by["gw_vegelbud"]["options"]))
        self.assertIn("Lose a match", by["gw_high_stakes"]["best_rewards"]["why"])
        self.assertEqual(len(by["gw_high_stakes"]["options"]), 4)  # four leader cards, one per opponent
        # the "looks missable but isn't" entry tells you not to worry about four cards
        self.assertEqual(len(by["gw_not_missable"]["options"]), 4)
        # linked quests exist (or are empty for the reassurance entry)
        self.assertEqual(by["gw_not_missable"]["quests"], [])
        self.assertTrue(by["gw_dangerous_game"]["quests"] == ["a_dangerous_game"])

    def test_searching_gwent_finds_the_gwent_entries(self):
        decs = core.load_decisions()
        found = {d["id"] for d in core.filter_decisions(decs, "gwent")}
        self.assertTrue({d["id"] for d in decs if d["kind"] == "gwent"} <= found)
        self.assertIn("gw_baron", {d["id"] for d in core.decisions_for(decs, {"family1"})})

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

    # ---- Views (the Show filter) and progress counts ----
    def test_views_filter_quests_by_status(self):
        done = {"lilac", "beast"}
        rows = core.annotate(self.data, done)
        v = {name: {q["id"] for q in core.apply_view(rows, name)} for name in core.VIEWS}
        self.assertEqual(len(v["all"]), len(self.data["quests"]))
        self.assertEqual(v["done"], done)
        self.assertTrue(v["done"].isdisjoint(v["todo"]))
        self.assertTrue(v["available"] <= v["todo"])                       # available quests are to-do
        self.assertIn("incident", v["available"])                           # its prerequisites are done
        self.assertNotIn("imperial", v["available"])                        # still blocked
        self.assertIn("imperial", v["todo"])                                # blocked quests are still to do
        self.assertTrue(all(self.by_id[i].get("missable") for i in v["missable"]))
        self.assertTrue(v["missable"].isdisjoint(done))
        self.assertEqual(core.apply_view(rows, "bogus"), rows)              # unknown view shows everything

    def test_lost_quests_are_not_to_do(self):
        rows = core.annotate(self.data, {"imperial"})                       # starting Imperial Audience closes Missing in Action
        self.assertEqual({q["id"]: q["status"] for q in rows}["missing_in_action"], core.MISSED)
        self.assertNotIn("missing_in_action", {q["id"] for q in core.apply_view(rows, "todo")})

    def test_every_view_and_goal_has_a_label(self):
        self.assertEqual(set(core.VIEWS), set(core.VIEW_LABELS))
        self.assertEqual(set(core.GOALS), set(core.GOAL_LABELS))
        self.assertTrue(all(core.VIEW_LABELS.values()) and all(core.GOAL_LABELS.values()))

    def test_region_progress_counts_done_quests_per_region_and_overall(self):
        p = core.region_progress(self.data, set())
        self.assertEqual(p[None], (0, len(self.data["quests"])))
        self.assertEqual(sum(t for r, (d, t) in p.items() if r is not None), len(self.data["quests"]))
        p = core.region_progress(self.data, {"lilac", "beast", "funeral_pyres", "not_a_quest"})
        self.assertEqual(p["White Orchard"][0], 2)
        self.assertEqual(p["Velen"][0], 1)
        self.assertEqual(p[None][0], 3)                                     # unknown ids are ignored
        self.assertTrue(all(0 <= d <= t for d, t in p.values()))
        wo = [q["id"] for q in self.data["quests"] if q["region"] == "White Orchard"]
        self.assertEqual(core.region_progress(self.data, set(wo))["White Orchard"], (len(wo), len(wo)))

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
