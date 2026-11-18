# Witcher 3 Guide Overlay

An always-on-top overlay that tracks quests, shows the recommended order, and
warns about missable quests and items.

```bash
python -m witcher_guide
```

- Run Witcher 3 in **borderless windowed** mode (exclusive fullscreen hides overlays).
- **F8** shows/hides the overlay, **F9** locks it (click-through, so the mouse goes to the game) or unlocks it, **F10** quits it. The ✕ in the title bar also closes it (unlock with F9 first if it is locked).
- **F11** switches between a fully transparent overlay (only the text is visible, and you can click through everything else) and a dark backing panel, which is easier to read over bright or busy scenes. Your choice is remembered in `settings.json` next to `progress.json`. On Windows only; elsewhere the window stays dark.
- **Clicks on empty space:** in transparent mode a nearly invisible window sits behind the overlay so
  clicks on the see-through parts are absorbed instead of landing on the game (and taking its focus).
  It never takes focus itself. If clicks still fall through to the game on your system, raise its
  opacity by adding `"backing_alpha": 0.05` to `settings.json` (allowed range 0.01 to 0.5) and restart. Global hotkeys are Windows only; elsewhere F8/F9 work while the overlay has focus.
- Double-click a quest to mark it done. Progress is saved to `%APPDATA%\witcher_guide\progress.json`.
- Green `▶` = available now, `○` = blocked (select it to see what to do first), `✖` = missed, `⚠` = missable.

## Launcher

- **Double-click `witcher_guide.pyw`** to start the overlay with no console window. Nothing
  starts automatically with Windows; you launch it when you want it.
- Optional: `python witcher_guide.pyw --watch` keeps the overlay hidden until `witcher3.exe`
  is running, shows it while you play, and hides it when the game exits. Use
  `--process YourGame.exe` if your edition (for example the remaster) has a different
  executable name.
- If you ran an earlier version's `install_autostart.bat`, remove its startup entry with
  `python witcher_guide.pyw --uninstall`.

## Automatic quest tracking

The overlay can follow the game: finished quests are ticked automatically, quests the game
reports as failed show as missed, and the quest you select in the game's journal is
highlighted ("Tracking in game") with the list jumping to it. A small script mod makes the
game write this information to its script log; the overlay reads that log.

**Status:** the mod and the overlay side are written and tested against simulated logs and
the game's vanilla scripts, but **not yet run in the game**. Setup is in
[`mod/README.md`](mod/README.md) (build the mod with `python mod/install_mod.py`, then launch
the game with `-debugscripts`). Until the mod is installed, everything works as before with
manual ticking.

## Warnings

- **Tracking a quest that closes others:** if the quest you are tracking in the game would make you miss
  missable quests you haven't finished (for example tracking *Imperial Audience* while *Missing in Action*
  is still open), a red warning appears under the tracking line and the overlay pops up even if you hid it
  with F8. Needs the in-game mod (see below). The affected rows are marked "will be lost".
- **Long lists and long descriptions never get cut off:** anything that doesn't fit shows a
  "+N more (click)" or "N more lines (click to expand)" link. Click it to expand, and click again to collapse.
  The window grows to fit.

## Closing a stuck or old copy

Only one copy can run at a time; launching a second shows a message instead of starting. To close
a copy that is still running (for example one started before an update), press **F10**, or in
PowerShell:

```bash
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*witcher_guide*' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## Troubleshooting automatic tracking

Run `python -m witcher_guide.diagnose` from this folder. It checks whether the game wrote a log,
whether the mod's lines are in it, whether the overlay can read them, and whether the quest
titles match `quests.json`, then prints a report you can paste when asking for help.

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
