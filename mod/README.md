# In-game quest reporter (mod side) - NOT WRITTEN YET

The overlay already understands the messages below and has been tested against
simulated logs. What is missing is the small WitcherScript mod that makes the game
write them. It has not been written because the game's journal API names could not be
confirmed from documentation, and a script mod that guesses names can break a game
install. It needs to be written against the real scripts.

## What the mod must do

Write lines to the script log (`Documents\The Witcher 3\scriptlog.txt`; the game must be
launched with `-debugscripts`) using `LogChannel('modWG', "<line>")`. The overlay only
looks for the marker `@@WG@@`, so any prefix the game adds is fine.

| When | Line |
|---|---|
| A save is loaded / the game starts | `@@WG@@\|snapshot\|begin`, then one `@@WG@@\|q\|<title>\|<state>` per journal quest, then `@@WG@@\|snapshot\|end` |
| A quest's status changes | `@@WG@@\|q\|<title>\|<state>` |
| The tracked quest changes | `@@WG@@\|tracked\|<title>` (empty title = nothing tracked) |

`<title>` is the quest's English display name (for example `Imperial Audience`).
`<state>` is one of `active`, `success`, `failed`, `inactive`.

## What I need to write it

From your installed game's scripts (or the community's decompiled script dumps), the
exact names and signatures for:

1. getting the journal manager and iterating all quests,
2. a quest's display name and status (and the status values),
3. the currently tracked quest,
4. a good place to hook "status changed", "tracked quest changed" and "save loaded".

Pasting the relevant function signatures into chat is enough. Please don't commit
game script files to this public repository.

## Things I have not been able to check

- Whether `-debugscripts` has side effects you'd care about.
- Whether script mods work on the remastered edition.
- Script Merger may be needed if the hook sits in a file other mods also change.
