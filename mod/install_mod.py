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


def candidate_game_dirs():
    """Common install locations that exist on this machine."""
    roots = [r"C:\Program Files (x86)\Steam\steamapps\common\The Witcher 3",
             r"C:\Program Files\Steam\steamapps\common\The Witcher 3",
             r"C:\GOG Games\The Witcher 3 Wild Hunt GOTY", r"C:\GOG Games\The Witcher 3 Wild Hunt",
             r"C:\Program Files (x86)\GOG Galaxy\Games\The Witcher 3 Wild Hunt GOTY",
             r"C:\Program Files\Epic Games\TheWitcher3"]
    return [Path(r) for r in roots if (Path(r) / "content").exists()]


def ask_game_dir(ask=None, candidates=None):
    """Interactive prompt used when the script is started without arguments (double-click)."""
    ask = ask or input  # looked up at call time so callers/tests can substitute it
    found = candidate_game_dirs() if candidates is None else candidates
    if found:
        print(f"Found a Witcher 3 install:\n  {found[0]}")
        if ask("Use this folder? [Y/n] ").strip().lower() in ("", "y", "yes"):
            return found[0]
    print("Paste the Witcher 3 install folder (the one that contains 'content' and 'bin').")
    print("Steam: right-click the game > Manage > Browse local files, then copy the address.")
    return Path(ask("Folder: ").strip().strip('"'))


def run(game=None, scripts=None, out=None):
    """Builds the mod and prints a summary. Raises PatchError on problems."""
    scripts = Path(scripts) if scripts else Path(game) / "content" / "content0" / "scripts"
    out = Path(out) if out else Path(game or ".") / "mods" / MOD_NAME
    files = build(scripts, out)
    print(f"Wrote {len(files)} files to {out}:")
    for f in files:
        print("  ", f.relative_to(out))
    print("\nNext: run Script Merger if you use other mods, then launch the game with -debugscripts.")


def uninstall(game=None, out=None):
    """Removes the mod folder. The game's own files were never modified, so this restores the base game."""
    import shutil
    out = Path(out) if out else Path(game) / "mods" / MOD_NAME
    if not out.exists():
        print(f"Nothing to remove: {out} does not exist.")
        return False
    if out.name != MOD_NAME:
        raise PatchError(f"Refusing to delete {out}: it is not a {MOD_NAME} folder.")
    shutil.rmtree(out)
    print(f"Removed {out}. The game is back to normal (remove -debugscripts from its launch options if you added it).")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="The Witcher 3 install folder")
    ap.add_argument("--scripts", help="folder holding the vanilla scripts (default: <game>/content/content0/scripts)")
    ap.add_argument("--out", help=f"output mod folder (default: <game>/mods/{MOD_NAME})")
    ap.add_argument("--uninstall", action="store_true", help="remove the mod and return to the base game")
    a = ap.parse_args(argv)
    if a.uninstall:
        if not (a.game or a.out):
            sys.exit("Error: pass --game (or --out) with --uninstall.")
        try:
            uninstall(a.game, a.out)
        except PatchError as e:
            sys.exit(f"Error: {e}")
        return

    if not (a.scripts or a.game):  # started with no arguments, e.g. by double-clicking
        print("Witcher Guide mod installer\n")
        try:
            game = ask_game_dir()
            run(game=game)
        except PatchError as e:
            print(f"\nError: {e}")
        except (OSError, EOFError) as e:
            print(f"\nError: {e}")
        input("\nPress Enter to close this window...")
        return
    try:
        run(a.game, a.scripts, a.out)
    except PatchError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
