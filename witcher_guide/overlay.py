"""Always-on-top, click-through overlay for the Witcher 3 guide.

Run the game in *borderless windowed* mode (exclusive fullscreen hides overlays).
Hotkeys (work while the game has focus, Windows only):
    F8  show / hide the overlay
    F9  lock (click-through, game gets the mouse) / unlock (interact with overlay)
    F10 quit the overlay
    F11 switch between a fully transparent overlay and a dark backing panel
The \u2715 button in the title bar also closes it (unlock with F9 first if it is locked).
"""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from witcher_guide import core, tracker

IS_WINDOWS = sys.platform == "win32"

# Every background is KEY, which Windows renders fully transparent (and click-through),
# so only the text and thin outlines are visible. Near-black so anti-aliased text edges look clean.
KEY = "#010101"
BG, FG, DIM = KEY, "#f2e8d0", "#a89d86"
# Colours used instead of KEY when the dark backing panel is switched on (F11).
PANEL = {"base": "#14110f", "head": "#1f1a15", "entry": "#241e18", "alert": "#2a1411", "detail": "#1f1a15"}
PANEL_SELECTED = "#2c2620"
WIDTH = 470
SHORT = {"Hearts of Stone": "Hearts", "Blood and Wine": "Blood&Wine"}  # keep the tab rows from overflowing
GOLD, RED, GREEN, BLUE = "#e8b85a", "#ff6b62", "#7fd685", "#7ab8f0"
ICON = {core.DONE: "✔", core.AVAILABLE: "▶", core.BLOCKED: "○", core.MISSED: "✖"}

# Win32 constants
MOD_NOREPEAT, VK_F8, VK_F9, VK_F10, VK_F11 = 0x4000, 0x77, 0x78, 0x79, 0x7A
WM_HOTKEY = 0x0312
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80


def start_hotkey_thread(events):
    """Register F8/F9 globally and push 'toggle'/'lock' onto `events`."""
    if not IS_WINDOWS:
        return
    import ctypes
    from ctypes import wintypes

    def loop():
        user32 = ctypes.windll.user32
        user32.RegisterHotKey(None, 1, MOD_NOREPEAT, VK_F8)
        user32.RegisterHotKey(None, 2, MOD_NOREPEAT, VK_F9)
        user32.RegisterHotKey(None, 3, MOD_NOREPEAT, VK_F10)
        user32.RegisterHotKey(None, 4, MOD_NOREPEAT, VK_F11)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                events.put({1: "toggle", 2: "lock", 3: "quit", 4: "backdrop"}.get(msg.wParam, "lock"))

    threading.Thread(target=loop, daemon=True).start()


class Overlay:
    def __init__(self, root, data=None, progress=None):
        self.root = root
        self.data = data or core.load_data()
        self.progress = progress or core.Progress()
        self.tracker = tracker.Tracker(self.progress, self.data)
        self.region = None  # None = all regions
        self.locked = False
        self.visible = True
        self.events = queue.Queue()
        self._drag = (0, 0)
        self._roles = {}
        self.transparent = False
        self._settings_path = self.progress.path.parent / "settings.json"
        self.backdrop = self._load_settings().get("backdrop", False)

        root.title("Witcher 3 Guide")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        self._style()
        self._build()
        self.refresh()
        root.update_idletasks()
        root.geometry(f"{WIDTH}x{root.winfo_reqheight()}+30+60")
        self._set_click_through(False)
        self._apply_backdrop()
        start_hotkey_thread(self.events)
        root.after(80, self._poll)

    # ---- UI -------------------------------------------------------------
    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("T.Treeview", background=BG, fieldbackground=BG, foreground=FG,
                    borderwidth=0, rowheight=24, font=("Segoe UI", 10))
        # no selection bar (it would be a solid block): selected rows turn bold white instead
        s.map("T.Treeview", background=[("selected", BG)], foreground=[("selected", "#ffffff")])
        s.layout("T.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # drop the border
        s.configure("T.TCheckbutton", background=BG, foreground=FG, indicatorbackground=BG, focuscolor=BG)
        s.map("T.TCheckbutton", background=[("active", BG)], indicatorbackground=[("active", BG)])

    def _build(self):
        r = self.root
        head = tk.Frame(r, bg=BG)
        head.pack(fill="x")
        self._tag("base", r)
        self.title_lbl = tk.Label(head, text="⚔ Witcher 3 Guide", bg=BG, fg=GOLD,
                                  font=("Segoe UI", 12, "bold"), anchor="w")
        self.title_lbl.pack(side="left", padx=8, pady=6)
        close = tk.Label(head, text="\u2715", bg=BG, fg=DIM, font=("Segoe UI", 12), padx=8, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.quit())
        close.bind("<Enter>", lambda e: close.config(fg=RED))
        close.bind("<Leave>", lambda e: close.config(fg=DIM))
        self.lock_lbl = tk.Label(head, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lock_lbl.pack(side="right", padx=4)
        self._tag("head", head, self.title_lbl, close, self.lock_lbl)
        for w in (head, self.title_lbl):
            w.bind("<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.x_root - r.winfo_x(), e.y_root - r.winfo_y())))
            w.bind("<B1-Motion>", lambda e: r.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}"))

        tabs = tk.Frame(r, bg=BG)
        tabs.pack(fill="x", padx=6, pady=(6, 0))
        self._tag("base", tabs)
        for c in range(5):
            tabs.grid_columnconfigure(c, weight=1, uniform="tab")
        self.tab_btns = {}
        for n, name in enumerate([None] + self.data["regions"]):
            b = tk.Label(tabs, text=SHORT.get(name, name or "All"), bg=BG, fg=DIM, font=("Segoe UI", 9), padx=5, cursor="hand2")
            self._tag("base", b)
            b.grid(row=n // 5, column=n % 5, sticky="w")
            b.bind("<Button-1>", lambda e, n=name: self.set_region(n))
            self.tab_btns[name] = b

        self.track_lbl = tk.Label(r, text="", bg=BG, fg=BLUE, anchor="w", font=("Segoe UI", 9, "bold"))
        self.track_lbl.pack(fill="x", padx=8)
        self._tag("base", self.track_lbl)

        bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=8, pady=6)
        self._tag("base", bar)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        e = tk.Entry(bar, textvariable=self.search_var, bg=BG, fg=FG, insertbackground=FG,
                     relief="flat", bd=0, highlightthickness=1, highlightbackground=DIM,
                     highlightcolor=GOLD, font=("Segoe UI", 10))
        e.pack(side="left", fill="x", expand=True, ipady=3)
        self._tag("entry", e)
        e.bind("<Button-1>", lambda ev: e.focus_force())
        self.miss_var = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Missable only", variable=self.miss_var, style="T.TCheckbutton",
                        command=self.refresh).pack(side="left", padx=(8, 0))

        self.alert_lbl = tk.Label(r, text="", bg=BG, fg=RED, justify="left", anchor="w",
                                  wraplength=WIDTH - 30, font=("Segoe UI", 9, "bold"))
        self.alert_lbl.pack(fill="x", padx=8)
        self._tag("alert", self.alert_lbl)

        self.tree = ttk.Treeview(r, style="T.Treeview", show="tree", selectmode="browse", height=11)
        self.tree.pack(fill="x", padx=8, pady=6)  # fixed rows: no half-cut row at the bottom
        for tag, col in (("done", DIM), ("available", GREEN), ("blocked", FG), ("missed", RED), ("missable", GOLD), ("tracked", BLUE)):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.tree.bind("<Double-1>", self._toggle_selected)

        self.detail = tk.Label(r, text="Double-click a quest to mark it done.", bg=BG, fg=FG,
                               justify="left", anchor="nw", wraplength=WIDTH - 30, font=("Segoe UI", 9), height=8)
        self.detail.pack(fill="x", padx=8, pady=(0, 8))
        self._tag("detail", self.detail)

    # ---- State ----------------------------------------------------------
    def set_region(self, name):
        self.region = name
        self.refresh()

    def refresh(self):
        done, failed = self.progress.all_done(), self.progress.auto_failed
        for n, b in self.tab_btns.items():
            b.config(fg=GOLD if n == self.region else DIM)
        self.tree.delete(*self.tree.get_children())
        rows = core.search(self.data, done, self.search_var.get(), self.region, self.miss_var.get(), failed=failed)
        # recommended next quests float to the top
        rows.sort(key=lambda q: 0 if q["status"] == core.AVAILABLE else 1)
        for q in rows:
            tags = [q["status"]] + (["missable"] if q.get("missable") and q["status"] != core.DONE else [])
            if q["id"] == self.progress.tracked:
                tags.append("tracked")
            star = " ⚠" if q.get("missable") else ""
            mark = "\u25C9" if q["id"] == self.progress.tracked else ICON[q["status"]]
            self.tree.insert("", "end", iid=q["id"], text=f' {mark}  {q["name"]}{star}', tags=tags)
        names = {q["id"]: q["name"] for q in self.data["quests"]}
        t = self.progress.tracked
        self.track_lbl.config(text=f"\u25C9 Tracking in game: {names[t]}" if t in names else "")
        al = core.alerts(self.data, done, failed)
        by_id = {q["id"]: q["name"] for q in self.data["quests"]}
        lost = [a["name"] for a in al if a["status"] == core.MISSED]
        msg = []
        if lost:
            msg.append("MISSED: " + ", ".join(lost[:4]) + ("\u2026" if len(lost) > 4 else ""))
        groups = {}
        for a in al:
            if a["urgent"]:
                groups.setdefault(a["expires_before"], []).append(a["name"])
        for cutoff, names in groups.items():
            msg.append(f"Before {by_id.get(cutoff, cutoff)}: " + ", ".join(names[:3]) +
                       (f" +{len(names) - 3} more" if len(names) > 3 else ""))
        self.alert_lbl.config(text="\n".join(msg[:5]))
        self.alert_lbl.pack_forget() if not msg else self.alert_lbl.pack(fill="x", padx=8, before=self.tree)

    def _quest(self, qid):
        return next((q for q in core.annotate(self.data, self.progress.all_done(), self.progress.auto_failed) if q["id"] == qid), None)

    def _show_detail(self, _e=None):
        sel = self.tree.selection()
        q = self._quest(sel[0]) if sel else None
        if not q:
            return
        lines = [f'{q["name"]}  [{q["region"]} • {q["type"]} • {q["status"]}]']
        miss = core.missing_prereqs(q, self.data, self.progress.all_done())
        if miss and q["status"] == core.BLOCKED:
            lines.append("Do first: " + ", ".join(miss))
        if q.get("notes"):
            lines.append(q["notes"])
        if q.get("warn"):
            lines.append("⚠ " + q["warn"])
        if q.get("source"):
            lines.append("Source: " + q["source"])
        self.detail.config(text="\n".join(lines))

    def _toggle_selected(self, _e=None):
        sel = self.tree.selection()
        if sel:
            self.progress.toggle(sel[0])
            self.refresh()
            if self.tree.exists(sel[0]):
                self.tree.selection_set(sel[0])

    # ---- Overlay behaviour ---------------------------------------------
    def _hwnd(self):
        import ctypes
        return ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

    def _set_click_through(self, on):
        self.locked = on
        self.lock_lbl.config(text="LOCKED (F9 to unlock)" if on else "F8 hide • F9 lock • F10 quit • F11 backdrop")
        if not IS_WINDOWS:
            return
        import ctypes
        u = ctypes.windll.user32
        h = self._hwnd()
        style = u.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style = style | WS_EX_TRANSPARENT if on else style & ~WS_EX_TRANSPARENT
        u.SetWindowLongW(h, GWL_EXSTYLE, style)

    def apply_log_lines(self, lines):
        """Feed game log lines to the tracker and refresh; jump to a newly tracked quest."""
        changes = {c for c in (self.tracker.feed(l) for l in lines) if c}
        if not changes:
            return
        if "tracked" in changes and self.progress.tracked:
            qid = self.progress.tracked
            if not self.tree.exists(qid):  # hidden by a filter: clear filters so it shows
                self.region = None
                self.search_var.set("")
                self.miss_var.set(False)
            self.refresh()
            if self.tree.exists(qid):
                self.tree.selection_set(qid)
                self.tree.see(qid)
                self._show_detail()
        else:
            self.refresh()

    def _tag(self, role, *widgets):
        self._roles.setdefault(role, []).extend(widgets)

    def _load_settings(self):
        try:
            return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(json.dumps({"backdrop": self.backdrop}), encoding="utf-8")
        except OSError:
            pass

    def set_backdrop(self, on):
        self.backdrop = on
        self._apply_backdrop()
        self._save_settings()

    def _apply_backdrop(self):
        """Transparent: every background is KEY (see-through on Windows), only text shows.
        Backdrop: a dark semi-opaque panel behind everything, for bright or busy scenes."""
        on = self.backdrop
        for role, widgets in self._roles.items():
            colour = PANEL[role] if on else KEY
            for w in widgets:
                w.config(bg=colour)
        base = PANEL["base"] if on else KEY
        st = ttk.Style(self.root)
        st.configure("T.Treeview", background=base, fieldbackground=base)
        st.map("T.Treeview", background=[("selected", PANEL_SELECTED if on else KEY)])
        st.configure("T.TCheckbutton", background=base, indicatorbackground=base, focuscolor=base)
        st.map("T.TCheckbutton", background=[("active", base)], indicatorbackground=[("active", base)])
        try:  # Windows only; elsewhere the window simply stays near-black / dark
            self.root.attributes("-transparentcolor", "" if on else KEY)
            self.root.attributes("-alpha", 0.92 if on else 1.0)
            self.transparent = not on
        except tk.TclError:
            self.transparent = False

    def quit(self):
        self.root.destroy()

    def set_visible(self, visible):
        self.visible = visible
        (self.root.deiconify if visible else self.root.withdraw)()

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if isinstance(ev, tuple) and ev[0] == "lines":
                    self.apply_log_lines(ev[1])
                elif ev == "toggle":
                    self.set_visible(not self.visible)
                elif ev == "show":
                    self.set_visible(True)
                elif ev == "hide":
                    self.set_visible(False)
                elif ev == "lock":
                    self._set_click_through(not self.locked)
                elif ev == "backdrop":
                    self.set_backdrop(not self.backdrop)
                elif ev == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(80, self._poll)


def run(on_ready=None, start_hidden=False, track_game=True):
    """Create the overlay and run the Tk loop. `on_ready(overlay)` runs once it exists."""
    root = tk.Tk()
    ov = Overlay(root)
    if start_hidden:
        ov.set_visible(False)
    if not IS_WINDOWS:  # dev fallback: no global hotkeys, so use local keys
        root.bind("<F8>", lambda e: ov.events.put("toggle"))
        root.bind("<F9>", lambda e: ov.events.put("lock"))
        root.bind("<F10>", lambda e: ov.events.put("quit"))
        root.bind("<F11>", lambda e: ov.events.put("backdrop"))
    root.bind("<Escape>", lambda e: root.destroy())
    if track_game:
        tracker.start_tracking(ov.events)
    if on_ready:
        on_ready(ov)
    root.mainloop()


def main():
    run()


if __name__ == "__main__":
    main()
