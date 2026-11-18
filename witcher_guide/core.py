"""Pure logic for the Witcher 3 guide overlay (no GUI imports, fully testable)."""
import json
import os
from pathlib import Path

DONE, MISSED, AVAILABLE, BLOCKED = "done", "missed", "available", "blocked"

DATA_FILE = Path(__file__).parent / "data" / "quests.json"


def default_progress_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "witcher_guide" / "progress.json"


def load_data(path=DATA_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Progress:
    """Completed quests, persisted to JSON.

    `done` is what you ticked by hand. `auto_done` / `auto_failed` come from the
    in-game mod and are replaced whenever the game reports a full snapshot, so
    loading an older save corrects them. `tracked` (the quest selected in the
    game's journal) is runtime-only.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path else default_progress_path()
        self.done, self.auto_done, self.auto_failed = set(), set(), set()
        self.tracked = None
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, list):  # format written by earlier versions
            raw = {"done": raw}
        self.done = set(raw.get("done", []))
        self.auto_done = set(raw.get("auto_done", []))
        self.auto_failed = set(raw.get("auto_failed", []))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "done": sorted(self.done), "auto_done": sorted(self.auto_done),
            "auto_failed": sorted(self.auto_failed)}), encoding="utf-8")

    def all_done(self):
        return self.done | self.auto_done

    def toggle(self, qid):
        """Tick or untick by hand; unticking also overrides an automatic completion."""
        if qid in self.all_done():
            self.done.discard(qid)
            self.auto_done.discard(qid)
        else:
            self.done.add(qid)
        self.save()
        return qid in self.all_done()


def status(quest, by_id, done, failed=frozenset()):
    if quest["id"] in done:
        return DONE
    if quest["id"] in failed:  # the game itself reported it failed
        return MISSED
    # Missed: a later quest it must precede has already been completed.
    cutoff = quest.get("expires_before")
    if cutoff and cutoff in done:
        return MISSED
    if all(r in done for r in quest.get("requires", [])):
        return AVAILABLE
    return BLOCKED


def annotate(data, done, failed=frozenset()):
    by_id = {q["id"]: q for q in data["quests"]}
    return [dict(q, status=status(q, by_id, done, failed)) for q in data["quests"]]


def next_up(data, done, region=None, failed=frozenset()):
    """Available, not-done quests in data order (the recommended order)."""
    return [q for q in annotate(data, done, failed)
            if q["status"] == AVAILABLE and (region is None or q["region"] == region)]


def alerts(data, done, failed=frozenset()):
    """Missable quests that are already lost, or that must be done before a
    main-story cutoff quest which can be started right now. Cutoffs with no
    prerequisites (startable from the beginning) and side-quest cutoffs are only
    flagged once lost, to keep the banner quiet. Each row gets an `urgent`
    flag; lost rows come first."""
    rows = annotate(data, done, failed)
    by_id = {q["id"]: q for q in rows}
    out = []
    for q in rows:
        if not q.get("missable") or q["status"] == DONE:
            continue
        cutoff = by_id.get(q.get("expires_before"))
        if q["status"] == MISSED:
            out.append(dict(q, urgent=False))
        elif (cutoff and cutoff["status"] == AVAILABLE and cutoff["type"] == "main"
              and cutoff.get("requires")):
            out.append(dict(q, urgent=True))
    out.sort(key=lambda q: q["status"] != MISSED)
    return out


def missing_prereqs(quest, data, done):
    names = {q["id"]: q["name"] for q in data["quests"]}
    return [names.get(r, r) for r in quest.get("requires", []) if r not in done]


def search(data, done, text="", region=None, missable_only=False, failed=frozenset()):
    text = text.lower().strip()
    rows = []
    for q in annotate(data, done, failed):
        if region and q["region"] != region:
            continue
        if missable_only and not q.get("missable"):
            continue
        hay = f'{q["name"]} {q.get("notes", "")}'.lower()
        if text and text not in hay:
            continue
        rows.append(q)
    return rows
