import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mod"))
import install_mod as im  # noqa: E402

HUD = "\tevent  OnQuestEvent( journalQuest : CJournalQuest )\n\t{\n\t\tLogChannel( 'Journal', \"OnQuestEvent \"+journalQuest.baseName );\n\t\tOnQuestUpdate( journalQuest, true );\n\t}\n"
QUESTS = "\tpublic function OnQuestTrackingStarted( journalQuest : CJournalQuest )\n\t{\n\t\tvar e : SUpdateEvent;\n\t\te.eventType\t\t= EUET_StartedTracking;\n\t\te.delay\t\t\t= 0;\n\t}\n"
PLAYER = "\t\tif(spawnData.restored)\n\t\t{\n\t\t\tApplyPatchFixes();\n\t\t}\n"
FILES = {"game/gui/hud/hud.ws": HUD, "game/gui/hud/modules/hudModuleQuests.ws": QUESTS,
         "game/player/playerWitcher.ws": PLAYER}


class TestInstaller(unittest.TestCase):
    def test_inserts_one_marked_line_after_the_anchor_with_same_indent(self):
        out = im.patch_text("game/gui/hud/hud.ws", HUD)
        lines = out.split("\n")
        i = next(n for n, l in enumerate(lines) if "WG_Snapshot" in l)
        self.assertIn("OnQuestEvent ", lines[i - 1])
        self.assertEqual(lines[i], "\t\tWG_Snapshot(); " + im.MARK)
        self.assertEqual(len(lines), len(HUD.split("\n")) + 1)

    def test_idempotent(self):
        once = im.patch_text("game/gui/hud/hud.ws", HUD)
        self.assertEqual(im.patch_text("game/gui/hud/hud.ws", once), once)

    def test_crlf_files_keep_crlf(self):
        out = im.patch_text("game/player/playerWitcher.ws", PLAYER.replace("\n", "\r\n"))
        self.assertNotIn("\n\n", out.replace("\r\n", ""))
        self.assertEqual(out.count("\r\n"), PLAYER.count("\n") + 1)
        self.assertEqual(out.count("\n"), out.count("\r\n"))

    def test_fails_loudly_when_anchor_missing_or_ambiguous(self):
        with self.assertRaises(im.PatchError):
            im.patch_text("game/gui/hud/hud.ws", "nothing here")
        with self.assertRaises(im.PatchError):
            im.patch_text("game/player/playerWitcher.ws", PLAYER + PLAYER)

    def test_build_preserves_encoding_and_writes_new_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "src", Path(d) / "out"
            for i, (rel, text) in enumerate(FILES.items()):
                p = src / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(im.encode(text, "utf-16") if i == 0 else text.encode("utf-8"))
            written = im.build(src, out)
            self.assertEqual(len(written), 4)
            hud = (out / "content/scripts/game/gui/hud/hud.ws").read_bytes()
            self.assertEqual(hud[:2], b"\xff\xfe")
            self.assertIn("WG_Snapshot", im.decode(hud)[0])
            qm = (out / "content/scripts/game/gui/hud/modules/hudModuleQuests.ws").read_bytes()
            self.assertFalse(qm.startswith(b"\xff\xfe"))
            self.assertIn("WG_LogTracked( journalQuest );", qm.decode())
            self.assertIn("function WG_Snapshot", (out / "content/scripts/game/modWitcherGuide/witcherGuide.ws").read_text())

    def test_build_reports_missing_scripts(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(im.PatchError):
            im.build(Path(d), Path(d) / "out")

    def test_mod_script_defines_every_function_the_patches_call(self):
        ws = (Path(im.__file__).parent / "witcherGuide.ws").read_text()
        for _, stmt in im.PATCHES.values():
            name = stmt.split("(")[0]
            self.assertIn(f"function {name}(", ws)
        # and the script emits the protocol the overlay parses
        from witcher_guide import tracker
        self.assertIn(tracker.PREFIX, ws)
        for part in ("snapshot|begin", "snapshot|end", "|q|", "|tracked|"):
            self.assertIn(part, ws)


if __name__ == "__main__":
    unittest.main()
