import tempfile
import unittest
from pathlib import Path

from witcher_guide import diagnose


def run(path_text=None):
    out = []
    tmp = tempfile.TemporaryDirectory()
    p = Path(tmp.name) / "scriptlog.txt"
    if path_text is not None:
        p.write_text(path_text, encoding="utf-8")
    ok = diagnose.report([p], out=out.append)
    tmp.cleanup()
    return ok, "\n".join(out)


GOOD = ("[Journal] OnQuestEvent q101\n@@WG@@|snapshot|begin\n@@WG@@|q|Lilac and Gooseberries|success\n"
        "@@WG@@|q|The Beast of White Orchard|success\n@@WG@@|q|Some Odd Title|active\n"
        "@@WG@@|snapshot|end\n@@WG@@|tracked|The Incident at White Orchard\n")


class TestDiagnose(unittest.TestCase):
    def test_missing_log(self):
        ok, text = run(None)
        self.assertFalse(ok)
        self.assertIn("No log file", text)

    def test_logging_works_but_mod_silent(self):
        ok, text = run("[Journal] OnQuestEvent q101\nother\n")
        self.assertFalse(ok)
        self.assertIn("the mod wrote nothing", text)

    def test_no_journal_lines_at_all(self):
        ok, text = run("just some noise\n")
        self.assertFalse(ok)
        self.assertIn("no journal lines either", text)

    def test_healthy_log_reports_matches(self):
        ok, text = run(GOOD)
        self.assertIn("2 of 3 distinct titles matched", text)
        self.assertIn("would be marked done: 2", text)
        self.assertIn("Some Odd Title", text)
        self.assertIn("The Incident at White Orchard", text)

    def test_empty_snapshot_is_flagged(self):
        ok, text = run("@@WG@@|snapshot|begin\n@@WG@@|snapshot|end\n")
        self.assertFalse(ok)
        self.assertIn("No quest is reported as 'success'", text)

    def test_untranslated_titles_are_flagged(self):
        ok, text = run("@@WG@@|snapshot|begin\n@@WG@@|q|Nieznany tytul|success\n@@WG@@|snapshot|end\n")
        self.assertFalse(ok)
        self.assertIn("Nothing matched", text)


if __name__ == "__main__":
    unittest.main()
