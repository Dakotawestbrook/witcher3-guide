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

## Launcher

- **Double-click `witcher_guide.pyw`** to start the overlay with no console window. Nothing
  starts automatically with Windows; you launch it when you want it.
- Optional: `python witcher_guide.pyw --watch` keeps the overlay hidden until `witcher3.exe`
  is running, shows it while you play, and hides it when the game exits. Use
  `--process YourGame.exe` if your edition (for example the remaster) has a different
  executable name.
- If you ran an earlier version's `install_autostart.bat`, remove its startup entry with
  `python witcher_guide.pyw --uninstall`.

## Automatic quest tracking (in progress)

The overlay can follow the game: finished quests are ticked automatically, quests the
game reports as failed show as missed, and the quest you select in the game's journal is
highlighted ("Tracking in game") with the list jumping to it. It reads messages the game
would write to its script log (`Documents\The Witcher 3\scriptlog.txt`, which needs the
game launched with `-debugscripts`).

**Status:** the overlay side is built and tested with simulated logs. The in-game mod that
writes those messages is **not written yet**; see [`mod/README.md`](mod/README.md) for the
message format and what is needed to finish it. Until then everything works as before
(manual ticking). Quest titles the game reports that don't match `quests.json` are listed
in `unmatched_quests.txt` next to `progress.json`; map them in `witcher_guide/data/aliases.json`.

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
