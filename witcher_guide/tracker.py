"""Receives quest events from the in-game mod and updates progress.

The mod writes lines to the game's script log (scriptlog.txt, needs the game to
be launched with -debugscripts). Only lines containing PREFIX are used:

    @@WG@@|snapshot|begin          full journal dump follows (on save load)
    @@WG@@|q|<quest title>|<state> state = active | success | failed | inactive
    @@WG@@|snapshot|end
    @@WG@@|tracked|<quest title>   the quest selected/tracked in the journal ('' = none)

Anything before PREFIX on the line (timestamps, channel names) is ignored.
A snapshot replaces the automatic state, so loading an older save corrects it;
q lines outside a snapshot are applied incrementally.
"""
import json
import os
import re
import sys
import threading
from pathlib import Path

PREFIX = "@@WG@@"
ALIASES_FILE = Path(__file__).parent / "data" / "aliases.json"
LOG_NAMES = ("scriptlog.txt", "scriptslog.txt")  # documented spellings differ


def norm(title):
    t = re.sub(r"\((part|pt)\.?\s*\d+\)", "", title.lower().replace("’", "'"))
    return re.sub(r"[^a-z0-9]", "", t)


def parse_line(line):
    """Returns ('snapshot', 'begin'|'end'), ('q', title, state), ('tracked', title) or None."""
    i = line.find(PREFIX)
    if i < 0:
        return None
    parts = [p.strip() for p in line[i + len(PREFIX):].lstrip("|").split("|")]
    kind = parts[0].lower() if parts else ""
    if kind == "snapshot" and len(parts) > 1 and parts[1].lower() in ("begin", "end"):
        return ("snapshot", parts[1].lower())
    if kind == "q" and len(parts) >= 3 and parts[1]:
        return ("q", parts[1], parts[2].lower())
    if kind == "tracked":
        return ("tracked", parts[1] if len(parts) > 1 else "")
    return None


class Matcher:
    """Maps in-game quest titles to quest ids (several ids if a game quest is split here)."""

    def __init__(self, data, aliases=None):
        self.index = {}
        for q in data["quests"]:
            self.index.setdefault(norm(q["name"]), []).append(q["id"])
        for key, ids in (aliases or {}).items():
            if not key.startswith("_"):
                self.index[norm(key)] = list(ids)

    def match(self, title):
        key = norm(title)
        return self.index.get(key) or self.index.get(re.sub(r"^the", "", key)) or []


def load_aliases(path=ALIASES_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Tracker:
    def __init__(self, progress, data, aliases=None):
        self.progress = progress
        self.matcher = Matcher(data, load_aliases() if aliases is None else aliases)
        self.unmatched = set()
        self._snap = None  # (done, failed) while a snapshot is being received
        self._snap_seen = 0  # quest lines in the current snapshot

    def _ids(self, title):
        ids = self.matcher.match(title)
        if not ids and title not in self.unmatched:
            self.unmatched.add(title)
            self._write_unmatched()
        return ids

    def _write_unmatched(self):
        try:
            p = self.progress.path.parent / "unmatched_quests.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(sorted(self.unmatched)) + "\n", encoding="utf-8")
        except OSError:
            pass

    def feed(self, line):
        """Apply one log line. Returns 'progress', 'tracked' or None for what changed."""
        ev = parse_line(line)
        if not ev:
            return None
        pr = self.progress
        if ev[0] == "snapshot":
            if ev[1] == "begin":
                self._snap, self._snap_seen = (set(), set()), 0
                return None
            if self._snap is None:
                return None
            done, failed = self._snap
            seen, self._snap = self._snap_seen, None
            if not seen:  # an empty snapshot (journal not loaded yet) must never wipe progress
                return None
            changed = (done, failed) != (pr.auto_done, pr.auto_failed)
            pr.auto_done, pr.auto_failed = done, failed
            if changed:
                pr.save()
            return "progress" if changed else None
        if ev[0] == "tracked":
            ids = self._ids(ev[1]) if ev[1] else []
            new = ids[0] if ids else None
            if new == pr.tracked and set(ids) == pr.tracked_all:
                return None
            pr.tracked, pr.tracked_all = new, set(ids)
            return "tracked"
        _, title, state = ev
        if self._snap is not None:
            self._snap_seen += 1
        if state not in ("success", "failed"):
            self._ids(title)  # still learn about unmatched titles
            return None
        ids = self._ids(title)
        target = self._snap if self._snap is not None else (pr.auto_done, pr.auto_failed)
        done, failed = target
        before = (set(done), set(failed))
        for i in ids:
            if state == "success":
                done.add(i); failed.discard(i)
            else:
                failed.add(i); done.discard(i)
        if self._snap is None and (done, failed) != before:
            pr.save()
            return "progress"
        return None


# ---- locating and tailing the game's log -------------------------------------
def documents_dir():
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / "Documents"


def default_log_paths():
    base = documents_dir() / "The Witcher 3"
    return [base / n for n in LOG_NAMES]


def find_log(paths):
    existing = [p for p in paths if p.exists()]
    return max(existing, key=lambda p: p.stat().st_mtime) if existing else None


class LogTailer:
    """Yields new complete lines containing PREFIX from a growing file."""

    def __init__(self, path):
        self.path, self.pos, self.buf = Path(path), 0, b""

    def read_new_lines(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            self.pos, self.buf = 0, b""
            return []
        if size < self.pos:  # the game truncated/recreated the log
            self.pos, self.buf = 0, b""
        if size == self.pos:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return []
        self.pos += len(data)
        *lines, self.buf = (self.buf + data).split(b"\n")
        text = [l.decode("utf-8", "replace").rstrip("\r") for l in lines]
        return [l for l in text if PREFIX in l]


def start_tracking(events, paths=None, interval=1.0, stop=None):
    """Background thread: posts ('lines', [...]) to `events` as the log grows."""
    paths = [Path(p) for p in (paths or default_log_paths())]
    stop = stop or threading.Event()

    def loop():
        tailer, current = None, None
        while not stop.is_set():
            found = find_log(paths)
            if found != current:
                current, tailer = found, (LogTailer(found) if found else None)
            if tailer:
                lines = tailer.read_new_lines()
                if lines:
                    events.put(("lines", lines))
            stop.wait(interval)

    threading.Thread(target=loop, daemon=True).start()
    return stop
