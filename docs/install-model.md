# The install model: a source is not an engine

Your clone is read once, to build the engine, and nothing writes to it again.
This page is the reference the installer, the updater and their end-to-end
tests are written against.

[The idea](#the-idea) · [The layout](#the-layout) ·
[Ownership](#ownership-is-recorded-never-guessed) ·
[Command by command](#behaviour-command-by-command) ·
[Migration](#migration-of-existing-installs) ·
[Chosen costs](#two-consequences-we-are-choosing-not-hiding) ·
[What this buys](#what-this-buys)

Decided 2026-08-17, after an audit (work item #9) measured a contradiction
between two correct fixes: the documented install path produced exactly the
object the updater had just learned to refuse.

## The idea

| | Up to v1.28.1 | Since v1.29.0 |
|---|---|---|
| The engine is | your clone | a version the installer built, `versions/<id>/` |
| Who owns it | *inferred* from its git state | *recorded*: `state/engine-managed` |
| An update writes into | your clone | a mirror the installer owns, `source.git` |
| A failed update | leaves a half-checked-out clone | deletes the candidate; nothing had switched |

`install.sh` used to **observe** whether the engine happened to be clean,
detached and on a release tag. It never **put** it there. Ownership was inferred
from a state the installer had not created — and `git clone` never produces that
state, so a documented install could never be updated.

Inference cannot answer the question. A clean development checkout sitting on a
tag is indistinguishable from an install, and always will be. So we stop asking:
the installer **creates** what it owns, and owns nothing else.

## The layout

```
~/.greymatter/
├── source.git/                bare mirror the installer owns — where updates come from
├── versions/
│   ├── v1.28.1/               an immutable engine: no .git, no history, code only
│   └── v1.29.0/
├── engine -> versions/v1.29.0 the active version. One symlink.
├── runtime/
│   └── capsule-native-<hash>/ the menu bar pill's binary, keyed by its Swift sources
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

`~/greymatter` — the user's clone — is a **source**. It is read to build a
version and never written to again. Switching versions changes one symlink,
`engine`, and nothing else.

<details>
<summary><b>Why the switch is one symlink</b></summary>

Measured on the current tree: everything already resolves *through*
`~/.greymatter/engine`, so nothing has to be rewritten when the active version
changes.

| What | Points at | Where |
|---|---|---|
| trunk mounts (`hooks`, `agents`, `capsule`, `planet`, `companion`, `tests`) | `$GM/engine/<dir>` | `install.sh` §3 |
| the `brain` CLI | `$GM/engine/brain` | `install.sh` §4 |
| Claude Code hooks in `settings.json` | `~/.greymatter/engine/...` | `merge_settings.py` |
| launchd jobs | `~/.greymatter/trunk/hooks/...` → engine | plist templates, **guarded** — see [ownership](#ownership-is-recorded-never-guessed) |
| the Desktop planet launcher | `$TRUNK/gmtr/launch.sh` → engine (GMTR map, since v2.2) | `install.sh` §9 |

One exception: `~/.claude/statusline.py` is a **copy** (`install.sh` §6), not a
link. It is refreshed by the `install.sh` replay that follows every switch.

So a version switch is `ln -sfn` + **`mv -hf`** on a single symlink — one
`rename(2)`, atomic. There is no window in which half the installation is on the
new version.

</details>

<details>
<summary><b>⚠️ Why <code>mv -hf</code> and not <code>mv -f</code></b></summary>

`-h` is not a detail, and leaving it out does not fail — it does something
else. `~/.greymatter/engine` is a symlink to a DIRECTORY, so plain `mv -f`
follows it and moves the new link *inside* the old version: the engine never
switches, and an immutable version quietly gains a stray file that breaks its
own manifest.

Written that way first, and it still looked like it worked — the `install.sh`
replay relinks the engine afterwards with `rm` + `ln -s`, so the real switch was
happening non-atomically, in another file, by accident. The end-to-end test
found it on its second run; no component test could have.

</details>

## Ownership is recorded, never guessed

| What the installer touches | Where ownership is recorded | Already there, not recorded |
|---|---|---|
| the engine, inside `~/.greymatter` | `state/engine-managed` | no gate: that directory **is** the installation |
| a launchd job (its Label) | `state/launchd-owned` | refuses by name, writes nothing |
| `~/.claude/agents`, `~/.claude/statusline.py`, `~/.local/bin/brain` | `manifest.txt` | names it, changes nothing |

Two things live outside the installer's own folder and can belong to someone
else: launchd jobs, and three paths shared with the rest of the machine. For
both, ownership is a **recorded fact** written only after a successful
placement — never inferred from a name, a prefix or "it looks like something
GreyMatter writes".

Inside `~/.greymatter` there is no gate. That directory **is** the
installation, and gating it would make a legitimate re-install refuse its own
engine.

<details>
<summary><b>launchd jobs — the incident, and the rule</b></summary>

`launchctl` indexes the per-user domain by **Label**, not by `$HOME` and not by
the path of the plist. `launchctl unload <path>` therefore frees whatever the
domain holds under the Label written *inside* that file — including a job a
different installation loaded from somewhere else. On 2026-08-18 that took the
author's `com.greymatter.resume` and `.machiniste` over for about 28 hours, and
the plists on disk never changed: it was invisible to `ls`, `cat` and `shasum`.

So ownership of a Label is a **recorded fact**, `state/launchd-owned`, written
only after a successful `load` — the same shape as `state/engine-managed` for
the engine. It is never inferred from the Label, the `com.greymatter.*` prefix,
the plist on disk, `$HOME`, or `ProgramArguments`.

| Situation | What the installer does |
|---|---|
| the Label is not in the domain | registers it, then records it |
| it is there **and** recorded | unloads and reloads, and **checks the result** |
| it is there and **not** recorded | refuses by name, writes nothing, touches nothing — not even the plist file |

A job installed before that record existed is adopted by a separate, deliberate
command, `greymatter/adopt-launchd.sh <label>`. No automatic path calls it. It
requires two concordances **before** it asks anything — the live service must
run this installation's program from the expected plist, and that plist must be
equivalent to the template this installation would render, under the normal
form in `greymatter/plist_normalise.py` — and then an explicit human
confirmation. The two together do not discover who loaded the job; nothing can.
They say the service matches this installation today, and the person decides.

</details>

<details>
<summary><b>The three shared paths — the incident, and the rule</b></summary>

Three paths do not belong to the installation that writes them:
`~/.claude/agents`, `~/.claude/statusline.py` and `~/.local/bin/brain`. They
live outside `~/.greymatter`, one machine can hold several GreyMatters, and the
first one there is using them.

On 2026-08-19 an install ran on a machine that already had the author's. It
repointed the agents link at its own trunk and overwrote the status line,
printed `backed up:` and `+`, and exited 0. The other installation went on
calling agents that were no longer where it had left them: **118
`agent not found` in 39 hours**, its distillation dead, and no line anywhere
saying a foreign surface had been taken. The timestamped backup was real, and
it is what allowed the repair — the defect is the silent takeover, not a
missing backup.

The answer is the launchd answer, one surface over. The record already existed
and was simply never read: `manifest.txt`, appended to after every successful
placement, written for the uninstaller.

| Situation | What the installer does |
|---|---|
| nothing is there | places it, then records it |
| it is there **and** recorded | backs it up and replaces it, silently — a re-install must not become a wall |
| it is there and **not** recorded | names it, says what occupies it and what GreyMatter loses, changes nothing |

A refusal is a reported outcome, not a crash: everything else installs, and the
closing screen counts what was left alone — a message printed three screens up
has scrolled away, the same defect an earlier audit (C bis A4) named for the PATH
warning. The next step is the one the refusal prints,
`mv <path> <path>.before-greymatter` followed by a re-run, and
`tests/e2e_occupied_surfaces.sh` runs that gesture rather than describing it.

Not a crash, and not a clean install either. A surface left alone can cost
something the verification checks: an agents folder that belongs to someone
else means Claude Code cannot reach GreyMatter's agents, the selftest says so,
and the installer then exits 1 like any install whose verification is red. The
closing screen says "works" only when the verification agrees.

</details>

## Behaviour, command by command

| Command | In one line |
|---|---|
| `install.sh` | builds `versions/<id>/` from the clone, points `engine` at it, exits with the selftest's verdict |
| `install.sh --dev` | points `engine` at the clone itself; automatic updates off |
| `brain update` | builds the new version from the mirror, tests it **before** switching, switches only on green |
| `brain update --rollback` | points `engine` back at the previous version — no git, no network |
| `uninstall.sh` | removes what the installer made; `--purge-engine` also removes the versions and the mirror |
| `brain doctor` | checks every engine file against its manifest; reports, never repairs |
| `selftest.sh` | takes an optional engine path, so a version is tested before anything points at it |

<details>
<summary><b><code>install.sh</code> (normal), step by step</b></summary>

1. Read the version identity from the source it is run from:
   `git describe --tags --always` — `v1.29.0` when detached on a tag,
   `v1.28.1-24-g6f28312` for a plain clone of `main`. Both are valid names.
   **Uncommitted edits in the source never change the name** (no `-dirty`
   suffix since 2026-09-20): the engine is `git archive HEAD`, so those edits
   are not in it anyway. Two names for one content made every re-install from a
   working clone rebuild 11.6 MB it already had. The installer now says out
   loud, once, that the uncommitted work is not in the engine.
   **The documented `git clone && ./install.sh` keeps working unchanged**, and
   produces an updatable install. That is the whole point of the change.
2. Build `versions/<id>/` with `git archive <HEAD> | tar -x`. 162 files,
   11.6 MB measured. The source is read, never written.
3. Write `versions/<id>/.greymatter-manifest`: sha256 of every file. This is
   the immutability oracle, and it replaces the git-based dirt check, since a
   version has no `.git`.
4. Mirror the source into `source.git`, so updates have an origin that does not
   live in anybody's working repository.
5. Build the menu bar pill into `runtime/capsule-native-<hash>/` and link it as
   `versions/<id>/capsule/macos/.build`. The version stays immutable: the build
   happens outside it, and only the binary (under 1 MB) is kept. The key is the
   hash of the Swift sources, so two versions with the same capsule code share
   one binary. It needs Swift from Apple's Command Line Tools; without it the
   installer skips only the pill and names `xcode-select --install`
   (`build_capsule` in `greymatter/engine-lib.sh`, held by
   `tests/capsule_runtime.py`).
6. Write `state/engine-managed`, remove `state/engine-dev`.
7. Point `engine` at `versions/<id>`, then do everything the installer already
   does: trunk, mounts, CLI, hooks, launchd, planet, shortcut, verification —
   leaving alone every shared surface it cannot prove it placed.
8. Exit with the verification's verdict: `1` when the selftest is red, `0`
   otherwise — a PATH still to fix is a working install. Until v2.0.3 the
   installer exited 0 on a red selftest (`tests/install_exit_code.sh`).

Idempotent: re-running with the same source rebuilds nothing if
`.greymatter-manifest` already matches.

The installer also seeds `config/ranking.json` in an existing trunk when that
file is absent. It leaves a user's existing weights in place, so updating the
engine cannot silently replace their recall configuration.

</details>

<details>
<summary><b><code>install.sh --dev</code></b></summary>

The only mode in which an engine may be a working checkout, and it must be
asked for by name.

- `engine` → the checkout itself, exactly as today.
- Writes `state/engine-dev` (the checkout path); removes `state/engine-managed`.
- Creates no `versions/` entry and no mirror.
- Prints, so nobody discovers it later:
  `development engine — automatic updates are OFF for this install`.

</details>

<details>
<summary><b><code>brain update</code></b></summary>

The gate is now structural. It does not reason about branches, tags or dirt to
decide *whose* repo this is; it reads provenance.

1. `state/engine-dev` present →
   ```
   Development engine detected.
   Automatic engine updates are disabled for --dev installations.
   ```
   No checkout, no reset, no fetch. Exit 0 under `--auto` (this is a
   configuration, not a failure); exit 1 by hand.
   Since v2.1.1 `--auto` also exits 0 before this step unless
   `state/auto-update-on` exists: silent installing is an opt-in
   (`brain update --auto-on`), and by default session start only looks
   (`--check`) and the agent asks the user.
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

</details>

<details>
<summary><b><code>brain update --rollback</code></b></summary>

Repoint `engine` at `versions/<previous-version>`, replay `install.sh`,
selftest. No git, no checkout, no network. If that directory no longer exists,
refuse and say which versions are retained — a rollback that silently lands
somewhere else is worse than one that refuses.

Retention: the active version, the previous one, and one spare. Older ones are
pruned at the end of a successful update.

</details>

<details>
<summary><b><code>uninstall.sh</code></b></summary>

`--purge-engine` can finally do what its name says: remove `versions/`,
`source.git` and `runtime/`, because the installer created all three. The
user's source clone stays on disk, untouched — it was never ours to delete.
Without the flag, nothing changes.

**It resolves `~/.greymatter` exactly the way the installer does**
(2026-08-26). The two scripts decide ownership by comparing PATHS — is this
shortcut the one we made, is this engine the one we built — and a comparison is
only as good as the spelling on both sides. The installer canonicalises with
`pwd -P`; uninstall did not, so wherever `$HOME` goes through a symlink (every
`mktemp -d` on macOS, and the CI runner) it read the Finder shortcut it had just
created, saw `/private/var/…` where it expected `/var/…`, concluded the link was
somebody else's and left it on the machine. Same trap as the ownership record
install.sh already warns about, one file further on.

**The Desktop app is removed by bundle id, not by name** (2026-09-27). It
became `GreyMatter.app`, a name plain enough for another app to carry, so both
scripts read `org.greymatter.planet` in its `Info.plist` before their
`rm -rf`; anything else under that name stays, with a warning
(`tests/desktop_launcher.sh`).

**An uninstaller from before the rename hands over.** A clone at v2.0.x has its
own `uninstall.sh`, which sources `cbrain/launchd-lib.sh` from the engine and knows <!-- pre-rename -->
only the old names. The engine ships a stub at that path which `exec`s the
engine's own `uninstall.sh --yes`; on a blank Mac, without it, the old script
reported success and left both jobs, the shortcut and the Desktop app.

</details>

<details>
<summary><b><code>brain doctor</code></b></summary>

- It used to run `git -C engine status` to detect a dirty engine. A versioned
  engine has no `.git`, so doctor now checks every file against
  `.greymatter-manifest` with `shasum -a 256 -c` (`hooks/brain_doctor.py`, the
  `.greymatter-manifest` branch).
- Any difference is reported as an **anomaly, never repaired**. An immutable
  version that changed is a fact the user needs to see, not a mess to tidy away
  behind their back.
- In `--dev` mode the git-based check is kept, and doctor says which mode the
  install is in and which version is active.

</details>

<details>
<summary><b><code>selftest.sh</code></b></summary>

Gains an optional engine path. Called with none, it behaves exactly as today.

**And `install.sh` now always names it** (2026-08-26). With no argument the
selftest resolves the CLI through the trunk, then through PATH — neither of
which belongs to the version being installed. A fresh machine has no `brain` on
PATH at that moment, so the installer's own verification went red on a healthy
tree; a machine that already had GreyMatter gave it the OTHER installation's
engine to test. The rule the header states — when an engine is named, its own
`brain` is the only one allowed — is exactly what an installer is in a position
to guarantee, so it does. `brain update` already named the candidate it was
about to switch to.

</details>

## Migration of existing installs

```
v1.28.1 install            its OLD updater                 the NEW install.sh
engine → your clone   ──▶  git checkout v1.29.0       ──▶  builds versions/v1.29.0/,
                           inside your clone (last time)    points engine at it;
                                                            the clone becomes a source
```

The conversion heals itself: there is no migration script for the user to run.
It costs one thing, once — uncommitted work in the clone — and that cost has
its own document, [UPGRADING.md](UPGRADING.md).

<details>
<summary><b>The five steps, measured</b></summary>

Measured, not assumed — replayed in a sandbox with a laboratory origin, the
real `install.sh` and the real `brain update`.

1. Today's installed users run **v1.28.1 or older, which contain no gate at
   all** (verified: neither `engine-managed` nor `gate_ownership` appears in
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
`detached v1.29.0` → marker written.

Developers convert by running `./install.sh --dev` once.

</details>

<details>
<summary><b>The installer says so when it happens</b></summary>

A conversion changes what somebody's checkout IS, inside an automatic update
they did not watch, so the notice goes into the update log at the moment it
applies rather than waiting to be looked up: what the checkout was, what the
engine is now, and that `brain update` will not touch the checkout again. It
fires only on a conversion — an ordinary re-install is silent, because a notice
printed every time stops being read.

</details>

<details>
<summary><b>The one honest cost</b></summary>

The old updater has no gate, so for a user with uncommitted work in their
clone, step 2 runs `git checkout -- .` one final time and discards it. We cannot
fix that from here — it is the code already installed. The release note must
say, plainly: *commit or stash anything in your greymatter clone before
updating to v1.29.0.* [UPGRADING.md](UPGRADING.md) is that note.

</details>

<details>
<summary><b>The v2.1.0 rename, replayed the same way</b></summary>

An updater from v2.0.x builds the v2.1.0 candidate with its **own** code: it
writes the manifest under the old file name, runs migrations from the old
folder only, then replays the new `install.sh`. Each of those is met on the new
side: `verify_manifest` reads either manifest name, the old migrations folder
keeps forwarding stubs, and `install.sh` runs migration 002 before it resolves
a single path. Details in [the migrations README](../greymatter/migrations/README.md).

</details>

## Two consequences we are choosing, not hiding

| Consequence | What happens | Status |
|---|---|---|
| Agent briefs edited in place | the edit lands in an immutable version: doctor flags it, a switch drops it | named here, not fixed here |
| Disk | 11.6 MB per retained version, three retained ≈ 35 MB | accepted |

<details>
<summary><b>Both, in full</b></summary>

**Agent briefs.** `agents/` is mounted into the trunk from the engine
(`greymatter/engine-paths.txt`), and the gardening agents edit `agents/*.md`
through those links — the incident reported by a tester on 2026-08-16. Under an
immutable engine those edits land in a version that is not supposed to change:
doctor will flag them, and a version switch will drop them. That is the correct
behaviour for "immutable", and it is a real change from before. Named here, not
fixed here.

**Disk.** 11.6 MB per retained version, plus the pill's binary (under 1 MB,
shared by the versions whose capsule code is identical), plus the mirror. Three
versions retained ≈ 35 MB of engine.

</details>

## What this buys

| Promise | Why it now holds |
|---|---|
| **P1** — the updater never writes where the user created something | it has no code path that does: nothing left to detect, nothing left to get wrong |
| **P2** — the installer owns what it made, and only that | the marker records a provenance instead of passing a verdict on a git state |
| **P3** — the trunk is never touched by an update | unchanged, and now trivially auditable: no git command in the update path names the trunk |
| Rollback | repointing a symlink at a directory already tested beats checking out and hoping |
| GMatter, the app | an app that ships as a bundle has no clone to adopt; a versioned engine beside a durable trunk is the model it needs, built early |
