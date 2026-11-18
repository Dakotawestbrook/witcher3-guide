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

Quest data lives in `witcher_guide/data/quests.json`. The bundled dataset is a
**starter set written from memory and known to contain errors** (for example,
the real point of no return is The Isle of Mists). Entries marked
`"verify": true` must be checked against a guide before you rely on them.
Fields: `requires` (order), `missable` + `warn` (warnings), `expires_before`
(becomes missed once that quest is done).

## Tests

```bash
python -m unittest discover -s . -t .
```
