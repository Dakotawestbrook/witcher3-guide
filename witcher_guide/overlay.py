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
WIDTH = 470  # default width
MIN_W = 400
EDGE = 6  # px band along each edge (and corner) that resizes the window
ROW_H = 24  # list row height in px (matches the Treeview style)
MIN_ROWS = 3  # list rows at the smallest size
DEFAULT_EXTRA_ROWS, MAX_EXTRA_ROWS = 8, 60  # rows added on top of MIN_ROWS
DETAIL_LINES = 7  # detail text taller than this collapses behind a clickable 'more'
DETAIL_LINES_DECISION = 12  # decisions are longer, so show more before collapsing
DECISIONS = "__decisions__"  # the special tab that lists decisions instead of quests
EMPTY = "__empty__"  # id of the placeholder row shown when nothing matches
MENU_BG, MENU_ACTIVE = "#1f1a15", "#3a2f22"
HELP_TEXT = """Quick guide
\u2022 Click a tab to switch region. The \u2696 Decisions tab lists the best choices.
\u2022 Double-click a quest, or press Space, to mark it done. Finished quests are ticked automatically if the in-game mod is installed.
\u2022 "Show" filters the list (to do, available now, missable, done). In Decisions, "Best for" picks what to favour.
\u2022 Click a warning to expand it. Click the \u25C9 hint to jump to the decision in the quest you're tracking.
\u2022 Right-click anywhere, or click \u2261, for the menu.
\u2022 Drag the title or any blank space to move the window. Drag an edge or \u25E2 to resize.
Keys: F1 this help \u2022 F8 hide/show \u2022 F9 lock (click-through) \u2022 F10 quit \u2022 F11 dark background
In the window: / search \u2022 Esc clear search \u2022 Down from search jumps to the list \u2022 Ctrl+Left/Right switch tabs"""
INTRO_TEXT = "Click a quest for details. Double-click or press Space to mark it done. Press F1 or right-click for help."
SHORT = {"Hearts of Stone": "Hearts", "Blood and Wine": "Blood&Wine"}  # keep the tab rows from overflowing
GOLD, RED, GREEN, BLUE = "#e8b85a", "#ff6b62", "#7fd685", "#7ab8f0"
ICON = {core.DONE: "✔", core.AVAILABLE: "▶", core.BLOCKED: "○", core.MISSED: "✖"}

# Win32 constants
MOD_NOREPEAT, VK_F8, VK_F9, VK_F10, VK_F11 = 0x4000, 0x77, 0x78, 0x79, 0x7A
WM_HOTKEY = 0x0312
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
# Almost-invisible window behind the overlay. Clicks on the see-through parts land on it instead of
# falling through to the game, so they don't change which window has focus.
BACKING_ALPHA = 0.02


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
    def __init__(self, root, data=None, progress=None, backing=None, decisions=None):
        self.root = root
        self.data = data or core.load_data()
        self.decisions = core.load_decisions() if decisions is None else decisions
        self.goal = "all"  # what the Decisions tab is optimising for: all / rewards / morals / outcome
        self._detail_limit = DETAIL_LINES
        self._hint_vis = {"risk": False, "dec": False, "legend": False}
        self.progress = progress or core.Progress()
        self.tracker = tracker.Tracker(self.progress, self.data)
        self.region = None  # None = all regions
        self.locked = False
        self.visible = True
        self.events = queue.Queue()
        self._action = None  # the drag in progress: ('move', offset) or ('resize', state)
        self._roles = {}
        self.transparent = False
        self._settings_path = self.progress.path.parent / "settings.json"
        st = self._load_settings()
        self.backdrop = st.get("backdrop", False)
        self.view = st.get("view", "all") if st.get("view") in core.VIEWS else "all"
        self._tip_win, self._tip_job, self._tab_tips = None, None, {}
        self._hover_row = None
        self.width = self._clamp_width(st.get("width", WIDTH))
        self.extra_rows = self._clamp_rows(st.get("extra_rows", DEFAULT_EXTRA_ROWS))
        self.back = None  # the click-catching window, created below
        self._open = set()  # which truncated texts the user has expanded: alerts / risk / detail
        self._ready = False
        self._detail_text = ""
        self._last_banners = ([], [])
        self._want_backing = IS_WINDOWS if backing is None else backing

        root.title("Witcher 3 Guide")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        self._style()
        self._build()
        self.refresh()
        root.update_idletasks()
        root.geometry(f"{self.width}x{root.winfo_reqheight() + self.extra_rows * ROW_H}+30+60")
        self._ready = True
        if self._want_backing:
            self._make_backing()
        for ev, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag_motion),
                       ("<ButtonRelease-1>", self._release), ("<Motion>", self._hover), ("<Leave>", self._hover_end)):
            root.bind(ev, fn, add="+")
        self._set_click_through(False)
        self._apply_backdrop()
        self._build_menus()
        self._bind_shortcuts()
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
        self.prog_lbl = tk.Label(head, text="", bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.prog_lbl.pack(side="left")
        close = tk.Label(head, text="\u2715", bg=BG, fg=DIM, font=("Segoe UI", 12), padx=8, cursor="hand2")
        close.pack(side="right", padx=(0, EDGE))
        close.bind("<Button-1>", lambda e: self.quit())
        close.bind("<Enter>", lambda e: close.config(fg=RED))
        close.bind("<Leave>", lambda e: close.config(fg=DIM))
        self.menu_btn = tk.Label(head, text="\u2261", bg=BG, fg=GOLD, font=("Segoe UI", 15), padx=6, cursor="hand2")
        self.menu_btn.pack(side="right")
        self.menu_btn.bind("<Button-1>", lambda e: self._popup(self.menu, self.menu_btn))
        self.lock_lbl = tk.Label(head, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lock_lbl.pack(side="right", padx=4)
        self._tag("head", head, self.title_lbl, self.prog_lbl, close, self.menu_btn, self.lock_lbl)
        self._tip(self.menu_btn, "Menu: help, lock, dark background, reset. Right-click anywhere also opens it.")
        self._tip(close, "Close the overlay (F10)")
        self._tip(self.prog_lbl, "Quests ticked off in this tab / all quests")
        for w in (head, self.title_lbl, self.prog_lbl):  # drag to move the window (unless the pointer is on an edge)
            w.bind("<ButtonPress-1>", lambda e: self._press(e, movable=True))
            w.bind("<B1-Motion>", self._drag_motion)
            w.bind("<ButtonRelease-1>", self._release)
        head.bind("<Motion>", self._hover)
        head.bind("<Leave>", self._hover_end)

        tabs = self._tabs = tk.Frame(r, bg=BG)
        tabs.pack(fill="x", padx=6, pady=(6, 0))
        self._tag("base", tabs)
        self.tab_btns = {}
        for name in [None] + self.data["regions"]:
            b = tk.Label(tabs, text=SHORT.get(name, name or "All"), bg=BG, fg=DIM, font=("Segoe UI", 9), padx=5, cursor="hand2")
            self._tag("base", b)
            b.bind("<Button-1>", lambda e, n=name: self.set_region(n))
            self.tab_btns[name] = b
        dtab = tk.Label(tabs, text="\u2696 Decisions: best choices", bg=BG, fg=DIM, font=("Segoe UI", 9, "bold"), padx=5, cursor="hand2")
        self._tag("base", dtab)
        dtab.bind("<Button-1>", lambda e: self.set_region(DECISIONS))
        self.tab_btns[DECISIONS] = dtab
        for name, b in self.tab_btns.items():
            self._tip(b, lambda n=name: self._tab_tips.get(n, ""))
        self._layout_tabs()

        self.track_lbl = tk.Label(r, text="", bg=BG, fg=BLUE, anchor="w", font=("Segoe UI", 9, "bold"))
        self.track_lbl.pack(fill="x", padx=8)
        self._tag("base", self.track_lbl)
        self.hints = tk.Frame(r, bg=BG)  # holds the warnings/hints; it is only packed while it has content
        self._tag("base", self.hints)
        # shown only while the tracked quest would close a missable quest you haven't finished
        self.risk_lbl = tk.Label(self.hints, text="", bg=BG, fg=RED, justify="left", anchor="w",
                                 wraplength=self.width - 30, font=("Segoe UI", 10, "bold"))
        self.risk_lbl.bind("<Button-1>", lambda e: self._toggle("risk"))
        self._tag("alert", self.risk_lbl)
        # shown while the tracked quest contains a decision; click to see the best choices
        self.dec_lbl = tk.Label(self.hints, text="", bg=BG, fg=GOLD, justify="left", anchor="w", cursor="hand2",
                                wraplength=self.width - 30, font=("Segoe UI", 9, "bold"))
        self.dec_lbl.bind("<Button-1>", lambda e: self._goto_decision())
        self._tag("base", self.dec_lbl)
        self.legend_lbl = tk.Label(self.hints, text="\u21C4 = best for rewards and best for morals differ. Click \"Best for\" to filter.",
                                   bg=BG, fg=DIM, justify="left", anchor="w", wraplength=self.width - 30, font=("Segoe UI", 8))
        self._tag("base", self.legend_lbl)

        bar = self.bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=8, pady=6)
        self._tag("base", bar)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_search())
        e = self.search_entry = tk.Entry(bar, textvariable=self.search_var, bg=BG, fg=FG, insertbackground=FG,
                                         relief="flat", bd=0, highlightthickness=1, highlightbackground=DIM,
                                         highlightcolor=GOLD, font=("Segoe UI", 10))
        e.pack(side="left", fill="x", expand=True, ipady=3)
        self._tag("entry", e)
        e.bind("<Button-1>", lambda ev: e.focus_force())
        # a hint inside the empty box, and a clear button once something is typed
        self.ph_lbl = tk.Label(e, text="", bg=BG, fg=DIM, font=("Segoe UI", 10, "italic"), cursor="xterm")
        self.ph_lbl.place(x=6, rely=0.5, anchor="w")
        self.ph_lbl.bind("<Button-1>", lambda ev: e.focus_force())
        self.clear_btn = tk.Label(e, text="\u2715", bg=BG, fg=DIM, font=("Segoe UI", 9), cursor="hand2", padx=4)
        self.clear_btn.bind("<Button-1>", lambda ev: self._clear_search())
        self._tag("entry", self.ph_lbl, self.clear_btn)
        self._tip(self.clear_btn, "Clear the search (Esc)")
        # drop-down buttons: one for quests (Show) and one for the Decisions tab (Best for)
        self.view_lbl = self._pill(bar, lambda: f"Show: {core.VIEW_LABELS[self.view]} \u25BE",
                                   lambda: self._popup(self.view_menu, self.view_lbl),
                                   "Choose which quests the list shows")
        self.goal_lbl = self._pill(bar, lambda: f"Best for: {core.GOAL_LABELS[self.goal]} \u25BE",
                                   lambda: self._popup(self.goal_menu, self.goal_lbl),
                                   "What the recommended choice should favour")
        self.view_lbl.pack(side="left", padx=(8, 0))

        self.alert_lbl = tk.Label(r, text="", bg=BG, fg=RED, justify="left", anchor="w",
                                  wraplength=self.width - 30, font=("Segoe UI", 9, "bold"))
        self.alert_lbl.pack(fill="x", padx=8)
        self.alert_lbl.bind("<Button-1>", lambda e: self._toggle("alerts"))
        self._tag("alert", self.alert_lbl)

        self.tree = ttk.Treeview(r, style="T.Treeview", show="tree", selectmode="browse", height=MIN_ROWS)
        # The list takes whatever height is left. The window height is always a whole number of
        # rows (see _fit), so there is never a half-cut row at the bottom.
        self.tree.pack(fill="both", expand=True, padx=8, pady=6)
        for tag, col in (("empty", DIM), ("done", DIM), ("available", GREEN), ("blocked", FG), ("missed", RED), ("missable", GOLD), ("tracked", BLUE), ("atrisk", RED)):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.tag_configure("hover", foreground="#ffffff")  # last, so it wins over the status colours
        self.tree.bind("<Motion>", lambda e: self._set_hover_row(self.tree.identify_row(e.y) or None))
        self.tree.bind("<Leave>", lambda e: self._set_hover_row(None))
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.tree.bind("<Double-1>", self._toggle_selected)
        self.tree.bind("<Return>", self._toggle_selected)
        self.tree.bind("<space>", self._toggle_selected)

        self.detail = tk.Text(r, bg=BG, fg=FG, wrap="word", height=3, relief="flat", bd=0,
                              highlightthickness=0, font=("Segoe UI", 9), cursor="arrow", padx=0, pady=0,
                              takefocus=0, state="disabled")
        self.detail.pack(fill="x", padx=8)
        self.more_lbl = tk.Label(r, text="", bg=BG, fg=BLUE, anchor="w", font=("Segoe UI", 9, "bold"))
        self.more_lbl.bind("<Button-1>", lambda e: self._toggle("detail"))
        self.more_lbl.pack(fill="x", padx=8, pady=(0, 8))
        self._tag("detail", self.detail, self.more_lbl)
        for tag, col in (("rewards", GOLD), ("morals", GREEN), ("outcome", BLUE), ("warnline", RED)):
            self.detail.tag_configure(tag, foreground=col)
        self.detail.tag_configure("title", font=("Segoe UI", 9, "bold"))
        self._set_detail(INTRO_TEXT)

        # drag this corner to resize the window
        self.grip = tk.Label(r, text="\u25E2", bg=BG, fg=DIM, font=("Segoe UI", 11), cursor=self._cursor_for({"r", "b"}))
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<ButtonPress-1>", lambda e: self._begin_resize(e, {"r", "b"}))
        self.grip.bind("<B1-Motion>", self._drag_motion)
        self.grip.bind("<ButtonRelease-1>", self._release)
        self._tag("base", self.grip)

    # ---- State ----------------------------------------------------------
    def set_region(self, name):
        self.region = name
        self.refresh()

    def refresh(self):
        done, failed = self.progress.all_done(), self.progress.auto_failed
        risks = core.tracked_risks(self.data, done, failed, self.progress.tracked_all)
        risk_ids = {q["id"] for q in risks}
        self._update_tabs()
        self._hover_row = None
        self.tree.delete(*self.tree.get_children())
        in_decisions = self.region == DECISIONS
        self._set_mode_controls(in_decisions)
        dec_quests = {qid for d in self.decisions for qid in d["quests"]}
        rows = [] if in_decisions else core.apply_view(
            core.search(self.data, done, self.search_var.get(), self.region, False, failed=failed), self.view)
        if in_decisions:
            self._fill_decisions()
        # recommended next quests float to the top
        rows.sort(key=lambda q: 0 if q["status"] == core.AVAILABLE else 1)
        for q in rows:
            tags = [q["status"]] + (["missable"] if q.get("missable") and q["status"] != core.DONE else [])
            if q["id"] == self.progress.tracked:
                tags.append("tracked")
            if q["id"] in risk_ids:
                tags.append("atrisk")
            star = " ⚠" if q.get("missable") else ""
            if q["id"] in dec_quests:
                star += " \u2696"  # this quest contains a decision
            if q["id"] in risk_ids:
                star = " \u203C will be lost"
            mark = "\u25C9" if q["id"] == self.progress.tracked else ICON[q["status"]]
            self.tree.insert("", "end", iid=q["id"], text=f' {mark}  {q["name"]}{star}', tags=tags)
        if not self.tree.get_children():  # nothing to show: say why, and how to fix it
            what = "decisions" if in_decisions else "quests"
            self.tree.insert("", "end", iid=EMPTY, tags=["empty"], text=f"  No {what} match. " + (
                "Clear the search or change \"Best for\"." if in_decisions else
                "Clear the search or change \"Show\"."))
        names = {q["id"]: q["name"] for q in self.data["quests"]}
        t = self.progress.tracked
        self.track_lbl.config(text=f"\u25C9 Tracking in game: {names[t]}" if t in names else "")
        decs = core.decisions_for(self.decisions, self.progress.tracked_all)
        if decs:
            self.dec_lbl.config(text="\u2696 Decision in this quest: " + ", ".join(d["name"] for d in decs)
                                     + ". Click for the best choices.")
        self._hint_vis["dec"] = bool(decs)
        self._hint_vis["legend"] = in_decisions
        self._render_banners(core.alerts(self.data, done, failed), risks)

    # ---- Decisions tab ------------------------------------------------------
    def _set_mode_controls(self, in_decisions):
        """The Show filter belongs to quests; the Best-for filter belongs to decisions."""
        self.view_lbl.config(text=f"Show: {core.VIEW_LABELS[self.view]} \u25BE")
        self.goal_lbl.config(text=f"Best for: {core.GOAL_LABELS[self.goal]} \u25BE")
        self.ph_lbl.config(text="Search decisions..." if in_decisions else "Search quests...")
        if in_decisions and not self.goal_lbl.winfo_manager():
            self.view_lbl.pack_forget()
            self.goal_lbl.pack(side="left", padx=(8, 0))
        elif not in_decisions and self.goal_lbl.winfo_manager():
            self.goal_lbl.pack_forget()
            self.view_lbl.pack(side="left", padx=(8, 0))

    def _fill_decisions(self):
        tracked = set(self.progress.tracked_all)
        rows = core.filter_decisions(self.decisions, self.search_var.get(), self.goal)
        rows.sort(key=lambda d: 0 if set(d["quests"]) & tracked else 1)  # the tracked quest's decisions first
        for d in rows:
            conflict = core.has_conflict(d)
            tags = (["missable"] if conflict else []) + (["tracked"] if set(d["quests"]) & tracked else [])
            suffix = ("  \u21C4" if conflict else "") + ("  \u2022 ending" if d.get("affects_ending") else "") + (
                "  \u2022 gwent" if d["kind"] == "gwent" and "gwent" not in d["name"].lower() else "")
            self.tree.insert("", "end", iid="dec:" + d["id"], text=f' \u2696  {d["name"]}{suffix}', tags=tags)

    def _cycle_goal(self):
        self._set_goal(core.GOALS[(core.GOALS.index(self.goal) + 1) % len(core.GOALS)])

    def _set_goal(self, goal):
        self.goal = goal
        if hasattr(self, "goal_var"):
            self.goal_var.set(goal)
        sel = self.tree.selection()
        self.refresh()
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
            self._show_detail()

    def _set_view(self, view):
        self.view = view
        if hasattr(self, "view_var"):
            self.view_var.set(view)
        self._save_settings()
        self.refresh()

    def _goto_decision(self):
        """Jump from the tracked quest's hint to its decision in the Decisions tab."""
        decs = core.decisions_for(self.decisions, self.progress.tracked_all)
        if not decs:
            return
        self.region = DECISIONS
        self.search_var.set("")
        self.refresh()
        iid = "dec:" + decs[0]["id"]
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._show_detail()

    def _layout_hints(self):
        for w in (self.risk_lbl, self.dec_lbl, self.legend_lbl):
            w.pack_forget()
        vis = self._hint_vis
        if not any(vis.values()):
            self.hints.pack_forget()
            return
        if not self.hints.winfo_manager():
            self.hints.pack(fill="x", before=self.bar)
        if vis["risk"]:
            self.risk_lbl.pack(fill="x", padx=8, pady=(2, 0))
        if vis["dec"]:
            self.dec_lbl.pack(fill="x", padx=8, pady=(2, 0))
        if vis["legend"]:
            self.legend_lbl.pack(fill="x", padx=8, pady=(2, 0))

    # ---- Warnings, and text that can be expanded when it doesn't fit ---------
    def _clip(self, key, names, limit):
        """Join names. Past `limit`, show a clickable summary that expands to the full list."""
        if len(names) <= limit:
            return ", ".join(names), False
        if key in self._open:
            return ", ".join(names) + "  \u25B2 show less", True
        return ", ".join(names[:limit]) + f"  \u25BC +{len(names) - limit} more (click)", True

    def _render_banners(self, alerts, risks):
        self._last_banners = (alerts, risks)
        by_id = {q["id"]: q["name"] for q in self.data["quests"]}
        msg, clipped = [], False
        lost = [a["name"] for a in alerts if a["status"] == core.MISSED]
        if lost:
            text, c = self._clip("alerts", lost, 4)
            msg.append("MISSED: " + text)
            clipped |= c
        groups = {}
        for a in alerts:
            if a["urgent"]:
                groups.setdefault(a["expires_before"], []).append(a["name"])
        for cutoff, names in groups.items():
            if cutoff in self.progress.tracked_all:
                continue  # the red tracking warning below already lists these
            text, c = self._clip("alerts", names, 3)
            msg.append(f"Before {by_id.get(cutoff, cutoff)}: " + text)
            clipped |= c
        self.alert_lbl.config(text="\n".join(msg), cursor="hand2" if clipped else "arrow")
        if msg:
            self.alert_lbl.pack(fill="x", padx=8, before=self.tree)
        else:
            self.alert_lbl.pack_forget()

        if risks:
            text, c = self._clip("risk", [q["name"] for q in risks], 4)
            tracked = by_id.get(self.progress.tracked, "this quest")
            self.risk_lbl.config(text=f"\u26A0 You are tracking {tracked}. Starting it will make you miss: "
                                      f"{text}. Finish those first.", cursor="hand2" if c else "arrow")
        self._hint_vis["risk"] = bool(risks)
        self._layout_hints()
        self._fit()

    def _toggle(self, key):
        self._open ^= {key}
        if key == "detail":
            self._set_detail(self._detail_text, self._detail_limit)
        else:
            self._render_banners(*self._last_banners)

    def _set_detail(self, text, limit=DETAIL_LINES):
        """Show text in full if it fits; otherwise collapse it with a clickable 'more'."""
        self._detail_text, self._detail_limit = text, limit
        d = self.detail
        d.config(state="normal")
        d.delete("1.0", "end")
        d.insert("1.0", text)
        for i, line in enumerate(text.split("\n"), 1):  # colour the recommendation lines
            tag = ("title" if i == 1 else "rewards" if line.startswith("Best for rewards") else
                   "morals" if line.startswith("Best for morals") else
                   "outcome" if line.startswith("Best for the outcome") else
                   "warnline" if line.startswith("\u26A0") else None)
            if tag:
                d.tag_add(tag, f"{i}.0", f"{i}.end")
        d.config(state="disabled")
        self.root.update_idletasks()
        count = d.count("1.0", "end", "displaylines")
        n = max(1, count[0] if count else 1)
        over, open_ = n > limit, "detail" in self._open
        d.config(height=n if (open_ or not over) else limit)
        if over:
            self.more_lbl.config(text="\u25B2 show less" if open_ else
                                 f"\u25BC {n - limit} more line{'s' if n - limit > 1 else ''} (click to expand)", cursor="hand2")
        else:
            self.more_lbl.config(text="", cursor="arrow")
        self._fit()

    def _fit(self):
        """Keep the window at its content's minimum height plus the rows the user added, so
        expanded text is never cut off and the list always shows whole rows."""
        if not self._ready:
            return
        self.root.update_idletasks()
        h = self.root.winfo_reqheight() + self.extra_rows * ROW_H
        if (self.width, h) != (self.root.winfo_width(), self.root.winfo_height()):
            self.root.geometry(f"{self.width}x{h}")  # size only: the position is kept
        self.grip.lift()

    # ---- Resizing ---------------------------------------------------------------
    @staticmethod
    def _clamp_width(w):
        try:
            return max(MIN_W, int(w))
        except (TypeError, ValueError):
            return WIDTH

    @staticmethod
    def _clamp_rows(n):
        try:
            return min(max(0, int(n)), MAX_EXTRA_ROWS)
        except (TypeError, ValueError):
            return DEFAULT_EXTRA_ROWS

    @staticmethod
    def _cursor_for(edges):
        """Mouse cursor for the edges being grabbed (Windows and X11 use different names)."""
        e = set(edges)
        if not e:
            return ""
        horiz, vert = bool(e & {"l", "r"}), bool(e & {"t", "b"})
        if horiz and vert:
            nwse = e in ({"l", "t"}, {"r", "b"})
            if IS_WINDOWS:
                return "size_nw_se" if nwse else "size_ne_sw"
            return "bottom_right_corner" if nwse else "bottom_left_corner"
        if horiz:
            return "size_we" if IS_WINDOWS else "sb_h_double_arrow"
        return "size_ns" if IS_WINDOWS else "sb_v_double_arrow"

    def _edges_at(self, x_root, y_root):
        """Which window edges the pointer is within EDGE px of (empty set: none)."""
        rx, ry = x_root - self.root.winfo_rootx(), y_root - self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if not (0 <= rx < w and 0 <= ry < h):
            return set()
        return ({"l"} if rx < EDGE else set()) | ({"r"} if rx >= w - EDGE else set()) | \
               ({"t"} if ry < EDGE else set()) | ({"b"} if ry >= h - EDGE else set())

    def _own_event(self, e):
        """Events bubble up from child widgets; only the window's own margins count here."""
        return e.widget is self.root or e.widget is self.back

    def _hover(self, e):
        if e.widget is self.root or e.widget is self.back or str(e.widget) == str(self.title_lbl.master):
            edges = self._edges_at(e.x_root, e.y_root)
            cursor = self._cursor_for(edges)
            if e.widget is self.back:
                target = None if edges else self._interactive_at(e.x_root, e.y_root)
                if target is not None and not cursor:
                    cursor = str(target.cget("cursor"))  # e.g. the hand over tabs and buttons
                self._set_hover_row(self._row_at(e.x_root, e.y_root) if target is self.tree else None)
            try:
                e.widget.config(cursor=cursor)
            except tk.TclError:
                pass

    def _hover_end(self, e):
        if e.widget is self.back:
            self._set_hover_row(None)
        if self._own_event(e) or str(e.widget) == str(self.title_lbl.master):
            try:
                e.widget.config(cursor="")  # children inherit a parent's cursor, so always reset
            except tk.TclError:
                pass

    def _press(self, e, movable=False):
        if not movable and not self._own_event(e):
            return
        edges = self._edges_at(e.x_root, e.y_root)
        target = None if (edges or e.widget is not self.back) else self._interactive_at(e.x_root, e.y_root)
        if edges:
            self._begin_resize(e, edges)
        elif target is not None:
            self._forward_click(target, e)
        else:
            # The window's own blank areas (the see-through gaps, handled by the backing window in
            # transparent mode) move it, so you can grab it anywhere that isn't a control.
            self._action = ("move", (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()))

    # ---- Clicks on the see-through parts of controls ---------------------------------------------
    # In transparent mode only the letters are opaque, so a click between two letters (or on the empty
    # end of a row) lands on the invisible window behind the overlay. That window finds the control
    # whose rectangle contains the pointer and hands it the click, so every row, tab and button is
    # clickable across its whole area.
    @staticmethod
    def _clickable(w):
        if isinstance(w, (ttk.Treeview, tk.Entry)):
            return True
        return bool(w.bind("<Button-1>") or w.bind("<ButtonPress-1>"))

    def _interactive_at(self, x, y):
        """The innermost clickable widget whose rectangle contains the screen point (x, y), or None."""
        best = None

        def walk(parent):
            nonlocal best
            for c in parent.winfo_children():
                if isinstance(c, tk.Toplevel) or not c.winfo_ismapped():
                    continue
                cx, cy = c.winfo_rootx(), c.winfo_rooty()
                if cx <= x < cx + c.winfo_width() and cy <= y < cy + c.winfo_height():
                    if self._clickable(c):
                        best = c
                    walk(c)

        walk(self.root)
        return best

    def _forward_click(self, target, e):
        lx, ly = e.x_root - target.winfo_rootx(), e.y_root - target.winfo_rooty()
        self._action = None
        target.event_generate("<ButtonPress-1>", x=lx, y=ly, rootx=e.x_root, rooty=e.y_root)
        if self._action is None:  # a plain click: finish it. (A drag that the control started must continue.)
            target.event_generate("<ButtonRelease-1>", x=lx, y=ly, rootx=e.x_root, rooty=e.y_root)
        if isinstance(target, (ttk.Treeview, tk.Entry)):
            target.focus_force()  # so Space/Enter/typing work, as after clicking a visible row

    def _double_click(self, e):
        """A double-click on the backing window: on a list row it ticks the quest, like the list's own."""
        if self._edges_at(e.x_root, e.y_root):
            return self._press(e)
        target = self._interactive_at(e.x_root, e.y_root)
        if target is self.tree:
            self._forward_click(target, e)
            self._toggle_selected()
        else:
            self._press(e)

    def _set_hover_row(self, iid):
        """Brighten the row under the pointer, so you can see what a click will hit."""
        old = self._hover_row
        if iid == old:
            return
        for row, add in ((old, False), (iid, True)):
            if row and row != EMPTY and self.tree.exists(row):
                tags = [t for t in self.tree.item(row, "tags") if t != "hover"]
                self.tree.item(row, tags=tags + (["hover"] if add else []))
        self._hover_row = iid

    def _row_at(self, x, y):
        """The list row under a screen point, or None."""
        t = self.tree
        if not (t.winfo_rootx() <= x < t.winfo_rootx() + t.winfo_width()
                and t.winfo_rooty() <= y < t.winfo_rooty() + t.winfo_height()):
            return None
        return t.identify_row(y - t.winfo_rooty()) or None

    def _begin_resize(self, e, edges):
        self._action = ("resize", dict(
            edges=set(edges), x0=e.x_root, y0=e.y_root, win_x=self.root.winfo_x(), win_y=self.root.winfo_y(),
            w0=self.width, h0=self.root.winfo_reqheight() + self.extra_rows * ROW_H))

    def _drag_motion(self, e):
        if not self._action:
            return
        kind, state = self._action
        if kind == "move":
            self.root.geometry(f"+{e.x_root - state[0]}+{e.y_root - state[1]}")
        else:
            self._do_resize(e, state)

    def _release(self, e):
        if self._action and self._action[0] == "resize":
            self._save_size()
        self._action = None

    def _do_resize(self, e, st):
        """Resize from any edge or corner. Left/top edges also move the window so the opposite
        side stays put. Width is free (>= MIN_W); height changes in whole list rows."""
        need = self.root.winfo_reqheight()  # the content's minimum height
        dx, dy, ed = e.x_root - st["x0"], e.y_root - st["y0"], st["edges"]
        w, x, y, rows = st["w0"], st["win_x"], st["win_y"], self.extra_rows
        if "r" in ed:
            w = st["w0"] + dx
        if "l" in ed:
            w = st["w0"] - dx
        w = self._clamp_width(w)
        if "l" in ed:
            x = st["win_x"] + st["w0"] - w
        if "b" in ed:
            rows = self._clamp_rows(round((st["h0"] + dy - need) / ROW_H))
        if "t" in ed:
            rows = self._clamp_rows(round((st["h0"] - dy - need) / ROW_H))
        h = need + rows * ROW_H
        if "t" in ed:
            y = st["win_y"] + st["h0"] - h
        if (w, rows) == (self.width, self.extra_rows) and (x, y) == (self.root.winfo_x(), self.root.winfo_y()):
            return
        widened = w != self.width
        self.width, self.extra_rows = w, rows
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.grip.lift()
        if widened:
            self._reflow()

    def _layout_tabs(self):
        """Flow the tabs like wrapping text: each takes its own width, and a new row starts when the
        next one would not fit. A wide window gets one row, a narrow one several."""
        self.root.update_idletasks()  # label widths are only known after their text was applied
        order = [self.tab_btns[n] for n in [None] + self.data["regions"]] + [self.tab_btns[DECISIONS]]
        avail, x, y = self.width - 12, 0, 0
        row_h = max(b.winfo_reqheight() for b in order)
        for b in order:
            w = b.winfo_reqwidth()
            if x and x + w > avail:
                x, y = 0, y + row_h
            b.place(x=x, y=y)
            x += w
        self._tabs.config(height=y + row_h)

    def _update_hint_text(self):
        """The header's key hints, shortened (or dropped) when the window is too narrow."""
        if self.locked:
            text = "LOCKED (F9 to unlock)" if self.width >= 440 else "LOCKED (F9)"
        elif self.width >= 600:
            text = "F1 help \u2022 F8 hide \u2022 F9 lock \u2022 F10 quit \u2022 F11 backdrop"
        elif self.width >= 470:
            text = "F1 help \u2022 F8 hide \u2022 F9 lock"
        else:
            text = "F1 help"
        self.lock_lbl.config(text=text)
        if hasattr(self, "lock_var"):
            self.lock_var.set(self.locked)

    def _reflow(self):
        """The width changed: move everything to suit it (tabs, header hint, wrapping, detail lines)."""
        self._update_tabs()
        self._update_hint_text()
        for lbl in (self.alert_lbl, self.risk_lbl, self.dec_lbl, self.legend_lbl):
            lbl.config(wraplength=self.width - 30)
        self._render_banners(*self._last_banners)
        self._set_detail(self._detail_text, self._detail_limit)

    def _save_size(self):
        self._save_settings()

    def _quest(self, qid):
        return next((q for q in core.annotate(self.data, self.progress.all_done(), self.progress.auto_failed) if q["id"] == qid), None)

    def _show_detail(self, _e=None):
        sel = self.tree.selection()
        if sel and sel[0] == EMPTY:
            return
        if sel and sel[0].startswith("dec:"):
            d = next((x for x in self.decisions if "dec:" + x["id"] == sel[0]), None)
            if d:
                self._open.discard("detail")
                self._set_detail(core.format_decision(d, self.goal), DETAIL_LINES_DECISION)
            return
        q = self._quest(sel[0]) if sel else None
        if not q:
            return
        lines = [f'{q["name"]}  [{q["region"]} • {q["type"]} • {q["status"]}]']
        decs = core.decisions_for(self.decisions, [q["id"]])
        if decs:
            lines.append("\u2696 Decision here: " + ", ".join(d["name"] for d in decs) + " (see the Decisions tab)")
        miss = core.missing_prereqs(q, self.data, self.progress.all_done())
        if miss and q["status"] == core.BLOCKED:
            lines.append("Do first: " + ", ".join(miss))
        if q.get("notes"):
            lines.append(q["notes"])
        if q.get("warn"):
            lines.append("⚠ " + q["warn"])
        if q.get("source"):
            lines.append("Source: " + q["source"])
        self._open.discard("detail")  # a newly selected quest starts collapsed
        self._set_detail("\n".join(lines))

    def _toggle_selected(self, _e=None):
        sel = self.tree.selection()
        if sel and sel[0] != EMPTY and not sel[0].startswith("dec:"):  # decisions are advice, not something to tick off
            self.progress.toggle(sel[0])
            self.refresh()
            if self.tree.exists(sel[0]):
                self.tree.selection_set(sel[0])


    # ---- Menus, tooltips and shortcuts ---------------------------------------------------
    def _pill(self, parent, text_fn, command, tip):
        """A small bordered button that looks clickable (used for the drop-down filters)."""
        b = tk.Label(parent, text=text_fn(), bg=BG, fg=GOLD, font=("Segoe UI", 9, "bold"), cursor="hand2",
                     padx=8, pady=2, highlightthickness=1, highlightbackground=DIM, highlightcolor=GOLD)
        b.bind("<Button-1>", lambda e: command())
        self._tag("base", b)
        self._tip(b, tip)
        return b

    def _build_menus(self):
        kw = dict(tearoff=0, bg=MENU_BG, fg=FG, activebackground=MENU_ACTIVE, activeforeground=GOLD,
                  bd=1, relief="flat", font=("Segoe UI", 10), selectcolor=GOLD)
        self.lock_var = tk.BooleanVar(value=self.locked)
        self.backdrop_var = tk.BooleanVar(value=self.backdrop)
        self.view_var = tk.StringVar(value=self.view)
        self.goal_var = tk.StringVar(value=self.goal)
        m = self.menu = tk.Menu(self.root, **kw)
        m.add_command(label="Quick help      F1", command=self._show_help)
        m.add_separator()
        m.add_checkbutton(label="Dark background      F11", variable=self.backdrop_var,
                          command=lambda: self.set_backdrop(self.backdrop_var.get()))
        m.add_checkbutton(label="Lock (click-through)      F9 to unlock", variable=self.lock_var,
                          command=lambda: self._set_click_through(self.lock_var.get()))
        m.add_command(label="Reset search and filters", command=self._clear_filters)
        m.add_command(label="Reset window size and position", command=self._reset_window)
        m.add_separator()
        m.add_command(label="Hide overlay      F8 to show again", command=lambda: self.set_visible(False))
        m.add_command(label="Quit      F10", command=self.quit)
        vm = self.view_menu = tk.Menu(self.root, **kw)
        for v in core.VIEWS:
            vm.add_radiobutton(label=core.VIEW_LABELS[v], variable=self.view_var, value=v,
                               command=lambda: self._set_view(self.view_var.get()))
        gm = self.goal_menu = tk.Menu(self.root, **kw)
        for g in core.GOALS:
            gm.add_radiobutton(label=core.GOAL_LABELS[g], variable=self.goal_var, value=g,
                               command=lambda: self._set_goal(self.goal_var.get()))

    def _popup(self, menu, widget):
        """Open a menu just under a widget."""
        self._hide_tip()
        try:
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _show_menu(self, e):
        """Right-click anywhere on the overlay opens the main menu at the pointer."""
        self._hide_tip()
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _tip(self, widget, text):
        """Hover tooltip. `text` may be a string or a function returning one."""
        def show():
            t = text() if callable(text) else text
            if not t or not widget.winfo_exists():
                return
            self._hide_tip()
            tw = tk.Toplevel(self.root)
            tw.overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
            except tk.TclError:
                pass
            tk.Label(tw, text=t, bg="#2b2620", fg=FG, padx=6, pady=3, justify="left", wraplength=280,
                     font=("Segoe UI", 9), highlightthickness=1, highlightbackground=DIM).pack()
            tw.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
            self._tip_win = tw

        def enter(_e):
            self._hide_tip()
            self._tip_job = self.root.after(550, show)

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", lambda e: self._hide_tip(), add="+")
        widget.bind("<ButtonPress>", lambda e: self._hide_tip(), add="+")

    def _hide_tip(self):
        if self._tip_job:
            try:
                self.root.after_cancel(self._tip_job)
            except tk.TclError:
                pass
            self._tip_job = None
        if self._tip_win:
            try:
                self._tip_win.destroy()
            except tk.TclError:
                pass
            self._tip_win = None

    def _update_tabs(self):
        """Tab styling (the active one is bold and underlined, finished ones turn green), tooltips with
        counts, and the progress text in the header. Then re-flow the tabs, as their widths changed."""
        prog = core.region_progress(self.data, self.progress.all_done())
        for name, b in self.tab_btns.items():
            active = name == self.region
            if name == DECISIONS:
                self._tab_tips[name] = f"{len(self.decisions)} decisions: the best choice for rewards, morals and the outcome"
                fg, font = (GOLD if active else DIM), ("Segoe UI", 9, "bold underline" if active else "bold")
            else:
                d, t = prog.get(name, (0, 0))
                self._tab_tips[name] = f"{name or 'All regions'}: {d} of {t} done"
                fg = GOLD if active else (GREEN if t and d == t else DIM)
                font = ("Segoe UI", 9, "bold underline" if active else "normal")
            b.config(fg=fg, font=font)
        D, T = prog[None]
        if self.region == DECISIONS:
            text = f"{len(self.decisions)} decisions"
        elif self.region is None:
            text = f"{D}/{T} done"
        else:
            d, t = prog.get(self.region, (0, 0))
            text = f"{d}/{t} here" if self.width < 520 else f"{self.region} {d}/{t}  \u2022  all {D}/{T}"
        self.prog_lbl.config(text=text)
        self._layout_tabs()

    def _on_search(self):
        if self.search_var.get():
            self.ph_lbl.place_forget()
            self.clear_btn.place(relx=1.0, x=-4, rely=0.5, anchor="e")
        else:
            self.clear_btn.place_forget()
            self.ph_lbl.place(x=6, rely=0.5, anchor="w")
        self.refresh()

    def _clear_search(self):
        self.search_var.set("")
        self.search_entry.focus_force()

    def _clear_filters(self):
        self.search_var.set("")
        self.goal = "all"
        self.goal_var.set("all")
        self._set_view("all")

    def _reset_window(self):
        self.width, self.extra_rows = WIDTH, DEFAULT_EXTRA_ROWS
        self.root.geometry("+30+60")
        self._fit()
        self._reflow()
        self._save_settings()

    def _show_help(self, _e=None):
        self._open.discard("detail")
        self.tree.selection_remove(*self.tree.selection())
        self._set_detail(HELP_TEXT, 24)

    def _bind_shortcuts(self):
        r = self.root
        r.bind("<F1>", self._show_help)
        r.bind("<Button-3>", self._show_menu, add="+")
        r.bind("<slash>", self._focus_search)
        r.bind("<Escape>", self._escape)
        r.bind("<Control-Right>", lambda e: self._cycle_tab(1))
        r.bind("<Control-Left>", lambda e: self._cycle_tab(-1))
        self.search_entry.bind("<Down>", self._search_down)
        self.search_entry.bind("<Return>", self._search_down)
        # Mouse wheel: handled for the whole window, not just for the list. In transparent mode the gaps
        # between the text belong to the invisible window behind the overlay, so the wheel is bound
        # app-wide and routed by where the pointer is. The list and the detail text bind it too, to
        # stop their built-in handling from scrolling a second time.
        for w in (self.tree, self.detail):
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(ev, self._on_wheel)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            r.bind_all(ev, self._on_wheel)

    def _wheel_target(self, x, y):
        """What the mouse wheel should scroll for a pointer at screen position (x, y): the detail text
        if the pointer is over it, otherwise the list. None when the pointer is outside the overlay."""
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        if not (rx <= x < rx + self.root.winfo_width() and ry <= y < ry + self.root.winfo_height()):
            return None
        d = self.detail
        if d.winfo_ismapped() and d.winfo_rooty() <= y < d.winfo_rooty() + d.winfo_height():
            return d
        return self.tree

    def _on_wheel(self, e):
        num, delta = getattr(e, "num", None), getattr(e, "delta", 0)
        if num == 4:
            notches = -1
        elif num == 5:
            notches = 1
        elif delta:  # Windows sends multiples of 120 (macOS small values); up is positive
            notches = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        else:
            return None
        target = self._wheel_target(e.x_root, e.y_root)
        if target is None:
            return None
        target.yview_scroll(notches * (3 if target is self.tree else 2), "units")
        return "break"

    def _focus_search(self, e):
        if isinstance(e.widget, tk.Entry):
            return None  # typing a slash into the search box
        self.search_entry.focus_force()
        return "break"

    def _escape(self, _e=None):
        if self.search_var.get():
            self.search_var.set("")
        self.tree.focus_set()

    def _search_down(self, _e=None):
        kids = [k for k in self.tree.get_children() if k != EMPTY]
        if kids:
            self.tree.focus_set()
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
            self.tree.see(kids[0])
        return "break"

    def _cycle_tab(self, step):
        order = [None] + list(self.data["regions"]) + [DECISIONS]
        self.set_region(order[(order.index(self.region) + step) % len(order)])
        return "break"

    # ---- Overlay behaviour ---------------------------------------------
    @staticmethod
    def _hwnd(widget):
        import ctypes
        return ctypes.windll.user32.GetParent(widget.winfo_id()) or widget.winfo_id()

    @staticmethod
    def _exstyle(hwnd, add=0, remove=0):
        import ctypes
        u = ctypes.windll.user32
        style = (u.GetWindowLongW(hwnd, GWL_EXSTYLE) | add) & ~remove
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def _make_backing(self):
        """A near-transparent window exactly behind the overlay that swallows clicks."""
        b = self.back = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.configure(bg="black")
        try:  # tunable in settings.json ("backing_alpha") if clicks fall through on your system
            alpha = float(self._load_settings().get("backing_alpha", BACKING_ALPHA))
            b.attributes("-alpha", min(max(alpha, 0.01), 0.5))
        except (tk.TclError, TypeError, ValueError):
            pass
        for ev, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag_motion),
                       ("<ButtonRelease-1>", self._release), ("<Motion>", self._hover), ("<Leave>", self._hover_end),
                       ("<Button-3>", self._show_menu), ("<Double-Button-1>", self._double_click)):
            b.bind(ev, fn)
        self.root.bind("<Configure>", self._on_configure, add="+")
        self._sync_back()

    def _on_configure(self, event):
        if event.widget is self.root:  # ignore the children's Configure events
            self._sync_back()

    def _sync_back(self):
        """Keep the backing window under the overlay and show it only when it is needed."""
        if not self.back:
            return
        want = self.visible and not self.backdrop  # the dark panel mode is opaque already
        if want:
            self.back.geometry(self.root.geometry())
            if self.back.state() != "normal":
                self.back.deiconify()
                if IS_WINDOWS:  # re-assert the window styles after the window was re-shown
                    self._set_click_through(self.locked)
            self.root.lift()  # text window stays above the backing
        elif self.back.state() != "withdrawn":
            self.back.withdraw()

    def _set_click_through(self, on):
        self.locked = on
        self._update_hint_text()
        if not IS_WINDOWS:
            return
        self.root.update_idletasks()
        windows = [(self.root, 0)] + ([(self.back, WS_EX_NOACTIVATE)] if self.back else [])
        for w, extra in windows:  # the backing never takes focus; both let clicks through when locked
            h = self._hwnd(w)
            self._exstyle(h, add=WS_EX_LAYERED | WS_EX_TOOLWINDOW | extra,
                          remove=0 if on else WS_EX_TRANSPARENT)
            if on:
                self._exstyle(h, add=WS_EX_TRANSPARENT)

    def apply_log_lines(self, lines):
        """Feed game log lines to the tracker and refresh; jump to a newly tracked quest."""
        changes = {c for c in (self.tracker.feed(l) for l in lines) if c}
        if not changes:
            return
        if "tracked" in changes and core.tracked_risks(
                self.data, self.progress.all_done(), self.progress.auto_failed, self.progress.tracked_all):
            self.set_visible(True)  # an important warning must not stay hidden behind F8
        if "tracked" in changes and self.progress.tracked:
            qid = self.progress.tracked
            if not self.tree.exists(qid):  # hidden by a filter: clear filters so it shows
                self.region = None
                self.search_var.set("")
                self.view = "all"
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
            data = dict(self._load_settings(), backdrop=self.backdrop, width=self.width, extra_rows=self.extra_rows,
                        view=self.view)
            self._settings_path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def set_backdrop(self, on):
        self.backdrop = on
        if hasattr(self, "backdrop_var"):
            self.backdrop_var.set(on)
        self._apply_backdrop()
        self._save_settings()

    def _apply_backdrop(self):
        """Transparent: every background is KEY (see-through on Windows), only text shows.
        Backdrop: a dark semi-opaque panel behind everything, for bright or busy scenes."""
        on = self.backdrop
        self._sync_back()
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
        self._hide_tip()
        self.root.destroy()

    def set_visible(self, visible):
        self.visible = visible
        (self.root.deiconify if visible else self.root.withdraw)()
        self._sync_back()

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
    if track_game:
        tracker.start_tracking(ov.events)
    if on_ready:
        on_ready(ov)
    root.mainloop()


def main():
    run()


if __name__ == "__main__":
    main()
