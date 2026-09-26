# Design doc — C Brain (an installable, self-updating knowledge trunk)

**TL;DR** — Extract, from a living `~/claude-brain`, a package called **C Brain**
that installs in one command on another macOS machine, behaves **identically** to
the original with everything around it (hooks, agents, capsule, planet,
companion, status line, CLI, launchd), and **updates itself** on each user's
machine.

**Why this doc is sized the way it is**: publishing is irreversible (revoking
access does not un-clone what is already cloned), the source of the package is a
system holding **real personal data about third parties**, and automatic updates
add a second serious risk: **code that installs itself on somebody else's
machine**.

---

## Who it is for, and why

**Audience**: users of a command-line agent — Claude Code first, but any model
running in a CLI — who want **more memory, more context, and a knowledge tree
that grows with time and with the volume of work** accumulated alongside their
agent.

This is not one more tool: it is what stops a session starting from zero, and
keeps what was understood once findable from any other project.

**Installation**: the user does not follow a procedure. They give **one command
to the agent already running in their CLI**, and the agent installs it. That is
the shortest possible manual, and it matches how this audience already works.

**An honest constraint, not to be dressed up**: the trunk, the agents, the CLI,
the planet and the capsule are portable everywhere. The **automatic wiring**
(`SessionStart` / `SessionEnd` / `PostToolUse` hooks, the status line) goes
through `~/.claude/settings.json` and exists only in Claude Code. On another CLI,
C Brain works **on demand** (`brain recall`, `brain status`, agents invoked
explicitly) but **not as a closed loop**. The installer detects this and says so;
it never lets anyone believe in an autonomy that is not there.

## Problem (the need, not the solution)

The trunk worked on **one** machine only, and its installation was not an
artefact: it was a sequence of manual gestures reconstructed from memory.

- A machine migration proved it: the `~/.claude/agents` symlink was never
  recreated → **the agents were invisible and the autonomous loop spun on nothing
  for 24 hours**, with no visible error at all.
- The resume `.plist` carried a hardcoded home path → the scheduler died silently.
- Nobody else could run the system, so it was neither showable nor transmissible.
- And once installed somewhere, **it freezes**: fixes made here never reach it. A
  frozen system on somebody else's machine is worse than none — it carries the
  bugs that have already been repaired.

The need: **that another person gets the same system running, that it can be
proven, and that it stays current without them doing anything.**

## Measurable success

In an isolated `HOME` first, then on a third-party machine:

| Criterion | Threshold |
|---|---|
| Installation | `git clone && ./install.sh` — **zero manual steps** beyond an admin password, under 10 minutes |
| Health | `brain selftest` **green**, `brain doctor` without error |
| Hooks live | a test session triggers recall + archiving (proven by `state/`, not by the docs) |
| Agents resolved | the 4 ship briefs listed by the CLI, covering 8 missions (the symlink trap is detected by the installer) |
| Capsule | an Electron window animating on a change to `state/status.json` |
| Planet | double-clicking the `.command` → a globe served on `localhost:8765` |
| Status line | visible in the CLI, same rendering as on the source machine |
| Idempotence | a second `install.sh` run does zero damage, `settings.json` untouched |
| **Updates** | a fix published here reaches the user **at their next session start**, without intervention, **without touching a single one of their notes** |
| **User rollback** | `brain update --rollback` restores the previous version in one command |
| Leaks | `leakcheck`: **zero marker** of personal data or secrets in the published repo and its history |

The local port branch has a clean working tree scan but old commits with names
now covered by new fingerprints. It must not be published as-is; the owner will
decide how to handle its history.

## Non-goals (explicit boundaries)

- **No note content whatsoever.** The package ships an **empty** trunk. Nobody clones somebody else's brain.
- **No skills** (`~/.claude/skills`) — too personal. Measured: **20 out of 20** contained personal markers (client, people, personal context). None was transferable. What ships instead: an **empty** `skills/` plus `skills/README.md`, the documentation of the **house standard** (nine requirements, forge-on-block, the skill/agent boundary, a template). We pass on the method that makes the skill, not the skill.
- **No `desktop_sync.py`** and no matching plist: it backs up the author's Desktop to *their* GitHub — strictly personal, and destructive on somebody else's machine (`--delete` on an unknown destination).
- **macOS only** (launchd, Electron, `open`). No Linux or Windows.
- **No telemetry.** An update is a `git pull`; it reports **nothing** back.
- **No forced migration of the source machine** to the new layout (see "Impact").
- **Neither the cold corpus nor the embeddings venv**: optional, BM25 is enough by default.

## Recall: one corpus, and weights you can read

Two decisions worth stating, because both were once invisible.

**The indexable corpus is defined once**, in `hooks/brain_corpus.py`. It used to be written
twice — once per recall engine — under a comment claiming the two were identical. Measured
on a real trunk, they had drifted by 5 documents. `tests/shared_corpus.py` now rejects any
engine that writes itself a local copy; the check is static, because comparing two lists
imported from the same module would be tautological and could never fail.

**The ranking weights live in `config/ranking.json`**, not in the engine. Each weight ships
with the measurement that justifies it, and `brain_recall.py --explain` decomposes any
result into the components that actually exist — the BM25 contribution per term, and the
utility annotation. Since ADR-0018, usage no longer multiplies the ranking score;
configured `alpha` is zero. It publishes no invented component: a number
nobody computes would be worse than no explanation, because it would be trusted.

The file is optional. Absent, unreadable or truncated, recall falls back on defaults that
are exactly the previously hardcoded values — a configuration must never be able to break
recall. It is part of the index fingerprint, so changing a weight rebuilds the index instead
of silently serving one scored under the old rules.

One knob ships OFF: `index.family_bridge_weight`, the vocabulary bridge between notes of the
same thematic family. At weight 1, on a 15-case golden set over a real trunk, it demoted the
note that literally answers the query from 1st to 2nd place and promoted an off-topic one.
The setting remains off, and this package has no thematic-family registry to read.
Turning it up would require a registry and a fresh measurement.

## One owner per vocabulary

Three times in three days this repository shipped the same shape of bug: a contract stated
in two places instead of shared from one. Two recall engines silently indexed different
corpora. The map read a field its exporter never wrote. A list of note types lived in a hook
and in five agent briefs at once.

So each vocabulary now has exactly one owner, and everyone else imports it:

| Vocabulary | Owner |
|---|---|
| the indexable corpus | `hooks/brain_corpus.py` |
| `metadata.type` | `hooks/on_fiche_write.py` (see below) |
| typed `relations:` | `hooks/graph_export.py` |
| ranking weights | `config/ranking.json` |

`brain_doctor` reports disagreements between these sources. It deliberately owns none of
them — a diagnostic tool that defines a vocabulary becomes a third thing to disagree with,
and then nobody can say which one is right. The cost of importing rather than restating is
that an import can fail, so the doctor announces a check it could not run instead of
reporting a clean trunk. `tests/doctor_contract.py` makes falling back on a local copy a
test failure.

### What `metadata.type` means — and what it is not

Five values: `user`, `feedback`, `project`, `reference`, `lesson`. They classify a note by
**what kind of knowledge it is**, and the writing agents are told this list in
`agents/*.md`; `tests/type_vocabulary.py` holds the two sides equal, because a vocabulary
written down twice is one that will disagree with itself.

**It is not the folder.** The two dimensions look alike — there is a `lessons/` folder and
a `lesson` type — and collapsing them would be a one-way mistake. Measured on a 400-note
trunk, `lessons/` holds `feedback` 121 · `lesson` 67 · `reference` 54 · `project` 1: most
of what lives there is not a lesson. Filing says *where you will look for it*; the type
says *what it is*.

`feedback` and `lesson` are the pair worth stating, since they share that folder: the
difference is the **origin** — what the user told you, against what was learned by
measuring something. `lesson` was adopted on that evidence on 2026-08-17, and explicitly
not on the grounds that a lot of notes live in `lessons/`.

The vocabulary stays **closed**: an unrecognised value is still recorded and still
reported. Widening it by one word did not turn it into "anything goes".

## Approach

### 1. The structural decision: separate the ENGINE from the TRUNK

This is what makes automatic updates possible **with no risk to the data**.

A single `~/claude-brain` mixes code (hooks, agents, capsule, planet) and content
(notes). A `git pull` on a repo where the user also commits their own notes ends
in conflict — or in loss.

```
~/.c-brain/versions/   ← the installed versions. Immutable exports, code ONLY.
~/.c-brain/engine/     ← a link to the ACTIVE version. Updating switches this link.
~/.c-brain/trunk/        ← the user's trunk. Their notes, their own git. NEVER touched.
    hooks/  → symlink to ~/.c-brain/engine/hooks
    agents/ → symlink to ~/.c-brain/engine/agents
    capsule/ planet/ companion/ → symlinks
    lessons/ projects/ meta/ life/ sessions/ state/ → REAL, the user's own
```

The paths become `~/.c-brain/trunk/hooks/...`: **no hook, no agent and no path
changes shape**. Behaviour is identical; only where the files come from changes.

### 2. Automatic updates

- `brain update`: `git pull` inside `~/.c-brain/engine`, then **replays `install.sh`** (idempotent by construction — it already knows not to overwrite anything). The symlinks make propagation immediate.
- **Automatic trigger (v1.28.0)**: a `SessionStart` hook launches the update **detached** and returns immediately, on **every** session. It does not merely report any more — it **installs**. The report of the run is shown at the *next* session start, which is the price of never blocking: better news one session late than a session waiting on a `git fetch` and a selftest.
  - Until v1.28.0 the same hook only *announced*, throttled to once every 24 h. That throttle existed because a notice repeated too often stops being read; it made no sense once the thing applies itself. **Nobody typed `brain update`** — the published engine sat weeks behind the author's, and a fix nobody installs fixes nothing.
  - A lock directory (`state/auto-update.lock`, `mkdir` being the shell's atomic test-and-set) keeps several sessions starting at once from updating in parallel; it is reclaimed after 30 minutes so a sleeping machine cannot wedge updates forever.
- **The selftest decides, and rolls back by itself.** In automatic mode nobody reads the screen, so *advising* a rollback would leave the tool broken until the user noticed — with no way to connect it to an update they never asked for. A red selftest restores the previous tag immediately, and the next session says so.
- **It can be turned off**: `brain update --auto-off` (or `CBRAIN_NO_AUTO_UPDATE=1`) restores the pre-v1.28.0 behaviour — report, do not apply. The way out is written before the way in.
- **Tagged versions, never `main`**: users follow `vX.Y.Z` tags, not the working branch. A draft commit reaches nobody.
- **Migrations**: a numbered `migrations/` folder, each script idempotent and **never destructive** to `lessons|projects|meta|life|sessions`. The log lives in `~/.c-brain/state`.
- **Rollback by hand**: `brain update --rollback` checks out the previous tag and re-runs `install.sh`.
- **The engine has to come back clean after the installer.** `install.sh` runs `npm install` in the capsule, and npm rewrote `capsule/package-lock.json` — which left the engine with an uncommitted change, and `update.sh` *refuses* a dirty engine rather than overwrite somebody's work. So `brain update` worked once and never again, on a machine where nobody suspected having touched anything. Root cause fixed (the lock declared a dependency `package.json` no longer had); `update.sh` also restores tracked files after the installer, which is safe precisely because the pre-check demanded a clean tree first.
- **And the same trap had a second mouth, found on somebody else's machine (2026-08-16).** The engine directories are mounted *inside* the trunk as symlinks, so the gardening agents walk into them and edit agent briefs — correct work, wrong repository. Each pass dirtied the engine, `update.sh` refused, and the install fell behind for ever without a signal. Two halves to the fix, because repairing the cause rescues nobody already stuck: the writing agents are now told the engine is off limits (`cbrain/engine-paths.txt` is the one list, read by the installer, the updater and the doctor), and `update.sh` **tolerates dirt confined to those paths** — it discarded them after updating anyway, so the refusal only ever cost people their updates. Anything outside still blocks, and is now named in the error.
- **`brain doctor` looks at the engine too.** It used to read only the trunk, so it came back fully green while the engine was dirty and updates were refusing to run — the diagnostic a user is asked to paste was blind to precisely this. It now reports the engine's own worktree, and prints the one-line repair.
- **A link inside an agent brief is a link in the trunk.** The briefs are mounted in the trunk, so `brain doctor` checks every `[[…]]` they hold. v2.0.0 turned eight agents into four ships but left ten mentions of the old jobs wrapped as links: a fresh install reported four dead links and `brain doctor` exited 1, which the CI install job caught only after the tag was out. In v2.0.1 the jobs are named as plain words, as on the French branch; a brief links only to a ship or a note that exists.

### 3. Generalization is declarative, not manual

`sync.sh` re-copies the engine from the living trunk on every pass: **a fix made
by hand would be overwritten**, and the leak would be back at the next commit
with nothing to flag it. Hence `rules.json` + `generalize.py`, **chained
automatically after every copy**, with a guard: a rule finding fewer occurrences
than expected makes the script **fail** — a falling counter means the source
changed its wording, not that the problem went away.

### What the engine/trunk split broke (found by running, not by reading)

The same trap twice: code deriving its paths from `__file__` instead of `$HOME`.
Under a symlink it then points into the **engine** instead of the **trunk**.

- `tests/invariants_brain.py` was writing `state/coherence.json` **into the installed repo** → three tests in error. Fixed by a rule: two distinct roots, `CODE` (follows the file) and `BRAIN` (derives from `$HOME`). The 22 other uses of `__file__` locate neighbouring **code** — those are correct and stay.
- `capsule/main.js` watched `status.json` through `__dirname` while `index.html` derived it from `homedir()`. The capsule would have animated but **never re-shown itself** when an agent woke up. Two halves of the same component disagreeing.
- `planet/graph.json` is regenerated **inside the engine**. Tolerated: it is gitignored and rebuilt on every launch. Never to be extended to user data.

### Two silent failures the installer work caught

- **A status line installed and invisible**: the file was copied into `~/.claude` but the `statusLine` key was never written into `settings.json`. Nothing would have flagged it — just a missing line. Fixed, and set **only** when the user has none of their own.
- **`brain update` announced but non-existent**: the installation summary listed it before the command existed. Removed from the message rather than promised empty.

### Rejected alternatives

| Alternative | Why not |
|---|---|
| **One repo for code and content, `git pull` on it** | The user commits their notes into the same repo → guaranteed conflict on the first update, lost notes at worst. That is the heart of the problem, not a detail. |
| **Reusing the previous extraction repo** | Its history had carried personal content; `git log -p` brings it back even after cleaning. → a new repo, and the old one deleted once C Brain was verified. |
| **Publishing the trunk itself behind a `.gitignore`** | A denylist lets things through by default. One forgotten file is a personal-data leak. An allowlist refuses by default. |
| **Copying files instead of symlinking** | Every update would have to re-copy and guess what the user changed locally. The symlink makes the code/content boundary **physical**, which is non-negotiable. |
| **Silent updates from `main`** | Unreviewed code would install on somebody else's machine. Tags force an explicit decision to publish. |
| **A Python or Makefile installer** | The entry point must run on a fresh Mac **before** anything is installed; `bash` is guaranteed, a Python venv is not. |
| **Copying by hand on every update** | Guaranteed drift between the living trunk and the package, with no signal. Hence `sync.sh --check`, which fails when the package has fallen behind. |

## Contract (what everything else rests on)

```
c-brain/
  install.sh          # the single entry point, idempotent, backs up before overwriting
  uninstall.sh        # back to the previous state, in one command
  publish.sh          # the only sanctioned path to a git push
  sync.sh             # living trunk → repo, allowlist; --check = drift report only
  generalize.py       # applies rules.json AFTER the copy (chained by sync.sh)
  rules.json          # declarative rules: code blocks + text substitutions
  leakcheck.py        # zero marker, otherwise exit 1 (blocks the commit)
  brain               # CLI, 18 subcommands (status|doctor|audit|review|recall|next|
                      #   coherence|utility|credit|embed|push|metrics|selftest|backup|
                      #   update|demo|capsule|version)
  hooks/              # the hooks + .plist.template  (desktop-sync EXCLUDED)
  agents/             # 4 ship briefs, 8 missions (no client or project names)
  capsule/            # Electron, without node_modules, without dead assets
  planet/             # index.html, launch.sh, media/  (graph.json EXCLUDED)
  companion/          # live change tracking
  statusline.py       # the CLI status line
  cbrain/             # update.sh, check_update.py, migrations/ — C Brain specific
  skeleton/           # the EMPTY trunk created on the user's machine
  skills/             # EMPTY + README.md = the house standard (no skill shipped)
  demo/               # a throwaway trunk `brain demo` places and removes (open question 3)
  tests/              # the checks that hold this contract, runnable by anyone
  docs/               # this design doc, the install guide, the verification recipe,
                      #   plus _coverage.json — which code each doc claims to describe
```

**Contract invariants** (checked by `selftest`, not by re-reading):

- no absolute `/Users/<somebody>` path in an executed file — everything derives from `$HOME`;
- `state/`, `planet/graph.json`, `capsule/node_modules/`, `corpus/`, `.venv/` are never committed;
- `install.sh` run twice yields the same state;
- **no engine script writes into `lessons|projects|meta|life`** — except the agents, the only legitimate write path, and they go through the user's trunk.
- **the local history exists before anything relies on it.** `install.sh` starts a git
  repository in the trunk, and says which way it went. Until 2026-08-17 it did not: a
  default trunk was unversioned, so the per-session save opened with "is this a repo?" and
  returned 0 — its own comment called that *"the normal case: nobody ran `git init`"*. The
  protection shipped, and was inert for everyone. **A protection that is silently inactive
  is worse than an absent one**: nothing is lost, and someone can believe for weeks that
  their history is being kept. Either it works, or the user is told it does not.
  ⚠️ **A local history is not a backup.** One disk, no remote, and the package pushes
  nowhere — a remote is opt-in. The vocabulary is load-bearing: `brain backup` records a
  "manual save", because the other word promises off-machine safety this never provided.
  ⚠️ **Trunk git is not engine git.** The ownership gate that protects `brain update`
  reasons about the ENGINE repository. Nothing about updating may look at the notes.
- **the automatic save commits ONE ZONE PER COMMIT** (`hooks/commit_par_zone.py`). It used to be a single `git add -A`: one such commit swallowed nineteen files of an unfinished piece of work, and 612 commits of that shape are in the history. A mixed commit cannot be read back, so the trunk's pre-commit hook refuses them and the automatic save leans on that refusal instead of working around it.
- **the maintenance loop asks before it spends** (`hooks/quota_probe.py`, surfaced as `brain credit`). An agent pass that starts with no credit left does not fail loudly — it half-runs and marks work as done. The probe is what makes the degraded mode a decision rather than an accident.
- **prose is held to the same standard as code** (`tests/docs_aligned.py`). Not by reading it — a check that needs a model to decide is not a check — but by asking whether the code a document claims to describe has moved since that document was last edited. `publish.sh` reports it; it does not yet refuse.

## Impact & risks

- **Risk #1 — leaking third parties' personal data.** `planet/graph.json` holds the **full text of the notes**, real names included, and is regenerated on every launch. Excluded by the allowlist *and* by `.gitignore` *and* caught by leakcheck. Three nets.
- **Risk #2 — auto-update is a code-execution channel into somebody else's machine.** Live since v1.28.0, and it is the heaviest trade-off in the package. Mitigations: tags only, never `main`; migrations non-destructive by construction; a red selftest rolls the version back automatically; rollback in one command by hand; `--auto-off` restores report-only; the hook never blocks a session, and never takes one down when it fails. What is *not* mitigated, and is written in `SECURITY.md` rather than glossed over: **the tags are not signed**, so this trusts whoever can write to the repo. Signing is a decision deferred until there are installs to protect (see `SECURITY.md`).
- **Risk #3 — the engine still named its author and their clients.** Measured after the first pass: **50 occurrences across 16 files**, and not confined to the agents. That was the real content of the generalization work.
- **The source machine stays the source of truth** and does **not** migrate to the engine/trunk layout for now: it runs in production with ten active hooks, and it is not refactored just to ship. `sync.sh` pushes its state into C Brain. A migration can follow once C Brain is proven elsewhere.
- **Confirmed dead weight**: `capsule/assets/` (7.4 MB) is **entirely dead** — the creature sprite is inline in `index.html` (the `BODY` grid), and no file under `assets/` is referenced by the code. Excluded by the allowlist.
- **Tooling trap**: macOS 27 ships **openrsync**, not GNU rsync. On a *single* file, `--dry-run --itemize-changes` always reports a transfer → a permanent false drift. `sync.sh` compares standalone files with `cmp`, never with rsync.
- **macOS TCC**: anything going through launchd and reading `~/Desktop` is refused without Full Disk Access — a GUI action that cannot be scripted, so it belongs in the install procedure.
- **Cost**: none. No server; an update is a `git pull`.

## Reversibility / kill switch

- **Before the first push**: everything is local, `rm -rf` is enough.
- **After publishing**: making the repo private again **does not un-clone** what is already out → the real kill switch is the leak check **before** the push, not after.
- **A bad update**: `brain update --rollback` (previous tag + reinstall). Removing the tag on GitHub also stops propagation to users who have not pulled yet.
- **On the user's machine**: `uninstall.sh` plus a timestamped `settings.json` backup → back to the previous state in one command. Their trunk is never deleted.
- **On the source machine**: no risk — the pipeline is read-only on the living trunk.

## Delivery (mergeable lots, each testable alone)

| Lot | Content | Done when |
|---|---|---|
| **L0** ✅ | `sync.sh` (allowlist) + `leakcheck.py` + `.gitignore` + `skills/` | tools shipped and **executed**: `sync --check` proven on three simultaneous divergences, leakcheck red at 50 (it sees) |
| **L1** ✅ | `generalize.py` + `rules.json` + `skeleton/` | **leakcheck green** (50 → 0); `selftest` + `doctor` + `recall` + `graph_export` green in an isolated HOME |
| **L2** ✅ | `install.sh` + `uninstall.sh` + `merge_settings.py` + `INSTALL.md` | full cycle proven in an isolated HOME: second pass = zero change; `settings.json` returns **semantically identical** after uninstall — every key of
yours back, none of ours left. Not byte-identical: uninstall rewrites the file through
Python's JSON serializer, so hand-formatting comes back reformatted (corrected v1.13.0); the user's note intact |
| **L3** ✅ | Capsule + status line | screenshots: `DISTILLING` then `IDLE` on a `status.json` change; three components aligned on the same path |
| **L4** ✅ | Planet + Desktop `.command` | `launch.sh` → `200` on index/graph/glb; headless capture of the globe and its legend |
| **L5** ✅ | Companion | pre/post hooks replayed: `+3 −1` aggregated, status line at **two lines** |
| **L6** ✅ | `brain update` + `check_update.py` + `migrations/` + `VERSION` | a fake remote with two tags: update, migration run exactly once, rollback, note intact at every step |
| **L7** ✅ | README + verification recipe + `publish.sh` + the repo online | clone from GitHub → `install.sh` → selftest and doctor **green** |
| **L8** ✅ | English translation, `main` / `fr` split | every **user-visible** string in English, held by `tests/english_only.py` in CI; **hook comments are still French** and say so in the README; `fr` keeps the original and stays the sync branch |

Critical path: **L0 → L1 → L2 → L6**. L3/L4/L5 parallelize after L2.

## Open questions

1. **Tag signing**: GPG or a plain annotated tag? The first proves an update really comes from the author; the second is simpler. **Still open.**

2. ~~**`sync.sh` cadence**: by hand, or a hook that warns when the package has fallen more than N days behind the living trunk?~~ — **Settled 2026-08-15, and neither answer was right.** A warning was the wrong shape: the drift detector had been reporting "up to date" for twelve days while the package served a two-week-old planet, because one exclusion was written by filename and silently hid the file it was meant to keep. A sensor nobody can trust is worse than no sensor. What actually shipped is *propagation*, not warning: at session end the author's machine copies, leak-checks, commits and pushes the `fr` branch on its own. The obstacle had never been risk — it was that `sync.sh` refuses to run anywhere but `fr`, the working copy sits on `main`, and switching branches under someone who is editing is worse than doing nothing. A second working copy pinned to `fr` (`git worktree`) satisfies the guard instead of bypassing it.
   **What stays a human gesture, and why**: translating `fr` → `main`, and stamping a version. Both are judgement. The tool that pushes is deliberately *not* in this package — a user who added a remote to their trunk never asked for their private notes to be pushed at the end of every session.

3. ~~**Is the empty trunk really empty?**~~ — **Settled.** `demo/` ships a throwaway trunk that `brain demo` places and `brain demo --remove` takes away, so a newcomer can see the format without anyone's real notes leaking into the package. The trunk a user gets is still empty.

4. **Should `publish.sh` refuse on unreviewed docs, or only warn?** It warns today, because four documents were behind the day the check landed and a gate nobody can satisfy only teaches people to skip the script. The honest answer is "refuse, once the backlog is zero" — but nothing currently forces that day to arrive.

---

*First drafted 2026-07-26. Kept in sync with reality as the implementation
proceeded — a design doc that stops matching the code is a comment that lies.*
