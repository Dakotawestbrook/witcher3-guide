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

## Quest data

`witcher_guide/data/quests.json` holds 198 entries across White Orchard, Velen,
Novigrad, Skellige, Kaer Morhen, the finale, general items/Gwent, and the
Hearts of Stone and Blood and Wine DLC. It was compiled from:

- main-story order: [gamepressure.com](https://www.gamepressure.com/thewitcher3/main-storyline/z978a9)
- side quests and recommended levels: [game-checklists.com](https://game-checklists.com/witcher3/all-side-quests-checklist.html)
- missable quests and cutoffs: [allthings.how](https://allthings.how/the-witcher-3-every-missable-quest-and-its-point-of-no-return/)

Each entry has a `source` field. The guides disagree in small ways (for example
gamepressure calls Imperial Audience "Royal Audience"), and none were checked in
the game itself, so treat the data as a well-sourced starting point. Known gaps:
the Hearts of Stone and Blood and Wine coverage is limited to their missable
cutoffs, and the level and prerequisite edges between side quests are not
modelled (only main-story order, Reason of State, and the cutoffs are).

Fields: `requires` (order), `missable` + `warn` (warnings), `expires_before`
(becomes MISSED once that quest is marked done), `level`, `source`. The banner
at the top of the overlay warns "Before <main quest>: ..." when a base-game
main-story cutoff is available to start.

## Tests

```bash
python -m unittest discover -s . -t .
```
