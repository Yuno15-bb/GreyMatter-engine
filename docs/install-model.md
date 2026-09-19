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
| launchd jobs | `~/.c-brain/trunk/hooks/...` → engine | plist templates, **guarded** — see below |
| the Desktop planet launcher | `$TRUNK/planet/launch.sh` → engine | `install.sh:398` |

One exception: `~/.claude/statusline.py` is a **copy** (`install.sh:227`), not a
link. It is refreshed by the `install.sh` replay that follows every switch.

### launchd jobs are the one thing the installer may not simply replace

`launchctl` indexes the per-user domain by **Label**, not by `$HOME` and not by
the path of the plist. `launchctl unload <path>` therefore frees whatever the
domain holds under the Label written *inside* that file — including a job a
different installation loaded from somewhere else. On 2026-08-18 that took the
author's `com.claudebrain.resume` and `.machiniste` over for about 28 hours, and
the plists on disk never changed: it was invisible to `ls`, `cat` and `shasum`.

So ownership of a Label is a **recorded fact**, `state/launchd-owned`, written
only after a successful `load` — the same shape as `state/engine-managed` for
the engine. It is never inferred from the Label, the `com.claudebrain.*` prefix,
the plist on disk, `$HOME`, or `ProgramArguments`.

| Situation | What the installer does |
|---|---|
| the Label is not in the domain | registers it, then records it |
| it is there **and** recorded | unloads and reloads, and **checks the result** |
| it is there and **not** recorded | refuses by name, writes nothing, touches nothing — not even the plist file |

A job installed before that record existed is adopted by a separate, deliberate
command, `cbrain/adopt-launchd.sh <label>`. No automatic path calls it. It
requires two concordances **before** it asks anything — the live service must
run this installation's program from the expected plist, and that plist must be
equivalent to the template this installation would render, under the normal form
in `cbrain/plist_normalise.py` — and then an explicit human confirmation. The
two together do not discover who loaded the job; nothing can. They say the
service matches this installation today, and the person decides.

So a version switch is `ln -sfn` + **`mv -hf`** on a single symlink — one
`rename(2)`, atomic. There is no window in which half the installation is on the
new version.

⚠️ `-h` is not a detail, and leaving it out does not fail — it does something
else. `~/.c-brain/engine` is a symlink to a DIRECTORY, so plain `mv -f` follows
it and moves the new link *inside* the old version: the engine never switches,
and an immutable version quietly gains a stray file that breaks its own manifest.
Written that way first, and it still looked like it worked — the `install.sh`
replay relinks the engine afterwards with `rm` + `ln -s`, so the real switch was
happening non-atomically, in another file, by accident. The end-to-end test found
it on its second run; no component test could have.

### Nor the surfaces it shares with the rest of the machine

Three paths do not belong to the installation that writes them: `~/.claude/agents`,
`~/.claude/statusline.py` and `~/.local/bin/brain`. They live outside `~/.c-brain`,
one machine can hold several C Brains, and the first one there is using them.

On 2026-08-19 an install ran on a machine that already had the author's. It
repointed the agents link at its own trunk and overwrote the status line, printed
`backed up:` and `+`, and exited 0. The other installation went on calling agents
that were no longer where it had left them: **118 `agent not found` in 39 hours**,
its distillation dead, and no line anywhere saying a foreign surface had been
taken. The timestamped backup was real, and it is what allowed the repair — the
defect is the silent takeover, not a missing backup.

The answer is the launchd answer, one surface over. Ownership is a **recorded
fact** and never inferred — not from the name of the file, not from "it looks
like something C Brain writes". The record already existed and was simply never
read: `manifest.txt`, appended to after every successful placement, written for
the uninstaller.

| Situation | What the installer does |
|---|---|
| nothing is there | places it, then records it |
| it is there **and** recorded | backs it up and replaces it, silently — a re-install must not become a wall |
| it is there and **not** recorded | names it, says what occupies it and what C Brain loses, changes nothing |

A refusal is a reported outcome, not a crash: everything else installs, and the
closing screen counts what was left alone — a message printed three screens up
has scrolled away, which is the defect C bis A4 named for the PATH warning. The
next step is the one the refusal prints, `mv <path> <path>.before-c-brain`
followed by a re-run, and `tests/e2e_occupied_surfaces.sh` runs that gesture
rather than describing it.

Inside `~/.c-brain` there is no gate. That directory **is** the installation, and
gating it would make a legitimate re-install refuse its own engine.

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
   does: trunk, mounts, CLI, hooks, launchd, planet, shortcut, verification —
   leaving alone every shared surface it cannot prove it placed.

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

**It resolves `~/.c-brain` exactly the way the installer does** (2026-08-26). The
two scripts decide ownership by comparing PATHS — is this shortcut the one we
made, is this engine the one we built — and a comparison is only as good as the
spelling on both sides. The installer canonicalises with `pwd -P`; uninstall did
not, so wherever `$HOME` goes through a symlink (every `mktemp -d` on macOS, and
the CI runner) it read the Finder shortcut it had just created, saw
`/private/var/…` where it expected `/var/…`, concluded the link was somebody
else's and left it on the machine. Same trap as the ownership record install.sh
already warns about, one file further on.

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

**And `install.sh` now always names it** (2026-08-26). With no argument the
selftest resolves the CLI through the trunk, then through PATH — neither of which
belongs to the version being installed. A fresh machine has no `brain` on PATH at
that moment, so the installer's own verification went red on a healthy tree; a
machine that already had C Brain gave it the OTHER installation's engine to test.
The rule the header states — when an engine is named, its own `brain` is the only
one allowed — is exactly what an installer is in a position to guarantee, so it
does. `brain update` already named the candidate it was about to switch to.

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

The installer **says so when it happens**. A conversion changes what somebody's
checkout IS, inside an automatic update they did not watch, so the notice goes
into the update log at the moment it applies rather than waiting to be looked up:
what the checkout was, what the engine is now, and that `brain update` will not
touch the checkout again. It fires only on a conversion — an ordinary re-install
is silent, because a notice printed every time stops being read.

Measured end state of the equivalent sequence: `branch main` →
`detached v1.29.0` → marker written. The conversion self-heals; there is no
migration script for the user to run.

**The one honest cost, and it has its own document** — [UPGRADING.md](UPGRADING.md). The old updater has no gate, so
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
