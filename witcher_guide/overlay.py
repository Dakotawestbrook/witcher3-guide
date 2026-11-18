"""Always-on-top, click-through overlay for the Witcher 3 guide.

Run the game in *borderless windowed* mode (exclusive fullscreen hides overlays).
Hotkeys (work while the game has focus, Windows only):
    F8  show / hide the overlay
    F9  lock (click-through, game gets the mouse) / unlock (interact with overlay)
"""
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from witcher_guide import core

IS_WINDOWS = sys.platform == "win32"

BG, FG, DIM = "#14110f", "#e8dcc4", "#8a7f6a"
GOLD, RED, GREEN, BLUE = "#d4a64a", "#e5534b", "#6fbf73", "#6aa5d8"
ICON = {core.DONE: "✔", core.AVAILABLE: "▶", core.BLOCKED: "○", core.MISSED: "✖"}

# Win32 constants
MOD_NOREPEAT, VK_F8, VK_F9 = 0x4000, 0x77, 0x78
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
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                events.put("toggle" if msg.wParam == 1 else "lock")

    threading.Thread(target=loop, daemon=True).start()


class Overlay:
    def __init__(self, root, data=None, progress=None):
        self.root = root
        self.data = data or core.load_data()
        self.progress = progress or core.Progress()
        self.region = None  # None = all regions
        self.locked = False
        self.visible = True
        self.events = queue.Queue()
        self._drag = (0, 0)

        root.title("Witcher 3 Guide")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.9)
        root.configure(bg=BG)
        root.geometry("430x600+30+60")

        self._style()
        self._build()
        self.refresh()
        root.update_idletasks()
        self._set_click_through(False)
        start_hotkey_thread(self.events)
        root.after(80, self._poll)

    # ---- UI -------------------------------------------------------------
    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("T.Treeview", background=BG, fieldbackground=BG, foreground=FG,
                    borderwidth=0, rowheight=24, font=("Segoe UI", 10))
        s.map("T.Treeview", background=[("selected", "#2c2620")])
        s.configure("T.TCheckbutton", background=BG, foreground=FG)

    def _build(self):
        r = self.root
        head = tk.Frame(r, bg="#1f1a15")
        head.pack(fill="x")
        self.title_lbl = tk.Label(head, text="⚔ Witcher 3 Guide", bg="#1f1a15", fg=GOLD,
                                  font=("Segoe UI", 12, "bold"), anchor="w")
        self.title_lbl.pack(side="left", padx=8, pady=6)
        self.lock_lbl = tk.Label(head, text="", bg="#1f1a15", fg=DIM, font=("Segoe UI", 9))
        self.lock_lbl.pack(side="right", padx=8)
        for w in (head, self.title_lbl):
            w.bind("<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.x_root - r.winfo_x(), e.y_root - r.winfo_y())))
            w.bind("<B1-Motion>", lambda e: r.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}"))

        tabs = tk.Frame(r, bg=BG)
        tabs.pack(fill="x", padx=6, pady=(6, 0))
        self.tab_btns = {}
        for n, name in enumerate([None] + self.data["regions"]):
            b = tk.Label(tabs, text=name or "All", bg=BG, fg=DIM, font=("Segoe UI", 9), padx=5, cursor="hand2")
            b.grid(row=n // 5, column=n % 5, sticky="w")
            b.bind("<Button-1>", lambda e, n=name: self.set_region(n))
            self.tab_btns[name] = b

        bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=8, pady=6)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        e = tk.Entry(bar, textvariable=self.search_var, bg="#241e18", fg=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 10))
        e.pack(side="left", fill="x", expand=True, ipady=3)
        e.bind("<Button-1>", lambda ev: e.focus_force())
        self.miss_var = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Missable only", variable=self.miss_var, style="T.TCheckbutton",
                        command=self.refresh).pack(side="left", padx=(8, 0))

        self.alert_lbl = tk.Label(r, text="", bg="#2a1411", fg=RED, justify="left", anchor="w",
                                  wraplength=400, font=("Segoe UI", 9, "bold"))
        self.alert_lbl.pack(fill="x", padx=8)

        self.tree = ttk.Treeview(r, style="T.Treeview", show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=8, pady=6)
        for tag, col in (("done", DIM), ("available", GREEN), ("blocked", FG), ("missed", RED), ("missable", GOLD)):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.tree.bind("<Double-1>", self._toggle_selected)

        self.detail = tk.Label(r, text="Double-click a quest to mark it done.", bg="#1f1a15", fg=FG,
                               justify="left", anchor="nw", wraplength=410, font=("Segoe UI", 9), height=8)
        self.detail.pack(fill="x", padx=8, pady=(0, 8))

    # ---- State ----------------------------------------------------------
    def set_region(self, name):
        self.region = name
        self.refresh()

    def refresh(self):
        done = self.progress.done
        for n, b in self.tab_btns.items():
            b.config(fg=GOLD if n == self.region else DIM)
        self.tree.delete(*self.tree.get_children())
        rows = core.search(self.data, done, self.search_var.get(), self.region, self.miss_var.get())
        # recommended next quests float to the top
        rows.sort(key=lambda q: 0 if q["status"] == core.AVAILABLE else 1)
        for q in rows:
            tags = [q["status"]] + (["missable"] if q.get("missable") and q["status"] != core.DONE else [])
            star = " ⚠" if q.get("missable") else ""
            self.tree.insert("", "end", iid=q["id"], text=f' {ICON[q["status"]]}  {q["name"]}{star}', tags=tags)
        al = core.alerts(self.data, done)
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
        return next((q for q in core.annotate(self.data, self.progress.done) if q["id"] == qid), None)

    def _show_detail(self, _e=None):
        sel = self.tree.selection()
        q = self._quest(sel[0]) if sel else None
        if not q:
            return
        lines = [f'{q["name"]}  [{q["region"]} • {q["type"]} • {q["status"]}]']
        miss = core.missing_prereqs(q, self.data, self.progress.done)
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
        self.lock_lbl.config(text="LOCKED (F9)" if on else "F8 hide • F9 lock")
        if not IS_WINDOWS:
            return
        import ctypes
        u = ctypes.windll.user32
        h = self._hwnd()
        style = u.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style = style | WS_EX_TRANSPARENT if on else style & ~WS_EX_TRANSPARENT
        u.SetWindowLongW(h, GWL_EXSTYLE, style)

    def set_visible(self, visible):
        self.visible = visible
        (self.root.deiconify if visible else self.root.withdraw)()

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev == "toggle":
                    self.set_visible(not self.visible)
                elif ev == "show":
                    self.set_visible(True)
                elif ev == "hide":
                    self.set_visible(False)
                elif ev == "lock":
                    self._set_click_through(not self.locked)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)


def run(on_ready=None, start_hidden=False):
    """Create the overlay and run the Tk loop. `on_ready(overlay)` runs once it exists."""
    root = tk.Tk()
    ov = Overlay(root)
    if start_hidden:
        ov.set_visible(False)
    if not IS_WINDOWS:  # dev fallback: no global hotkeys, so use local keys
        root.bind("<F8>", lambda e: ov.events.put("toggle"))
        root.bind("<F9>", lambda e: ov.events.put("lock"))
    root.bind("<Escape>", lambda e: root.destroy())
    if on_ready:
        on_ready(ov)
    root.mainloop()


def main():
    run()


if __name__ == "__main__":
    main()
