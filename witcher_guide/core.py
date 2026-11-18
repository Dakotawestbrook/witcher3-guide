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
    """Set of completed ids, persisted to JSON."""

    def __init__(self, path=None):
        self.path = Path(path) if path else default_progress_path()
        self.done = set()
        self.load()

    def load(self):
        try:
            self.done = set(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.done = set()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self.done)), encoding="utf-8")

    def toggle(self, qid):
        self.done.symmetric_difference_update({qid})
        self.save()
        return qid in self.done


def status(quest, by_id, done):
    if quest["id"] in done:
        return DONE
    # Missed: a later quest it must precede has already been completed.
    cutoff = quest.get("expires_before")
    if cutoff and cutoff in done:
        return MISSED
    if all(r in done for r in quest.get("requires", [])):
        return AVAILABLE
    return BLOCKED


def annotate(data, done):
    by_id = {q["id"]: q for q in data["quests"]}
    return [dict(q, status=status(q, by_id, done)) for q in data["quests"]]


def next_up(data, done, region=None):
    """Available, not-done quests in data order (the recommended order)."""
    return [q for q in annotate(data, done)
            if q["status"] == AVAILABLE and (region is None or q["region"] == region)]


def alerts(data, done):
    """Missable quests the player can act on right now, or has already lost."""
    out = []
    for q in annotate(data, done):
        if q.get("missable") and q["status"] in (AVAILABLE, MISSED):
            out.append(q)
    return out


def missing_prereqs(quest, data, done):
    names = {q["id"]: q["name"] for q in data["quests"]}
    return [names.get(r, r) for r in quest.get("requires", []) if r not in done]


def search(data, done, text="", region=None, missable_only=False):
    text = text.lower().strip()
    rows = []
    for q in annotate(data, done):
        if region and q["region"] != region:
            continue
        if missable_only and not q.get("missable"):
            continue
        hay = f'{q["name"]} {q.get("notes", "")}'.lower()
        if text and text not in hay:
            continue
        rows.append(q)
    return rows
