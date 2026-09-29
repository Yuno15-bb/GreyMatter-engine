# Installing GreyMatter

Three ways in, from the lightest to the fullest. This page covers the full
install, which is the only one with the pieces you can see.

[Choose](#choose-how) · [Ask your agent](#the-short-way-ask-your-agent) ·
[By hand](#the-manual-way) · [What it does](#what-the-install-does--and-does-not-do) ·
[Prerequisites](#prerequisites) · [First steps](#first-steps) ·
[New in v2.2](#new-in-v22) · [Upgrading](#upgrading-from-an-older-version) ·
[Uninstalling](#uninstalling)

> [!WARNING]
> **Already running GreyMatter v1.28.1 or earlier?** Read
> [Upgrading](#upgrading-from-an-older-version) before anything else — one
> command tells you whether an old updater can cost you uncommitted changes.

## Choose how

| Way | Command | You get |
|---|---|---|
| Plugin | `/plugin install greymatter@greymatter` | the memory, inside Claude Code |
| **Full install** | `./install.sh` | the memory, the `brain` command, the menu bar pill, the map app, the scheduled jobs |
| Memory only | `./install.sh --core-only` | the memory and `brain` — no window, no scheduled job |

The plugin route is in the [README](README.md#install). Everything below is the
full install, which installs **v2.2.0, the latest release**.

## The short way: ask your agent

```
Install GreyMatter: clone https://github.com/Yuno15-bb/GreyMatter-engine at tag v2.2.0
into ~/dev/greymatter, read its INSTALL.md, then run ./install.sh
and show me the final verification output.
```

Paste that into your CLI (Claude Code or another command-line agent). It
clones, installs, and hands you back the selftest result.

## The manual way

```bash
git clone --branch v2.2.0 https://github.com/Yuno15-bb/GreyMatter-engine ~/dev/greymatter
cd ~/dev/greymatter
./install.sh
```

`--branch v2.2.0` is what makes it the release. Without it you get `main`,
where the next version is being built and changes from one commit to the next.
Git may print `refs/tags/v2.2.0 … is not a commit!` and a note about a detached HEAD:
both are harmless — the tag is annotated, and git checks out the commit it
points to.

<details>
<summary><b>On a brand-new Mac</b></summary>

`git` and `python3` are not there yet: they come with Apple's Command Line
Tools. The first `git clone` opens Apple's dialog to install them — accept, let
it finish (a few minutes), then run the three lines again. You can also start
with `xcode-select --install`. Nothing else is needed: no Homebrew, no Node.
The same tools ship Swift, which builds the menu bar pill and the map app.

</details>

<details>
<summary><b>Options</b></summary>

| Option | Effect |
|---|---|
| `--dry-run` | writes nothing, shows what would happen |
| `--core-only` | the memory alone: no menu bar pill, no Desktop launcher, no scheduled jobs |
| `--dev` | for working ON GreyMatter: links the engine to your checkout and turns automatic engine updates off for it |
| `--no-launchd` | no scheduled jobs |
| `--no-capsule` | no menu bar pill |
| `--no-planet` | no GreyMatter launcher on your Desktop (the map app) |
| `--no-shortcut` | no `GreyMatter` shortcut in your home folder |

What you decline is remembered: updates, rollbacks and a new `./install.sh`
without these options keep it declined. Giving `--core-only` or a `--no-…`
option again replaces the old choices. To get every piece back, delete
`~/.greymatter/state/install-choices`, then run `./install.sh` with no option.

</details>

## What the install does — and does not do

```
~/.greymatter/versions/  each installed version. CODE only, immutable.
~/.greymatter/engine     → link to the ACTIVE version. Updating switches this link.
~/.greymatter/trunk      → YOUR trunk. Your notes. Never overwritten, never updated.
```

Two locations, and keeping them apart is the heart of the system: the code can
be replaced as often as it likes, your notes never are.

**This repository is the SOURCE, not the engine.** The installer reads it to
build a version under `~/.greymatter/versions/` and never writes to it again —
so `brain update` has nothing to do with your clone, and cannot move, reset or
overwrite it. Update your clone with git, like any other repository. See
[docs/install-model.md](docs/install-model.md).

<details>
<summary><b>What the installer does, step by step</b></summary>

- creates your **empty** trunk if none exists (and touches nothing if one does);
- builds an engine from this source and links it into the trunk with symlinks;
- puts the `brain` command in `~/.local/bin`;
- makes the agents visible to your CLI;
- **adds** its hooks to `~/.claude/settings.json` without touching the rest —
  your model, your theme, your own hooks are preserved, and a backup is written
  before any modification;
- builds the menu bar pill and installs the scheduled jobs, unless you decline them;
- drops the GreyMatter launcher on your Desktop, which opens the map;
- **checks its own work** (`selftest` + `doctor`) and shows you the result —
  and if that check is red, the installer exits with an error, so a script or
  an agent running it sees the failure too.

</details>

Installation does not send telemetry. Updates fetch published tags; recall reads
your local notes and may add note titles, summaries and paths to a prompt sent
to your model provider. [SECURITY.md](SECURITY.md) has the full data flow.

## Prerequisites

| Required | For |
|---|---|
| macOS | launchd, the menu bar pill, `open` |
| `python3` | every hook and the CLI |
| `git` | updates |
| `swift` *(optional)* | the menu bar pill and the map app — everything else works without it |

`python3`, `git` and `swift` all come with Apple's Command Line Tools
(`xcode-select --install`); their Python 3.9 is enough. Without `swift` the
installer skips only the pill and says how to add it later, and the Desktop
launcher opens the map in your browser instead.

## If you don't use Claude Code

| Works anywhere, on demand | Needs Claude Code |
|---|---|
| the trunk, the agents, the `brain` CLI, the map, the menu bar pill | recall at the start of a session, archiving at the end, autonomous maintenance |

GreyMatter still installs. **What you won't get is the closed loop**: it goes
through the hooks in `~/.claude/settings.json`, which are specific to Claude
Code. Elsewhere, GreyMatter works **on demand** — `brain recall`,
`brain status`, agents invoked explicitly. The installer detects this and tells
you; it does not pretend.

## First steps

```bash
brain demo                # place 3 example notes
brain recall cache deploy # what recall finds, and why
brain demo --remove       # take them away, leaving no trace
```

Your trunk starts **empty**, and an empty trunk shows nothing. Fill it with
examples first, long enough to understand the loop.

<details>
<summary><b>What the three example notes are</b></summary>

They cover the three useful types — a **lesson**, a **method** note, a project
**resume point** — and they link to each other, so the graph has something to
show.

`--remove` will not touch a note you have edited: it stopped being an example
the moment you wrote your first line in it.

</details>

Then, day to day:

```bash
brain status          where the trunk stands ("not started yet" until your first session)
brain recall <word>   search your memory
brain doctor          tree health
brain capsule         open the menu bar pill  (stop · status)
brain selftest        verify the installation
```

Then open `~/.greymatter/trunk/MEMORY.md`: it is the index loaded at the start
of every session, and it explains the note format. Your tree grows with the
work, not before.

## New in v2.2

| | v2.1.1 | v2.2.0 |
|---|---|---|
| Capsule | the floating orb, an Electron window | the menu bar pill, a native macOS program |
| Desktop launcher | opens the planet in your browser | opens the map in its own window |
| Builds with | `npm`, optional | Swift, from the Command Line Tools |
| `brain capsule` | opens the floating orb | opens the menu bar pill |

The planet is still there: `planet/launch.sh` opens it in your browser, as
before. Coming from v2.1.1, `brain update` makes the switch —
[docs/UPGRADING.md](docs/UPGRADING.md#upgrading-to-v220--the-menu-bar-pill)
says what moves.

## Upgrading from an older version

```bash
git -C ~/.greymatter/engine status --short
```

**Coming from v1.28.1 or earlier?** Run that first, then read
[docs/UPGRADING.md](docs/UPGRADING.md) before you upgrade. The updater shipped
with older releases may reset uncommitted changes in your engine checkout, once,
during the move to v1.29.0; the command shows whether you have any.

Your notes are not affected — the trunk is a separate directory and no update
path writes to it.

## Uninstalling

```bash
~/dev/greymatter/uninstall.sh
```

**Your trunk and your notes are never deleted.** Removed: the GreyMatter hooks
(the rest of `settings.json` untouched), the engine symlinks, the `brain`
command, the Desktop launcher, the scheduled jobs. Backups stay in
`~/.greymatter/backups/`.

<details>
<summary><b>Installed before v2.1.0, when the project was called C Brain?</b></summary> <!-- pre-rename -->

Your clone is still <!-- pre-rename -->
`~/dev/c-brain` and its `uninstall.sh` works the same: it hands over to the <!-- pre-rename -->
engine's own uninstaller, which knows both names. `~/.greymatter/engine/uninstall.sh`
is the same script, whichever way you installed.

</details>
