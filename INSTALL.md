# Installing GreyMatter

> ### ⚠️ Already running GreyMatter v1.28.1 or earlier?
> **Read [docs/UPGRADING.md](docs/UPGRADING.md) before you upgrade.** The updater
> shipped with older releases may reset uncommitted changes in your engine
> checkout, once, during the move to v1.29.0. One command tells you whether it
> concerns you:
> ```bash
> git -C ~/.c-brain/engine status --short
> ```
> Your notes are not affected — the trunk is a separate directory and no update
> path writes to it.

## The short way: ask your agent

Paste this into your CLI (Claude Code or another command-line agent):

```
Install GreyMatter: clone https://github.com/Yuno15-bb/GreyMatter-engine into ~/dev/c-brain, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

That's it. The agent clones, installs, and hands you back the selftest result.

## The manual way

```bash
git clone https://github.com/Yuno15-bb/GreyMatter-engine ~/dev/c-brain
cd ~/dev/c-brain
./install.sh
```

Options: `--dry-run` (writes nothing, shows what would happen) ·
`--dev` (for working ON GreyMatter: links the engine to your checkout and turns
automatic engine updates off for it) ·
`--no-launchd` (no scheduled jobs) · `--no-capsule` (no Electron) · `--no-shortcut`
(no `C Brain` shortcut in your home folder).

---

## What the install does — and does not do

Two locations, and keeping them apart is the heart of the system:

```
~/.c-brain/versions/  each installed version. CODE only, immutable.
~/.c-brain/engine     → link to the ACTIVE version. Updating switches this link.
~/.c-brain/trunk      → YOUR trunk. Your notes. Never overwritten, never updated.
```

**This repository is the SOURCE, not the engine.** The installer reads it to
build a version under `~/.c-brain/versions/` and never writes to it again — so
`brain update` has nothing to do with your clone, and cannot move, reset or
overwrite it. Update your clone with git, like any other repository.
See [docs/install-model.md](docs/install-model.md).

The installer:

- creates your **empty** trunk if none exists (and touches nothing if one does);
- builds an engine from this source and links it into the trunk with symlinks;
- puts the `brain` command in `~/.local/bin`;
- makes the agents visible to your CLI;
- **adds** its hooks to `~/.claude/settings.json` without touching the rest —
  your model, your theme, your own hooks are preserved, and a backup is written
  before any modification;
- installs the capsule and the scheduled jobs, unless you decline them;
- drops a planet launcher on your Desktop;
- **checks its own work** (`selftest` + `doctor`) and shows you the result.

It deletes nothing, sends nothing over the network, and reads none of your data.

## Prerequisites

| Required | For |
|---|---|
| macOS | launchd, Electron, `open` |
| `python3` | every hook and the CLI |
| `git` | updates |
| `npm` *(optional)* | the Electron capsule — everything else works without it |

## If you don't use Claude Code

GreyMatter still installs, and gives you the trunk, the agents, the `brain` CLI, the
planet and the capsule.

**What you won't get**: the closed loop. Recall at the start of a session,
archiving at the end, autonomous maintenance — all go through the hooks in
`~/.claude/settings.json`, which are specific to Claude Code. Elsewhere, GreyMatter
works **on demand**: `brain recall`, `brain status`, agents invoked explicitly.
The installer detects this and tells you — it does not pretend.

## First steps

Your trunk starts **empty**, and an empty trunk shows nothing. Fill it with
examples first, long enough to understand the loop:

```bash
brain demo                # place 3 example notes
brain recall cache deploy # what recall finds, and why
brain demo --remove       # take them away, leaving no trace
```

The three notes cover the three useful types — a **lesson**, a **method** note,
a project **resume point** — and they link to each other, so the graph has
something to show.

`--remove` will not touch a note you have edited: it stopped being an example
the moment you wrote your first line in it.

Then, day to day:

```bash
brain status          where the trunk stands
brain recall <word>   search your memory
brain doctor          tree health
brain capsule         open the floating orb  (stop · status)
brain selftest        verify the installation
```

Then open `~/.c-brain/trunk/MEMORY.md`: it is the index loaded at the start of every
session, and it explains the note format. Your tree grows with the work, not
before.

## Uninstalling

```bash
~/dev/c-brain/uninstall.sh
```

**Your trunk and your notes are never deleted.** Removed: the GreyMatter hooks (the
rest of `settings.json` untouched), the engine symlinks, the `brain` command, the
Desktop launcher, the scheduled jobs. Backups stay in `~/.c-brain/backups/`.
