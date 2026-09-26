# Upgrading

## ⚠️ IMPORTANT — one-time warning, before upgrading from v1.28.1 or earlier

**If your current C Brain engine is a Git checkout that contains uncommitted
changes, commit or stash them before upgrading to v2.0.0.**

The updater bundled with older releases predates the managed-engine architecture
and may reset tracked engine files once during the upgrade. That reset is
performed by the code already installed on your machine, so v2.0.0 cannot
prevent it — the older updater runs first, and it is what fetches and installs
the new version.

Reviewed after the September 2026 cleanup of comments in `install.sh` and
`cbrain/update.sh`: those edits changed attribution only. The upgrade behavior
and this warning remain the same.

This is not a formality. `git checkout -- .` discards uncommitted changes to
tracked files without asking and without a copy. If you have edits in your
checkout that are not committed, **they are not recoverable afterwards.**

### What is at risk, and what is not

| | At risk |
|---|---|
| Uncommitted changes to **tracked engine files** in your checkout — `hooks/`, `capsule/`, `planet/`, `agents/`, `tests/`, and the rest of the code | **YES** |
| Committed work, on any branch | No — commits are not touched |
| Untracked files, and anything in `.gitignore` (`node_modules/`, local scratch files) | No — `git checkout -- .` only touches tracked files |
| **Your trunk — `~/.c-brain/trunk`, all of your notes** | **No.** The trunk is a separate directory with its own history. No update path has ever written to it, and none does now. |

The risk is confined to the *code* checkout, and only to changes you have not
committed there.

### How to check, in one command

```bash
git -C ~/.c-brain/engine status --short
```

Read the output like this:

- **Nothing at all** — your checkout is clean. Nothing to do; upgrade normally.
- **A list of files** (`M hooks/something.py`, `M capsule/main.js`, …) — those are
  the changes at risk. Put them away first:

  ```bash
  git -C ~/.c-brain/engine stash          # or: git -C ~/.c-brain/engine commit -a
  ```

- **`fatal: not a git repository`** — good news, and the clearest signal there is:
  your engine is already a managed version rather than a checkout, so this whole
  warning does not apply to you.

Some agent-driven setups accumulate edits under `agents/` without anyone typing a
command — the gardening agents reach those files through the trunk's symlinks. So
run the check even if you are sure you never edited the engine yourself.

---

## Why this is 2.0.0

Two things you may rely on change meaning. Nothing is lost in either case, but
a habit or a script built on the old behaviour stops working the way it did.

### Recall now waits to be asked

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

### Eight agents became four, with the same eight jobs

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
automatic end-of-session pass already launches them this way. See [agents/README.md](../agents/README.md).

---

## What changes in how the engine is installed

This part was written for a v1.29.0 that was never tagged; it ships in v2.0.0
unchanged. After v2.0.0, C Brain no longer uses your checkout as the installed
engine.

- **Source checkouts are left untouched.** The repository you cloned is a SOURCE.
  The installer reads it to build an engine and never writes to it again. Update
  it with `git`, like any other repository — `brain update` has nothing to do
  with it and cannot move, reset or overwrite it.
- **Installed engines live under `~/.c-brain/versions/`.** Each one is an
  immutable export: no `.git`, no history, code only, with a `.cbrain-manifest`
  recording a checksum per file.
- **`~/.c-brain/engine` points to the active managed version.** Switching version
  is a single atomic symlink rename — nothing is copied over anything.
- **Updates test a candidate before switching.** The new version is built,
  verified against its manifest, migrated and selftested *while it is still
  inactive*. Only a green candidate becomes the engine; a red one is deleted and
  the running version is never involved.
- **Rollback switches between managed versions.** No checkout, no network. If the
  version being rolled back to is no longer on disk, the rollback refuses and
  says which versions remain, rather than landing somewhere else.
- **The trunk is not touched.** As before, and now structurally: no git command
  in the update path names the trunk.
- **`install.sh --dry-run` is inert, and reaches the end.** Reviewed 2026-08-26,
  because this release is the one people will want to preview before running it:
  until then the preview created `~/.c-brain` before it had read its own flag,
  and then died at "Engine linked into the trunk" with no message and exit 2.
- **The installer's closing verification tests the version it just built.** It
  used to fall back to whichever `brain` was on PATH — nothing at all on a clean
  machine, so a healthy install ended on "some hooks are broken"; the other
  installation's engine on a machine that already had C Brain. Nothing else in
  the upgrade path changes: the warning above still applies exactly as written.
- **Older trunks receive ranking defaults only if missing.** The installer copies
  `config/ranking.json` into an existing trunk only when it has no copy. A user
  configuration is never replaced by this default.
- **The installer's last screen says what happened.** It used to end on
  "installed" whatever had occurred above it. When the `brain` command is not on
  your PATH yet, the ending now says so, with the one-line export that fixes it
  and a full-path command that works right away (`tests/closing_verdict.sh`).
- **No stray "Abort trap: 6".** Checking a capsule whose Electron is broken no
  longer prints the shell's crash report in the middle of the install.
- **One commit, one engine.** Installing from a clone with uncommitted edits no
  longer builds a second `…-dirty` copy of the same version: those edits are not
  in the engine, and the installer says so instead of renaming it.

### If you work ON C Brain

Run the installer once with `--dev`:

```bash
./install.sh --dev
```

This is the only mode in which the engine may be a working checkout. It links the
engine to your checkout, records the choice in `~/.c-brain/state/engine-dev`, and
`brain update` then refuses by name:

```
Development engine detected.
Automatic engine updates are disabled for --dev installations.
```

No checkout, no reset, no fetch. Update your checkout with git.

### Your scheduled jobs will be left alone, and told so

An update replays `install.sh`. From now on the installer refuses to unload a
launchd Label it holds no record of owning — and an installation made before
that record existed has none. So on the first update you will see, by name:

    ! The service com.claudebrain.resume already exists, and this installation
      holds no proof that it owns it. NOTHING was changed [...]

**Nothing is broken**: the jobs keep running exactly what they were running. The
message names the command that adopts them. Until you run it, the plist is no
longer rewritten by an update, so a future change to the job definition will not
reach this machine — that is the price of not guessing whose job it is.

### Nothing else to do

There is no migration script and no command to run. An older installation
upgrades itself: its updater installs v2.0.0, which replays the new installer,
which builds a managed version from what was checked out and repoints the engine
at it. From that moment your checkout is a source, and stays one.

The background is in [install-model.md](install-model.md).

---

## For whoever publishes v2.0.0

`CHANGELOG.md` is generated from annotated tags, so the warning has to be in the
tag message or it will not appear there at all. Written here in advance, on
purpose: this is a safety instruction, and a safety instruction improvised at
`publish.sh` time is one that gets shortened.

Use it as is:

```bash
./publish.sh v2.0.0 "Recall on request, four agents, and a source that is no longer the engine

⚠️ UPGRADING FROM v1.28.1 OR EARLIER — ONE-TIME WARNING
If your engine is a Git checkout with uncommitted changes, commit or stash them
BEFORE upgrading. The updater in older releases predates this architecture and
resets tracked engine files once during the upgrade; it runs before v2.0.0
exists on your machine, so this release cannot prevent it.
Check with:  git -C ~/.c-brain/engine status --short
Your notes are NOT affected: the trunk is untouched by every update path.
Full note: docs/UPGRADING.md

Installed engines are now immutable versions under ~/.c-brain/versions/, and
~/.c-brain/engine points at the active one. Your clone is a source and is never
written to again. An update builds a candidate, selftests it while it is still
inactive, and switches only if it is green. Rollback repoints the link at a
version already known good. install.sh --dev is the one mode where the engine
may be a working checkout, and it is never auto-updated.

Recall now fires only when you ask (brain recall, ?brain, or a plain request);
BRAIN_RECALL_AUTO=1 restores it on every prompt. The eight agents are now four
- nostromo, narcissus, sulaco, anesidora - carrying the same eight jobs; a
script that launched an agent by its old name must name the ship instead."
```
