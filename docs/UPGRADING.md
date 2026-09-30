# Upgrading

Find the version you are coming from; the row tells you what to read and
whether you have anything to do. **Your notes are never touched by an update**,
whichever row is yours.

| Coming from | Read | Anything to do? |
|---|---|---|
| v2.2.0 | nothing — `brain update` | No |
| v2.1.1 | [The menu bar pill](#upgrading-to-v220--the-menu-bar-pill) | No. What you [declined at install](#if-you-declined-pieces-at-install) stays declined |
| v2.1.0 | [It asks before it updates](#upgrading-to-v211--it-asks-before-it-updates), then [the menu bar pill](#upgrading-to-v220--the-menu-bar-pill) | No — what you [declined at install](#if-you-declined-pieces-at-install) stays declined. `brain update --auto-on` if you preferred silent installs |
| v2.0.x | [One name](#upgrading-to-v210--one-name), then [it asks before it updates](#upgrading-to-v211--it-asks-before-it-updates), then [the menu bar pill](#upgrading-to-v220--the-menu-bar-pill) | Usually no. Yes if a job is "left running", or if you use the plugin. What you [declined at install](#if-you-declined-pieces-at-install) stays declined |
| **v1.28.1 or earlier** | [The one-time warning](#%EF%B8%8F-important--one-time-warning-before-upgrading-from-v1281-or-earlier) **first**, then [why 2.0.0](#why-this-is-200) and [the new install model](#what-changes-in-how-the-engine-is-installed) | **Yes — one command before you upgrade** |

## Upgrading to v2.2.0 — the menu bar pill

`brain update`, and say yes when your agent asks. **Your notes are not touched.**

| v2.1.1 | v2.2.0 |
|---|---|
| the floating orb, an Electron window | the menu bar pill, a native macOS program |
| the Desktop launcher opens the planet in your browser | the same launcher opens the map in its own window |
| `npm` builds the orb, optional | `swift` builds the pill, from the Command Line Tools |

**During the update** the installer stops the old orb, builds the pill (about
30 s) and starts it — unless you had declined the orb: see
[below](#if-you-declined-pieces-at-install). From then on each session start
opens the pill, never the orb. Without Swift only the pill is skipped, and
`brain capsule` then tells you how to add it: `xcode-select --install`, then
`./install.sh` again from your clone. The planet is still there, through
`planet/launch.sh`. Should an old orb still be on screen afterwards,
`brain capsule status` says so and `brain capsule` retires it.

### If you declined pieces at install

From v2.2.0 the installer remembers what you declined with `--core-only` or a
`--no-…` option, in `~/.greymatter/state/install-choices`. Every update and
every rollback reads it, so a declined piece stays declined. You have nothing
to do.

Before v2.2.0 there was no such record, and each update reinstalled every
piece. On the update that brings v2.2.0, the installer therefore reads your
Mac instead: a piece you had counts as chosen, and a piece you did not have
counts as declined.

| Declined with | Looked for on your Mac |
|---|---|
| `--no-launchd` | the two scheduled jobs' files, in `~/Library/LaunchAgents/` |
| `--no-capsule` | the floating orb, or the pill |
| `--no-planet` | `GreyMatter.app` on your Desktop |
| `--no-shortcut` | the `~/GreyMatter` shortcut |

Pieces installed under the names used before v2.1.0 count too.

**One case reads wrong.** A piece missing for another reason also counts as
declined. The usual one is the orb, which v2.1.1 skipped when `npm` was not
installed: you then get no pill after the update. `brain capsule` tells you
when that happened.

**To change your choices**, run `./install.sh` again from your clone:

- **With options:** they replace the record. Give only the options you still
  want.
- **With no option:** the record is kept, and the installer says which choices
  it kept.
- **For every piece:** delete `~/.greymatter/state/install-choices` first,
  then run `./install.sh` with no option.

`./uninstall.sh` deletes the record too.

### On a full menu bar

macOS tucks the icons furthest left behind the «
arrow when the bar runs out of room, and on macOS 27 a relaunched pill is placed
furthest left until the menu bar restarts. `killall MenuBarAgent` puts it back
in its place; macOS restarts the menu bar on its own within a second.

## Upgrading to v2.1.1 — it asks before it updates

From v1.28.0 to v2.1.0 every session start installed the newest version on its
own. From v2.1.1 session start only **looks**; when a newer version exists, your
agent **asks you**, once per version per day, and runs `brain update` if you say
yes. **Your notes are not touched.**

If you preferred the old way, one command brings it back:

```bash
brain update --auto-on    # install on its own again
brain update --auto-off   # back to asking
```

If v2.1.0 installed v2.1.1 on its own, the next session says so once, in its update report.

## Upgrading to v2.1.0 — one name

| Before v2.1.0 | From v2.1.0 |
|---|---|
| root `~/.c-brain` | `~/.greymatter` — the old path stays as a link | <!-- pre-rename -->
| Home shortcut `~/C Brain` | `~/GreyMatter` | <!-- pre-rename -->
| launchd jobs `com.claudebrain.*` | `com.greymatter.*` | <!-- pre-rename -->
| the Desktop app | `GreyMatter.app` |
| the plugin `c-brain` | `greymatter` | <!-- pre-rename -->

Until v2.1.0 the product was called GreyMatter while the machine still said
C Brain. From v2.1.0 every one of those names says GreyMatter. **Your notes are <!-- pre-rename -->
not touched.**

<details>
<summary><b>If you installed with <code>install.sh</code></b></summary>

Nothing to do. `brain update` (or `git pull && ./install.sh`) moves the root to
`~/.greymatter` and leaves a permanent link at the old path, so a script or an
alias that still names it keeps working. Then it replaces what it provably owns:
the scheduled jobs (by label), the hook commands in `~/.claude/settings.json`
(by path), the map app (by bundle id and the trunk it opens — rebuilt where you
moved it, never doubled on the Desktop) and the Home shortcut (by where it
points). A copy of the map app it says "could not be rebuilt" has a locked file in
it: delete that copy, then update again. Anything with the old name that it cannot prove is its own is left
alone.

**A job left under the old name.** If the installer says an old-label job is
"left running", it found one it has no record of installing — so it did not
touch it, and did not start the new one beside it. If you know it is an old
GreyMatter job, stop it and run the installer again:

```bash
launchctl bootout gui/$(id -u)/com.claudebrain.resume   # pre-rename; same for .machiniste
./install.sh
```

`brain update --rollback` to a v2.0.x version works: it switches the engine
back, removes the v2.1.0 hooks and jobs, and the older installer puts its own
back. The root stays at `~/.greymatter`; the old path reaches it through the link.

The Desktop app is now called `GreyMatter.app`. To uninstall, the `uninstall.sh`
of your old clone still works: it hands over to the engine's own uninstaller,
which knows both names.

</details>

<details>
<summary><b>If you installed the Claude Code plugin</b></summary>

The commands become `/greymatter:recall`, `/greymatter:distill`,
`/greymatter:doctor`. What we measured with Claude Code 2.1.283:

1. `claude plugin marketplace update c-brain` fetches v2.1.0. The plugin list <!-- pre-rename -->
   then marks yours "Renamed to greymatter", but it still runs v2.0.4, and
   `claude plugin update c-brain@c-brain` answers "Plugin not found". <!-- pre-rename -->
2. `claude plugin install greymatter@c-brain` is the step that moves you: it <!-- pre-rename -->
   installs v2.1.0 and the old entry disappears from `enabledPlugins`. Run it.
3. The marketplace keeps the name you added it under, so the plugin is listed as
   `greymatter@c-brain`. That is cosmetic. To get the new name there too, <!-- pre-rename -->
   remove the marketplace and add it again.

The plugin's first session moves `~/.c-brain` exactly as the installer does. <!-- pre-rename -->

</details>

## ⚠️ IMPORTANT — one-time warning, before upgrading from v1.28.1 or earlier

```bash
git -C ~/.greymatter/engine status --short
```

**Run that first.** If it lists files, your engine checkout has uncommitted
changes, and the old updater will discard them once, during the upgrade to
v2.0.0. Commit or stash them before you upgrade.

| What the command prints | What it means | What to do |
|---|---|---|
| **nothing at all** | your checkout is clean | nothing; upgrade normally |
| **a list of files** (`M hooks/something.py`, `M capsule/macos/Sources/Capsule/main.swift`, …) | those are the changes at risk | put them away first (below) |
| **`fatal: not a git repository`** | good news, and the clearest signal there is: your engine is already a managed version, not a checkout | nothing — this warning does not apply to you |

```bash
git -C ~/.greymatter/engine stash          # or: git -C ~/.greymatter/engine commit -a
```

Run the check even if you are sure you never edited the engine yourself: some
agent-driven setups accumulate edits under `agents/` without anyone typing a
command — the gardening agents reach those files through the trunk's symlinks.

<details>
<summary><b>Why it happens, and why v2.0.0 cannot prevent it</b></summary>

**If your current GreyMatter engine is a Git checkout that contains uncommitted
changes, commit or stash them before upgrading to v2.0.0.**

The updater bundled with older releases predates the managed-engine
architecture and may reset tracked engine files once during the upgrade. That
reset is performed by the code already installed on your machine, so v2.0.0
cannot prevent it — the older updater runs first, and it is what fetches and
installs the new version.

This is not a formality. `git checkout -- .` discards uncommitted changes to
tracked files without asking and without a copy. If you have edits in your
checkout that are not committed, **they are not recoverable afterwards.**

Reviewed after the September 2026 cleanup of comments in `install.sh` and
`greymatter/update.sh`: those edits changed attribution only. The upgrade
behavior and this warning remain the same.

</details>

<details>
<summary><b>What is at risk, and what is not</b></summary>

| | At risk |
|---|---|
| Uncommitted changes to **tracked engine files** in your checkout — `hooks/`, `capsule/`, `planet/`, `agents/`, `tests/`, and the rest of the code | **YES** |
| Committed work, on any branch | No — commits are not touched |
| Untracked files, and anything in `.gitignore` (`node_modules/`, local scratch files) | No — `git checkout -- .` only touches tracked files |
| **Your trunk — `~/.greymatter/trunk`, all of your notes** | **No.** The trunk is a separate directory with its own history. No update path has ever written to it, and none does now. |

The risk is confined to the *code* checkout, and only to changes you have not
committed there.

</details>

## Why this is 2.0.0

| What changed | Before | Since v2.0.0 |
|---|---|---|
| Recall | added 2–3 notes to **every** prompt | fires only when you ask |
| Agents | eight, one per job | four ships carrying the same eight jobs |

Two things you may rely on change meaning. Nothing is lost in either case, but
a habit or a script built on the old behaviour stops working the way it did.

<details>
<summary><b>Recall now waits to be asked</b></summary>

Until v1.28.1 the recall hook added two or three notes to **every** prompt.
Over a month of daily use, 3,256 notes were offered that way and 139 of them
were opened afterwards — 4.27 %. The block cost its noise on every message for
a service rendered about four times in a hundred, so it now fires only when you
ask:

- `brain recall "…"` from a terminal;
- `?brain` anywhere in a message;
- a plain request such as "search the brain", "any notes on…" or "have we seen
  this before" — in English or in French.

The search itself did not change. To get the old behaviour back, set
`BRAIN_RECALL_AUTO=1` in the environment your CLI agent starts from.

The ranking no longer learns from what you open. A note that had been opened
often used to climb; that weight is now fixed at 1.0, so the rank is the
relevance score alone. One slot in three is still kept for notes the search
rarely surfaces.

</details>

<details>
<summary><b>Eight agents became four, with the same eight jobs</b></summary>

The files `agents/mechanic.md`, `machinist.md`, `distiller.md`, `gardener.md`,
`challenger.md`, `architect.md`, `archivist.md` and `synthesizer.md` are gone.
Their work now runs under four agents, and the task you give names the job:

| Agent | Jobs it carries |
|---|---|
| `nostromo` | `mechanic`, `machinist` |
| `narcissus` | `distiller`, `gardener` |
| `sulaco` | `challenger`, `architect`, `archivist` |
| `anesidora` | `synthesizer` |

Each job keeps its own write permissions. If you launched an agent by its old
name — by hand, in a script, in a scheduled job — launch the ship instead and
name the job in the task, for example `nostromo` with "mechanic: …". The
automatic end-of-session pass already launches them this way. See
[agents/README.md](../agents/README.md).

</details>

## What changes in how the engine is installed

```
before v2.0.0     ~/.greymatter/engine  →  your clone (updated in place, by git)
since v2.0.0      ~/.greymatter/engine  →  ~/.greymatter/versions/<id>/  (built, immutable)
                  your clone            =  a source: read once, never written again
```

**There is nothing to run** — no migration script, no command. After v2.0.0, GreyMatter no longer uses
your checkout as the installed engine. An older installation upgrades itself: its updater
installs v2.0.0, which replays the new installer, which builds a managed
version from what was checked out and repoints the engine at it. From that
moment your checkout is a source, and stays one. The background is in
[install-model.md](install-model.md).

This part was written for a v1.29.0 that was never tagged; it ships in v2.0.0
unchanged.

<details>
<summary><b>Everything that changes, point by point</b></summary>

- **Source checkouts are left untouched.** The repository you cloned is a SOURCE.
  The installer reads it to build an engine and never writes to it again. Update
  it with `git`, like any other repository — `brain update` has nothing to do
  with it and cannot move, reset or overwrite it.
- **Installed engines live under `~/.greymatter/versions/`.** Each one is an
  immutable export: no `.git`, no history, code only, with a
  `.greymatter-manifest` recording a checksum per file.
- **`~/.greymatter/engine` points to the active managed version.** Switching
  version is a single atomic symlink rename — nothing is copied over anything.
- **Updates test a candidate before switching.** The new version is built,
  verified against its manifest, migrated and selftested *while it is still
  inactive*. Only a green candidate becomes the engine; a red one is deleted and
  the running version is never involved.
- **Rollback switches between managed versions.** No checkout, no network. If
  the version being rolled back to is no longer on disk, the rollback refuses
  and says which versions remain, rather than landing somewhere else.
- **What the reinstall printed is kept.** After switching, the update replays
  the installer and keeps its output. The updater you run is the one you are
  coming FROM: up to v2.1.1 it writes `/tmp/greymatter-update.log`; from v2.2.0
  on it writes `~/.greymatter/state/update.log`.
- **The trunk is not touched.** As before, and now structurally: no git command
  in the update path names the trunk.
- **`install.sh --dry-run` is inert, and reaches the end.** Reviewed 2026-08-26,
  because this release is the one people will want to preview before running
  it: until then the preview created `~/.greymatter` before it had read its own
  flag, and then died at "Engine linked into the trunk" with no message and
  exit 2.
- **The installer's closing verification tests the version it just built.** It
  used to fall back to whichever `brain` was on PATH — nothing at all on a clean
  machine, so a healthy install ended on "some hooks are broken"; the other
  installation's engine on a machine that already had GreyMatter. Nothing else
  in the upgrade path changes: the warning above still applies exactly as
  written.
- **Older trunks receive ranking defaults only if missing.** The installer
  copies `config/ranking.json` into an existing trunk only when it has no copy.
  A user configuration is never replaced by this default.
- **The installer's last screen says what happened.** It used to end on
  "installed" whatever had occurred above it. When the `brain` command is not on
  your PATH yet, the ending now says so, with the one-line export that fixes it
  and a full-path command that works right away (`tests/closing_verdict.sh`).
  Since v2.0.3 a red selftest is said on that screen even when the PATH advice
  is there too, and the installer exits 1, so a script, a CI job or an agent
  running it sees the failure (`tests/install_exit_code.sh`). That includes an
  install over another installation's agents folder: Claude Code cannot reach
  GreyMatter's agents there, the verification was already red in v2.0.2 behind
  an exit 0, and the closing screen no longer calls that install "working"
  (`tests/e2e_occupied_surfaces.sh`). An update that replays `install.sh` still
  treats that exit as a warning: the candidate's own selftest is what decides
  the switch.
- **No stray "Abort trap: 6".** Checking a capsule whose Electron is broken no
  longer prints the shell's crash report in the middle of the install.
- **One commit, one engine.** Installing from a clone with uncommitted edits no
  longer builds a second `…-dirty` copy of the same version: those edits are not
  in the engine, and the installer says so instead of renaming it.

</details>

<details>
<summary><b>If you work ON GreyMatter</b></summary>

Run the installer once with `--dev`:

```bash
./install.sh --dev
```

This is the only mode in which the engine may be a working checkout. It links
the engine to your checkout, records the choice in
`~/.greymatter/state/engine-dev`, and `brain update` then refuses by name:

```
Development engine detected.
Automatic engine updates are disabled for --dev installations.
```

No checkout, no reset, no fetch. Update your checkout with git.

</details>

<details>
<summary><b>Your scheduled jobs will be left alone, and told so</b></summary>

An update replays `install.sh`. From now on the installer refuses to unload a
launchd Label it holds no record of owning — and an installation made before
that record existed has none. So on the first update you will see, by name:

    ! The service com.greymatter.resume already exists, and this installation
      holds no proof that it owns it. NOTHING was changed [...]

**Nothing is broken**: the jobs keep running exactly what they were running.
The message names the command that adopts them. Until you run it, the plist is
no longer rewritten by an update, so a future change to the job definition will
not reach this machine — that is the price of not guessing whose job it is.

</details>

## For whoever published v2.0.0

`CHANGELOG.md` is generated from annotated tags, so the warning has to be in
the tag message or it will not appear there at all. Written here in advance, on
purpose: this is a safety instruction, and a safety instruction improvised at
`publish.sh` time is one that gets shortened. v2.0.0 is out; the message stays here
as the record of what it said.

<details>
<summary><b>The tag message, as written</b></summary>

```bash
./publish.sh v2.0.0 "Recall on request, four agents, and a source that is no longer the engine

⚠️ UPGRADING FROM v1.28.1 OR EARLIER — ONE-TIME WARNING
If your engine is a Git checkout with uncommitted changes, commit or stash them
BEFORE upgrading. The updater in older releases predates this architecture and
resets tracked engine files once during the upgrade; it runs before v2.0.0
exists on your machine, so this release cannot prevent it.
Check with:  git -C ~/.greymatter/engine status --short
Your notes are NOT affected: the trunk is untouched by every update path.
Full note: docs/UPGRADING.md

Installed engines are now immutable versions under ~/.greymatter/versions/, and
~/.greymatter/engine points at the active one. Your clone is a source and is never
written to again. An update builds a candidate, selftests it while it is still
inactive, and switches only if it is green. Rollback repoints the link at a
version already known good. install.sh --dev is the one mode where the engine
may be a working checkout, and it is never auto-updated.

Recall now fires only when you ask (brain recall, ?brain, or a plain request);
BRAIN_RECALL_AUTO=1 restores it on every prompt. The eight agents are now four
- nostromo, narcissus, sulaco, anesidora - carrying the same eight jobs; a
script that launched an agent by its old name must name the ship instead."
```

</details>
