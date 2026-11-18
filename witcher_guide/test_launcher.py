import queue
import tempfile
import threading
import unittest
from pathlib import Path

from witcher_guide import launcher


class TestLauncher(unittest.TestCase):
    def test_parse_tasklist(self):
        on = '"witcher3.exe","12345","Console","1","2,000,000 K"\r\n'
        off = "INFO: No tasks are running which match the specified criteria.\r\n"
        self.assertTrue(launcher.parse_tasklist(on))
        self.assertTrue(launcher.parse_tasklist(on.upper()))
        self.assertFalse(launcher.parse_tasklist(off))
        self.assertFalse(launcher.parse_tasklist('"witcher3launcher.exe","1","Console","1","1 K"\r\n'))
        self.assertTrue(launcher.parse_tasklist('"custom.exe","1","Console","1","1 K"', "custom.exe"))

    def test_step_is_edge_triggered(self):
        self.assertEqual(launcher.step(None, True), "show")
        self.assertEqual(launcher.step(None, False), "hide")
        self.assertIsNone(launcher.step(True, True))
        self.assertEqual(launcher.step(True, False), "hide")
        self.assertEqual(launcher.step(False, True), "show")

    def test_run_command(self):
        with tempfile.TemporaryDirectory() as d:
            py = Path(d) / "python.exe"; py.write_text("")
            (Path(d) / "pythonw.exe").write_text("")
            cmd = launcher.run_command(py, watch=True)
            self.assertIn("pythonw.exe", cmd)
            self.assertTrue(cmd.endswith("--watch"))
            self.assertIn("witcher_guide.pyw", cmd)
            self.assertNotIn("--watch", launcher.run_command(py, watch=False))
            self.assertIn("--process foo.exe", launcher.run_command(py, game_exe="foo.exe"))

    def test_pythonw_falls_back_to_python(self):
        with tempfile.TemporaryDirectory() as d:
            py = Path(d) / "python.exe"; py.write_text("")
            self.assertEqual(launcher.pythonw_for(py), py)

    def test_launcher_script_exists(self):
        self.assertTrue(launcher.LAUNCHER.exists())

    def test_watcher_posts_show_then_hide(self):
        states = iter([False, True, True, False])
        done = threading.Event()
        def fake(_exe):
            try:
                return next(states)
            except StopIteration:
                done.set()
                return False
        events = queue.Queue()
        stop = launcher.start_watcher(events, "x.exe", is_running=fake, interval=0.01)
        self.assertTrue(done.wait(2))
        stop.set()
        got = []
        while not events.empty():
            got.append(events.get())
        self.assertEqual(got, ["hide", "show", "hide"])


if __name__ == "__main__":
    unittest.main()
