"""Checks each link in the game -> log -> overlay chain and prints a report.

    python -m witcher_guide.diagnose            (run from the witcher3-guide folder)
    python -m witcher_guide.diagnose --log "C:\\path\\to\\scriptlog.txt"
"""
import argparse
import collections
import tempfile
import time
from pathlib import Path

from witcher_guide import core, tracker


def report(log_paths, data=None, out=print):
    data = data or core.load_data()
    ok = True
    out("== 1. Is the game writing a script log?")
    for p in log_paths:
        if p.exists():
            age = time.time() - p.stat().st_mtime
            out(f"   found {p}  ({p.stat().st_size:,} bytes, last written {age/60:.1f} min ago)")
        else:
            out(f"   missing {p}")
    log = tracker.find_log(log_paths)
    if not log:
        out("   -> No log file. The game was probably not launched with -debugscripts, or script")
        out("      logging is unavailable. Nothing else can work until this file exists.")
        return False

    raw = log.read_bytes().decode("utf-8", "replace").splitlines()
    out(f"\n== 2. What is in {log.name}?")
    out(f"   {len(raw):,} lines total")
    journal = [l for l in raw if "Journal" in l]
    mine = [l for l in raw if tracker.PREFIX in l]
    out(f"   lines mentioning 'Journal' (the game's own quest logging): {len(journal)}")
    out(f"   lines from the mod ('{tracker.PREFIX}'): {len(mine)}")
    if not mine:
        ok = False
        if journal:
            out("   -> Logging works (the game's own lines are there) but the mod wrote nothing.")
            out("      The mod may not be loaded, or its hook did not fire yet (try completing or")
            out("      updating a quest, or loading a save, then re-run this).")
        else:
            out("   -> The log has no journal lines either. Logging may be off or the log is for a")
            out("      different session. First 3 lines:")
            for l in raw[:3]:
                out("      " + l[:150])
        return False
    out("   first / last mod lines:")
    for l in mine[:3] + (["..."] if len(mine) > 6 else []) + mine[-3:]:
        out("      " + l[:150])

    out("\n== 3. Does the overlay understand them?")
    parsed = [tracker.parse_line(l) for l in mine]
    bad = sum(1 for e in parsed if e is None)
    states = collections.Counter(e[2] for e in parsed if e and e[0] == "q")
    snaps = sum(1 for e in parsed if e == ("snapshot", "begin"))
    out(f"   unreadable mod lines: {bad}")
    out(f"   snapshots: {snaps}   quest lines by state: {dict(states)}")
    tracked = [e[1] for e in parsed if e and e[0] == "tracked"]
    out(f"   last tracked quest reported: {tracked[-1] if tracked else '(none)'}")
    if not states.get("success"):
        ok = False
        out("   -> No quest is reported as 'success'. If your game has finished quests, the snapshot")
        out("      may have been sent before the journal loaded (an empty snapshot is ignored).")

    out("\n== 4. Do the quest titles match quests.json?")
    with tempfile.TemporaryDirectory() as d:
        pr = core.Progress(Path(d) / "p.json")
        tr = tracker.Tracker(pr, data)
        for l in mine:
            tr.feed(l)
        titles = {e[1] for e in parsed if e and e[0] == "q"}
        matched = {t for t in titles if tr.matcher.match(t)}
        out(f"   {len(matched)} of {len(titles)} distinct titles matched")
        out(f"   quests that would be marked done: {len(pr.auto_done)}   failed: {len(pr.auto_failed)}")
        miss = sorted(titles - matched)
        if miss:
            out(f"   unmatched titles ({len(miss)}), first 15 (these are fine if they are small side quests):")
            for t in miss[:15]:
                out(f"      {t}")
    if not matched and titles:
        ok = False
        out("   -> Nothing matched. Is the game set to a non-English language? Titles are matched by")
        out("      English name; the paste above shows what the game actually reports.")

    out("\n== 5. What does the overlay's saved progress contain?")
    real = core.Progress()
    out(f"   {real.path}")
    out(f"   ticked by hand: {len(real.done)}   automatic done: {len(real.auto_done)}   automatic failed: {len(real.auto_failed)}")
    if matched and not real.auto_done:
        out("   -> The log would mark quests done, but the overlay has none saved. Was the overlay")
        out("      running while the game loaded? Restart it (it re-reads the whole log on start).")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", help="path to scriptlog.txt (default: Documents\\The Witcher 3)")
    a = ap.parse_args(argv)
    paths = [Path(a.log)] if a.log else tracker.default_log_paths()
    ok = report(paths)
    print("\nAll checks passed." if ok else "\nSomething above needs attention. Paste this whole report to Claude.")


if __name__ == "__main__":
    main()
