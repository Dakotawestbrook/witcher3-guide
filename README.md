# Witcher 3 Guide Overlay

An always-on-top overlay that tracks quests, shows the recommended order, and
warns about missable quests and items.

```bash
python -m witcher_guide
```

- Run Witcher 3 in **borderless windowed** mode (exclusive fullscreen hides overlays).
- **F8** shows/hides the overlay, **F9** locks it (click-through, so the mouse goes to the game) or unlocks it. Global hotkeys are Windows only; elsewhere F8/F9 work while the overlay has focus.
- Double-click a quest to mark it done. Progress is saved to `%APPDATA%\witcher_guide\progress.json`.
- Green `▶` = available now, `○` = blocked (select it to see what to do first), `✖` = missed, `⚠` = missable.

## Launcher and autostart (Windows)

- **Double-click `witcher_guide.pyw`** to start the overlay with no console window.
- **Start with Windows:** double-click `install_autostart.bat` (or run `python witcher_guide.pyw --install`).
  It adds a per-user startup entry (no admin rights needed) and runs in *watch* mode: the
  overlay stays out of sight until Witcher 3 starts, appears while the game is running, and
  hides again when you quit. F8 still toggles it manually.
- `python witcher_guide.pyw --install --always` starts it with Windows and keeps it always visible.
- `python witcher_guide.pyw --status` shows what is installed.
- **Remove:** double-click `uninstall_autostart.bat` (or `python witcher_guide.pyw --uninstall`).
- Watch mode looks for the process `witcher3.exe`. If your edition (for example the
  remaster) uses a different executable name, install with
  `python witcher_guide.pyw --install --process YourGame.exe`.
- If you move or delete this folder, or reinstall Python, run the install step again.

## Quest data

`witcher_guide/data/quests.json` holds 262 entries across White Orchard, Velen,
Novigrad, Skellige, Kaer Morhen, the finale, general items/Gwent, and the full
quest lists for the Hearts of Stone and Blood and Wine DLC. It was compiled from:

- main-story order: [gamepressure.com](https://www.gamepressure.com/thewitcher3/main-storyline/z978a9)
- base-game side quests and recommended levels: [game-checklists.com](https://game-checklists.com/witcher3/all-side-quests-checklist.html)
- DLC quests, levels and missables: game-checklists.com ([Hearts of Stone](https://game-checklists.com/witcher3/hearts-of-stone.html), [Blood and Wine](https://game-checklists.com/witcher3/blood-and-wine-checklist.html))
- base-game missables and cutoffs: [allthings.how](https://allthings.how/the-witcher-3-every-missable-quest-and-its-point-of-no-return/)

Each entry has a `source` field. The guides disagree in small ways (for example
gamepressure calls Imperial Audience "Royal Audience"), and none were checked in
the game itself, so treat the data as a well-sourced starting point. Known gaps:
treasure hunts (except the one missable Hearts of Stone hunt) and fast-travel
signposts are not included, and prerequisites between base-game side quests are
not modelled (only main-story order, Reason of State, DLC chains and the
cutoffs are). In Blood and Wine, the branch-exclusive quests of the Syanna/Orianna
paths all show as available; only one path is playable per run.

Fields: `requires` (order), `missable` + `warn` (warnings), `expires_before`
(becomes MISSED once that quest is marked done), `level`, `source`. The banner
at the top of the overlay warns "Before <main quest>: ..." when a main-story
cutoff that has prerequisites becomes available to start.

## Tests

```bash
python -m unittest discover -s . -t .
```
