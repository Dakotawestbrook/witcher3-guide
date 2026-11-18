"""Launcher for the Witcher 3 guide overlay.

    python witcher_guide.pyw             run the overlay now (no console window)
    python witcher_guide.pyw --watch     stay hidden until the game is running, hide when it exits
    python witcher_guide.pyw --uninstall remove a startup entry from an earlier version (cleanup only)

Nothing here registers itself to start with Windows.
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

GAME_EXE = "witcher3.exe"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "WitcherGuide"
MUTEX_NAME = "Local\\WitcherGuideOverlay"
ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "witcher_guide.pyw"
CREATE_NO_WINDOW = 0x08000000


# ---- pure helpers (unit-tested) ---------------------------------------------
def parse_tasklist(output, exe=GAME_EXE):
    """True if `tasklist /FO CSV /NH` output lists a process named `exe`."""
    for line in output.splitlines():
        first = line.split(",")[0].strip().strip('"')
        if first.lower() == exe.lower():
            return True
    return False


def step(previous, running):
    """Edge-triggered watcher: returns 'show'/'hide' only when the state changes."""
    if running == previous:
        return None
    return "show" if running else "hide"


# ---- Windows-only pieces ----------------------------------------------------
def game_running(exe=GAME_EXE):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return parse_tasklist(out, exe)


def start_watcher(events, exe=GAME_EXE, is_running=game_running, interval=3.0, stop=None):
    """Poll in a background thread and post 'show'/'hide' on game start/exit."""
    stop = stop or threading.Event()

    def loop():
        prev = None
        while not stop.is_set():
            now = is_running(exe)
            ev = step(prev, now)
            if ev:
                events.put(ev)
            prev = now
            stop.wait(interval)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def acquire_single_instance():
    """Returns False if another overlay is already running (Windows only)."""
    if sys.platform != "win32":
        return True
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    acquire_single_instance.handle = handle  # keep alive for the process lifetime
    return not already


def _winreg():
    if sys.platform != "win32":
        raise SystemExit("This command is only supported on Windows.")
    import winreg
    return winreg


def uninstall():
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
        return True
    except FileNotFoundError:
        return False


# ---- entry point -------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Witcher 3 guide overlay launcher")
    ap.add_argument("--watch", action="store_true", help="show only while the game is running")
    ap.add_argument("--process", default=GAME_EXE, help=f"game process name (default {GAME_EXE})")
    ap.add_argument("--uninstall", action="store_true", help="remove a startup entry left by an earlier version")
    a = ap.parse_args(argv)

    if a.uninstall:
        print("Startup entry removed." if uninstall() else "No startup entry was installed.")
        return

    if not acquire_single_instance():
        return  # already running
    from witcher_guide import overlay

    def ready(ov):
        if a.watch and sys.platform == "win32":
            start_watcher(ov.events, a.process)
        elif a.watch:  # dev machines: no tasklist, so just stay visible
            ov.set_visible(True)

    overlay.run(on_ready=ready, start_hidden=a.watch and sys.platform == "win32")


if __name__ == "__main__":
    main()
