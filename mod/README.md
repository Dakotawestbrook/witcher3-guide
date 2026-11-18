# In-game quest reporter (the mod)

A tiny WitcherScript mod that makes the game write quest state to its script log, which the
overlay reads to tick finished quests, mark failed ones, and highlight the tracked quest.

**Status: written, not yet run in the game.** The journal functions it calls and the three
places it hooks into were checked against the game's vanilla scripts, the installer was run
against those scripts, and the overlay side was tested with simulated logs. Nobody has yet
compiled it with the game or watched it produce a real log, so expect to test it.

## Install

You need the game's vanilla scripts (usually `<game>\content\content0\scripts`; if that folder
isn't there, extract them with WolvenKit or the Mod Kit, the same files Script Merger uses).

```bash
python mod/install_mod.py --game "C:\Program Files (x86)\Steam\steamapps\common\The Witcher 3"
```

You can also just double-click `mod/install_mod.py`: it looks for your game folder, asks you to confirm or paste it, and waits for Enter before closing so you can read the result.

This builds `<game>\mods\modWitcherGuide`. It copies three of your own vanilla script files,
inserts **one line** into each (marked `// modWitcherGuide`), and adds `witcherGuide.ws`.
No game code is stored in this repository. If your scripts are elsewhere, add
`--scripts DIR`. If the installer says it can't find the place to patch, your game version
differs; add the three lines below by hand.

Then:
1. If you use other mods, run **Script Merger** (they may change the same files).
2. Launch the game with the launch option **`-debugscripts`** (Steam: Properties -> Launch
   Options). Without it the game doesn't write the log.
3. Start the overlay as usual. It reads `Documents\The Witcher 3\scriptlog.txt`.

To uninstall, delete `<game>\mods\modWitcherGuide`.

## What it hooks (verified to exist in the vanilla scripts)

| File | Where | Line added |
|---|---|---|
| `game/gui/hud/hud.ws` | `event OnQuestEvent`, after its `LogChannel(...)` line | `WG_Snapshot();` |
| `game/gui/hud/modules/hudModuleQuests.ws` | `OnQuestTrackingStarted`, after `e.eventType = EUET_StartedTracking;` | `WG_LogTracked( journalQuest );` |
| `game/player/playerWitcher.ws` | `OnSpawned`, after `ApplyPatchFixes();` (only runs when a save is loaded) | `WG_Snapshot();` |

`witcherGuide.ws` uses only functions the game's own scripts use: `GetJournalManager`,
`GetActivatedOfType('CJournalQuest', ...)`, `GetEntryStatus` (`JS_Success`, `JS_Failed`,
`JS_Active`, `JS_Inactive`), `GetTrackedQuest`, `GetTitleStringId` + `GetLocStringById`,
and `LogChannel`.

## Log format (what the overlay parses)

Lines containing `@@WG@@`; anything before it (timestamps, channel names) is ignored.

| Line | Meaning |
|---|---|
| `@@WG@@\|snapshot\|begin` ... `@@WG@@\|snapshot\|end` | full journal dump; replaces the automatic state, so loading an older save corrects it. An empty snapshot is ignored. |
| `@@WG@@\|q\|<title>\|<state>` | one quest; state = `active`, `success`, `failed`, `inactive` |
| `@@WG@@\|tracked\|<title>` | the tracked quest (empty = none) |

`<title>` is the quest's display name in your game language. The overlay matches it to
`quests.json` by name (English); titles it can't match are listed in `unmatched_quests.txt`
next to `progress.json` so you can map them in `witcher_guide/data/aliases.json`.

## Things still unverified

- Whether the quest-event hook fires before or after the status changes (the overlay corrects
  itself on the next event or save load either way).
- Whether `-debugscripts` has side effects you'd care about, and whether script mods work on
  the remastered edition.
- That the log file name on your system is `scriptlog.txt` (the overlay also accepts
  `scriptslog.txt`).
