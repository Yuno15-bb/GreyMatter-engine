# The install model: a source is not an engine

Decided 2026-08-17, after chantier #9 measured a contradiction between two
correct fixes: the documented install path produced exactly the object the
updater had just learned to refuse.

This document draws the target model, the migration of existing installs, and
the behaviour of every command that touches an engine. It is the reference the
implementation and the end-to-end contract are written against.

## The one sentence

`install.sh` used to **observe** whether the engine happened to be clean,
detached and on a release tag. It never **put** it there. Ownership was inferred
from a state the installer had not created — and `git clone` never produces that
state, so a documented install could never be updated.

Inference cannot answer the question. A clean development checkout sitting on a
tag is indistinguishable from an install, and always will be. So we stop asking:
the installer **creates** what it owns, and owns nothing else.

## The layout

```
~/.c-brain/
├── source.git/                bare mirror the installer owns — where updates come from
├── versions/
│   ├── v1.28.1/               an immutable engine: no .git, no history, code only
│   └── v1.29.0/
├── engine -> versions/v1.29.0 the active version. One symlink.
├── runtime/
│   └── electron/              ~250 MB, installed once, shared by every version
├── state/                     survives every switch
│   ├── engine-managed         provenance: this installation created versions/
│   ├── engine-dev             present ONLY in --dev mode, mutually exclusive
│   ├── previous-version       a version directory name, not a git ref
│   ├── applied-migrations.txt
│   └── tag-family
├── trunk/                     the user's notes. Nothing above ever writes here.
├── backups/
└── VERSION, manifest.txt
```

`~/c-brain` — the user's clone — is a **source**. It is read to build a version
and never written to again.

### Why the switch is one symlink

Measured on the current tree: everything already resolves *through*
`~/.c-brain/engine`, so nothing has to be rewritten when the active version
changes.

| What | Points at | Where |
|---|---|---|
| trunk mounts (`hooks`, `agents`, `capsule`, `planet`, `companion`, `tests`) | `$CB/engine/<dir>` | `install.sh:193` |
| the `brain` CLI | `$CB/engine/brain` | `install.sh:198` |
| Claude Code hooks in `settings.json` | `~/.c-brain/engine/...` | `merge_settings.py:69` |
| launchd jobs | `~/.c-brain/trunk/hooks/...` → engine | plist templates |
| the Desktop planet launcher | `$TRUNK/planet/launch.sh` → engine | `install.sh:398` |

One exception: `~/.claude/statusline.py` is a **copy** (`install.sh:227`), not a
link. It is refreshed by the `install.sh` replay that follows every switch.

So a version switch is `ln -sfn` + `mv -f` on a single symlink — one `rename(2)`,
atomic. There is no window in which half the installation is on the new version.

## Behaviour, command by command

### `install.sh` (normal)

1. Read the version identity from the source it is run from:
   `git describe --tags --always` — `v1.29.0` when detached on a tag,
   `v1.28.1-24-g6f28312` for a plain clone of `main`. Both are valid names.
   **The documented `git clone && ./install.sh` keeps working unchanged**, and
   produces an updatable install. That is the whole point of the chantier.
2. Build `versions/<id>/` with `git archive <HEAD> | tar -x`. 162 files, 11.6 MB
   measured. The source is read, never written.
3. Write `versions/<id>/.cbrain-manifest`: sha256 of every file. This is the
   immutability oracle, and it replaces the git-based dirt check, since a
   version has no `.git`.
4. Mirror the source into `source.git`, so updates have an origin that does not
   live in anybody's working repository.
5. Link `runtime/electron` into `versions/<id>/capsule/node_modules`. Electron is
   installed once, not once per version — otherwise each version would cost
   250 MB instead of 11.6 MB.
6. Write `state/engine-managed`, remove `state/engine-dev`.
7. Point `engine` at `versions/<id>`, then do everything the installer already
   does: trunk, mounts, CLI, hooks, launchd, planet, shortcut, verification.

Idempotent: re-running with the same source rebuilds nothing if
`.cbrain-manifest` already matches.

### `install.sh --dev`

The only mode in which an engine may be a working checkout, and it must be
asked for by name.

- `engine` → the checkout itself, exactly as today.
- Writes `state/engine-dev` (the checkout path); removes `state/engine-managed`.
- Creates no `versions/` entry and no mirror.
- Prints, so nobody discovers it later:
  `development engine — automatic updates are OFF for this install`.

### `brain update`

The gate is now structural. It does not reason about branches, tags or dirt to
decide *whose* repo this is; it reads provenance.

1. `state/engine-dev` present →
   ```
   Development engine detected.
   Automatic engine updates are disabled for --dev installations.
   ```
   No checkout, no reset, no fetch. Exit 0 under `--auto` (this is a
   configuration, not a failure); exit 1 by hand.
2. `state/engine-managed` absent, or `engine` resolving outside `versions/` →
   refuse without touching anything.
3. `git fetch --tags` into **`source.git`**. No git command ever runs against a
   directory the user created.
4. Build `versions/<new>` from the mirror, link the shared runtime, run pending
   migrations.
5. **Selftest the new version while it is still inactive.** `selftest.sh` gains
   an optional engine-path argument so a version can be checked before anything
   points at it. This is the ordering the old model could not offer: it checked
   out first and hoped.
6. Green → atomic switch of `engine`, then replay `install.sh` to refresh the
   copies (statusline) and the mounts. Record the outgoing version in
   `state/previous-version`.
   Red → **delete `versions/<new>`**. `engine` never moved. There is nothing to
   roll back from, because nothing was ever switched.

### `brain update --rollback`

Repoint `engine` at `versions/<previous-version>`, replay `install.sh`, selftest.
No git, no checkout, no network. If that directory no longer exists, refuse and
say which versions are retained — a rollback that silently lands somewhere else
is worse than one that refuses.

Retention: the active version, the previous one, and one spare. Older ones are
pruned at the end of a successful update.

### `uninstall.sh`

`--purge-engine` can finally do what its name says: remove `versions/`,
`source.git` and `runtime/`, because the installer created all three. The user's
source clone stays on disk, untouched — it was never ours to delete. Without the
flag, nothing changes.

### `brain doctor`

- Today it runs `git -C engine status` to detect a dirty engine
  (`brain_doctor.py:248`). A versioned engine has no `.git`, so that check is
  replaced by verifying `.cbrain-manifest`.
- Any difference is reported as an **anomaly, never repaired**. An immutable
  version that changed is a fact the user needs to see, not a mess to tidy away
  behind their back.
- In `--dev` mode the git-based check is kept, and doctor says which mode the
  install is in and which version is active.

### `selftest.sh`

Gains an optional engine path. Called with none, it behaves exactly as today.

## Migration of existing installs

Measured, not assumed — replayed in a sandbox with a laboratory origin, the real
`install.sh` and the real `brain update`.

1. Today's installed users run **v1.28.1 or older, which contain no gate at all**
   (verified: neither `engine-managed` nor `gate_ownership` appears in
   `v1.27.1`, `v1.28.0` or `v1.28.1`). Their `engine` is a symlink to their own
   clone.
2. Their **old** updater fetches and runs `git checkout v1.29.0` **inside that
   clone**. This is the last mutation their source will ever suffer, and it
   cannot be prevented: the code performing it is already on their disk.
3. It then replays the **new** `install.sh` from the checked-out v1.29.0.
4. The new installer sees `engine` resolving outside `versions/`, and converts:
   builds `versions/v1.29.0/` from that checkout, mirrors `source.git`, writes
   `engine-managed`, repoints `engine`.
5. From that moment the clone is a source. Nothing writes to it again.

Measured end state of the equivalent sequence: `branch main` →
`detached v1.29.0` → marker written. The conversion self-heals; there is no
migration script for the user to run.

**The one honest cost, for the release notes.** The old updater has no gate, so
for a user with uncommitted work in their clone, step 2 runs `git checkout -- .`
one final time and discards it. We cannot fix that from here — it is the code
already installed. The release note must say, plainly: *commit or stash anything
in your c-brain clone before updating to v1.29.0.*

Developers convert by running `./install.sh --dev` once.

## Two consequences we are choosing, not hiding

**Agent briefs.** `agents/` is mounted into the trunk from the engine
(`cbrain/engine-paths.txt`), and the gardening agents edit `agents/*.md` through
those links — the incident reported by Maissane Lagsir on 2026-08-16. Under an
immutable engine those edits land in a version that is not supposed to change:
doctor will flag them, and a version switch will drop them. That is the correct
behaviour for "immutable", and it is a real change from today. Named here, not
fixed here.

**Disk.** 11.6 MB per retained version, plus one shared 250 MB Electron runtime,
plus the mirror. Three versions retained ≈ 35 MB of engine.

## What this buys

- **P1 is structural.** The updater has no code path that writes to a directory
  the user created. There is nothing left to detect, so there is nothing left to
  get wrong.
- **P2 is structural.** The installer creates the engine, therefore it owns it.
  The marker records a provenance instead of passing a verdict on a git state.
- **P3 is unchanged** and now trivially auditable: no git command in the update
  path names the trunk.
- **Rollback stops being a gamble.** Repointing a symlink at a directory that was
  already tested beats checking out and hoping.
- **GMatter inherits it.** An app that ships as a bundle has no clone to adopt.
  A versioned, replaceable engine beside a durable trunk is the model it needs,
  and this is that model, built early.
