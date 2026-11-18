"""Builds the Witcher Guide script mod from YOUR copy of the game's scripts.

    python mod/install_mod.py --game "C:\\Program Files (x86)\\Steam\\steamapps\\common\\The Witcher 3"

It copies three vanilla script files from your game, inserts one line into each
(marked "// modWitcherGuide"), and writes them with witcherGuide.ws into
<game>\\mods\\modWitcherGuide. Game code is never stored in this repository.

If your scripts are somewhere else (for example extracted with WolvenKit), pass
--scripts DIR. Other mods that change the same files conflict: run Script Merger.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOD_NAME = "modWitcherGuide"
NEW_FILE = ("game/modWitcherGuide/witcherGuide.ws", HERE / "witcherGuide.ws")
MARK = "// modWitcherGuide"

# vanilla file -> (regex of the one line to insert after, statement to insert)
PATCHES = {
    # fires whenever a quest's status changes or a quest is added
    "game/gui/hud/hud.ws": (
        r"LogChannel\(\s*'Journal',\s*\"OnQuestEvent \"\s*\+\s*journalQuest\.baseName\s*\);",
        "WG_Snapshot();"),
    # fires when the player selects/tracks a different quest
    "game/gui/hud/modules/hudModuleQuests.ws": (
        r"e\.eventType\s*=\s*EUET_StartedTracking;",
        "WG_LogTracked( journalQuest );"),
    # fires when a saved game is loaded
    "game/player/playerWitcher.ws": (
        r"\bApplyPatchFixes\(\s*\);",
        "WG_Snapshot();"),
}


class PatchError(Exception):
    pass


def decode(raw):
    """Returns (text, encoding) preserving what the game's files use."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def encode(text, enc):
    if enc == "utf-16":  # keep a little-endian BOM like the originals
        return b"\xff\xfe" + text.encode("utf-16-le")
    return text.encode(enc)


def patch_text(rel, text):
    """Insert our line after the anchor line. Idempotent; fails loudly if the file differs."""
    pattern, stmt = PATCHES[rel]
    if MARK in text:
        return text
    hits = list(re.finditer(pattern, text))
    if len(hits) != 1:
        raise PatchError(f"{rel}: expected exactly one place to patch, found {len(hits)} "
                         "(your game version may differ; patch by hand, see mod/README.md)")
    m = hits[0]
    ls = text.rfind("\n", 0, m.start()) + 1
    indent = re.match(r"[ \t]*", text[ls:m.start()]).group(0)
    le = text.find("\n", m.end())
    le = len(text) if le < 0 else le
    nl = "\r\n" if text[:le].endswith("\r") else "\n"
    insert_at = le - (1 if nl == "\r\n" else 0)
    return text[:insert_at] + nl + f"{indent}{stmt} {MARK}" + text[insert_at:]


def build(scripts_dir, out_dir):
    scripts_dir, out_dir = Path(scripts_dir), Path(out_dir)
    written = []
    for rel in PATCHES:
        src = scripts_dir / rel
        if not src.exists():
            raise PatchError(f"Missing {src}. Point --scripts at your game's scripts folder.")
        text, enc = decode(src.read_bytes())
        dst = out_dir / "content" / "scripts" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(encode(patch_text(rel, text), enc))
        written.append(dst)
    rel, src = NEW_FILE
    dst = out_dir / "content" / "scripts" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    written.append(dst)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="The Witcher 3 install folder")
    ap.add_argument("--scripts", help="folder holding the vanilla scripts (default: <game>/content/content0/scripts)")
    ap.add_argument("--out", help=f"output mod folder (default: <game>/mods/{MOD_NAME})")
    a = ap.parse_args(argv)
    if not (a.scripts or a.game):
        ap.error("give --game or --scripts")
    scripts = Path(a.scripts) if a.scripts else Path(a.game) / "content" / "content0" / "scripts"
    out = Path(a.out) if a.out else Path(a.game or ".") / "mods" / MOD_NAME
    try:
        files = build(scripts, out)
    except PatchError as e:
        sys.exit(f"Error: {e}")
    print(f"Wrote {len(files)} files to {out}:")
    for f in files:
        print("  ", f.relative_to(out))
    print("\nNext: run Script Merger if you use other mods, then launch the game with -debugscripts.")


if __name__ == "__main__":
    main()
