# GreyMatter

[![CI](https://github.com/Yuno15-bb/GreyMatter-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Yuno15-bb/GreyMatter-engine/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Yuno15-bb/GreyMatter-engine?sort=semver&color=6b8afd)](https://github.com/Yuno15-bb/GreyMatter-engine/releases/latest)
[![Licence](https://img.shields.io/github/license/Yuno15-bb/GreyMatter-engine?color=8a8f98)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-8a8f98)](#compatibility)

**GreyMatter turns each session with your CLI agent into memory it can reuse —
distilled into a note, filed, linked, and handed back automatically the next
time it matters. From any project, and without leaving your machine.**

<table width="100%">
<tr>
<td width="74%" align="center">
  <img src="docs/media/planet.webp" alt="The knowledge map, turning: hundreds of notes arranged by resemblance in phosphor orange on black. The cursor lands on a note and a panel gives its region, title and summary; then the structure button is clicked and the map reorganises into the filing; then a family is clicked and opens as a sphere of its own" width="100%">
</td>
<td width="26%" align="center">
  <img src="docs/media/capsule.webp" alt="The capsule: a glass orb sitting on the desktop, its material and hue changing as each agent works — idle, gardening, challenging, committing — with the lines being written scrolling inside it and the current task named underneath" width="168">
</td>
</tr>
<tr>
<td align="center"><sub><b>Map</b></sub></td>
<td align="center"><sub><b>Agents</b></sub></td>
</tr>
</table>

Your agent is brilliant within a session and amnesic between two. Solve
something on Monday, explain it again on Thursday. GreyMatter is the part that
remembers.

The more work piles up, the more useful the tree gets — the opposite of a
conversation history, which only gets longer.

---

## What it actually does

**The memory itself** — this is the product, and it is all you need:

| | |
|---|---|
| **A trunk** | your lessons, projects, method — markdown, on your machine, versionable |
| **Automatic recall** | relevant notes are injected into context on every prompt |
| **It learns from use** | what served you climbs — with a slot kept for notes never seen, so it does not go round in circles |
| **It knows its own age** | notes never re-checked enter a review queue, dated from the git history |
| **8 agents** | they distill, file, link, challenge, synthesize, prune, repair, and watch the machine |
| **A closed loop** | session ends → archive → distill → file, without being asked |
| **Updates** | the engine updates itself **every session**; **your notes are never touched** |

**And two ways to look at it**, which are extensions and install separately —
`./install.sh --core-only` leaves both out:

| | |
|---|---|
| **A capsule** | a glass orb on your desktop showing the agents at work, live |
| **A map** | everything you wrote as one navigable 3D map, rebuilt on every launch |

<p align="center">
  <img src="docs/media/architecture.png" alt="How a session becomes memory: the trunk — ~/.c-brain/trunk, holding the notes, MEMORY.md and state — is read and written by three hook stages inside your session. On every prompt, inject_recall uses BM25 lexical search to pick the few notes that match what you asked and pastes them into the prompt. During the session, post_diff, track_read, on_fiche_write and pre_snapshot record what is written and read. At session end, archive_session and auto_maintain archive the session and wake the agents, in two layers: layer 1 always runs the distiller then the gardener, the gardener gated on the distiller actually succeeding; layer 2 wakes at most one of the challenger, architect, archivist or mechanic, and only if its sensor crosses a threshold and twelve hours have passed. Below, three ways to look at it: the capsule reading state/status.json, the planet built from graph_export, and the brain CLI — status, review, selftest, update — every automatic step runnable by hand" width="900">
</p>

### How good is the recall?

Measured, not asserted — `tests/recall_benchmark.py`, on a synthetic corpus
where finding the answer means picking one note out of ~120 that share its
subject and most of its vocabulary:

| notes | P@1 | P@3 | MRR | off-topic in what it injects | per prompt |
|---|---|---|---|---|---|
| 100 | 0.94 | 0.98 | 0.96 | 35% | 5 ms |
| 1000 | 0.79 | 0.93 | 0.86 | 24% | 47 ms |
| 5000 | 0.46 | 0.83 | 0.64 | 39% | — |

It holds to about a thousand notes and degrades sharply past that. Published
here because a memory tool that will not say how well it remembers is asking
for trust it has not earned. The CI enforces these numbers as thresholds.

**This bench does NOT measure everything.** Its corpus is synthetic, so its
vocabulary is coherent by construction: it says nothing about morphology
("ranger" versus "rangement") nor about the French/English mix, which are two
real causes of an unfindable note. Its numbers did not move when those two
points were fixed — that is a limit of the bench, not the absence of an effect.

### And on a real trunk, what does it change?

Measured on 2026-08-12 against the author's living Brain (312 notes), 10
questions about real facts of his work, 50 runs isolated from one another:

| what the assistant has | right answers | tokens per exchange |
|---|---|---|
| nothing | **0/10** | 178 k |
| the trunk + the map, **without** automatic recall | **8/10** | 264 k |
| **the full system** | **10/10** | **168 k** |

Automatic recall does not cost context, it **saves** it: with no suggestion the
assistant has to search, and searching burns turns. The detail of the protocol —
and the three campaigns that had to be thrown away before an honest measurement
came out — lives in the author's trunk, not here.

## Install

**As a Claude Code plugin** — the short way, and the one that updates itself:

```
/plugin marketplace add Yuno15-bb/GreyMatter-engine
/plugin install c-brain@c-brain
```

That gives you the whole memory: the trunk, automatic recall, the eight agents,
the `brain` command, and three commands you can type — `/c-brain:recall`,
`/c-brain:distill`, `/c-brain:doctor`. It creates `~/.c-brain/trunk` on your first session and
tells you so. It does **not** set up the capsule, the planet or the scheduled
jobs — a plugin cannot install a background service, and pretending otherwise
would leave you with a window that never opens.

**The full install** — everything above, plus the capsule, the planet and the
unattended maintenance:

```
Install GreyMatter: clone https://github.com/Yuno15-bb/GreyMatter-engine into ~/dev/c-brain, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

Or by hand: `git clone … && cd c-brain && ./install.sh`

> **Upgrading from v1.28.1 or earlier?** Read
> [docs/UPGRADING.md](docs/UPGRADING.md) first — a one-time warning about
> uncommitted changes in your engine checkout. Your notes are not affected.

**The memory and nothing else** — no Electron window, no 3D globe, no
background job:

```bash
./install.sh --core-only
```

Details, prerequisites and uninstall: **[INSTALL.md](INSTALL.md)**.

## The idea holding it all together

```
~/.c-brain/engine  ← link to the ACTIVE version under versions/. Code, replaceable, disposable.
~/.c-brain/trunk     ← the TRUNK. Your notes. Changes only when YOU write.
```

The two never mix. That is what lets an update land with zero risk to your work —
and lets `uninstall.sh` remove everything while leaving your knowledge intact.

Both live behind a leading dot, out of the way. Your notes should not: the
install puts a **`C Brain` shortcut in your home folder**, tagged, so the one
part that is yours is the one part you can see. That folder, the `~/.c-brain`
paths and the `/c-brain:` commands keep the engine's original name: they are
addresses, and an address that changes breaks every install that already
follows it.

<p align="center">
  <img src="docs/media/where-it-lands.png" alt="A home folder in Finder: the usual Applications, Desktop, Documents, Downloads, Movies, Music and Pictures — plus a red-tagged C Brain folder, with an arrow pointing at it" width="900">
</p>

## What it does not do

- **It makes no request of its own.** No telemetry, no network call beyond
  `git pull`. What travels is what your prompts already carry: the recall hook
  adds the name, description and path of two or three notes to a prompt you
  were sending anyway, and agents you start read whole notes. Both go to your
  model provider, like the rest of your message. [`SECURITY.md`](SECURITY.md)
  spells out where the line is.
- **It updates itself, and you should know that.** Every session start installs
  the latest published version, in the background — so code from the repo runs
  on your machine without you asking. The trunk is never touched, a version
  whose selftest goes red is undone automatically, and
  `brain update --auto-off` restores the old behaviour (report without
  installing).
- **It ships no knowledge.** Your tree starts empty, and the three skills it
  does ship only drive the tool. See [`skills/README.md`](skills/README.md) for
  the reasoning: we pass on the method, not somebody else's lived experience.

## The extensions

Neither of the two below is the product. They are how you *watch* it — pleasant,
optional, and skipped entirely by `./install.sh --core-only`. The plugin install
never sets them up at all, because a plugin cannot install a background service.

### The capsule

A pane of living glass in the corner of your screen. It does not decorate: it
carries three separate channels, and the first two read **without colour**.

| Channel | What it says |
|---|---|
| **Fluid mechanic** | the nature of the work — swell, sweep, vortex, shards |
| **Speed and amplitude** | how intense that step is |
| **Hue** | the family of agent — four, not thirteen |

Inside the sphere, the lines your agents are **actually writing** scroll by, bent
around the curve. When nothing has been written for a while it falls back to the
file the running agent executes — because an agent spends long minutes reading
without writing, and that is exactly when you look at it.

It clears itself off the desktop a minute after the work ends, and comes back on
the first agent. Clicks pass straight through it, except on the sphere itself:
grab it there and drop it wherever you like.

<p align="center">
  <img src="docs/media/capsule.webp" alt="The capsule: a glass orb in the corner of the screen, cycling through every agent state — distilling, gardening, filing, correcting, mapping, architecting, challenging, archiving, synthesizing, auditing, committing, then back to idle" width="190">
</p>
<p align="center"><sub>At its real size, one state per family — then back to rest.</sub></p>

Rest costs about 5 % of one core, work about 9 %. The cost follows the frame
rate, almost not the geometry — so the rate drops at rest and rises only during
transitions, where a dropped frame would read as a stutter.

### The planet

Every note is a dot, every `[[link]]` an arc, rebuilt from your trunk on each
launch — projects become cities, cross-cutting lessons become regions.

What opens is the **meaning map**: every note placed next to what it resembles,
folders ignored. That is where the map earns its place — two notes sitting
against each other here while your filing keeps them apart is a link you have
not written yet.

The **filing** is the second view, not the first: a small globe in the left
column holds it, one cluster per region. Aim a region in it and the same notes
light up in the map. `V` brings the filing back full size when you want to walk
it.

Point at a note: its links light up and the panel gives you the region, the
title and the summary — nothing more, because hovering is how you sweep. Click
it and the panel opens out: the plain-language section, the full note behind it,
and the connections at the end.

Points warm up as you read them and fade on their own; the ⚠ ✦ ↻ ▷ markers flag
what was challenged, held as a conviction, left open, or is replayable in 3D.

<p align="center">
  <img src="docs/media/planet.webp" alt="The knowledge map, turning: hundreds of notes arranged by resemblance in phosphor orange on black. The cursor lands on a note and a panel gives its region, title and summary; then the structure button is clicked and the map reorganises into the filing; then a family is clicked and opens as a sphere of its own" width="100%">
</p>
<p align="center"><sub>A showcase trunk of 375 notes and 1 474 links — the real shape of a working trunk, with generated titles. Yours starts empty.</sub></p>

**[Full planet documentation](docs/planet.md)** — the two views, reading a
point, the markers, and what the map cannot do.

## Commands

Inside your agent, once the plugin is installed:

```
/c-brain:recall <subject>   what the trunk already knows about it
/c-brain:distill            turn what was just worked out into a note
/c-brain:doctor             check the wiring and the trunk
```

And in any shell:

<p align="center">
  <img src="docs/media/recall.png" alt="Terminal: brain demo places three notes, brain recall ranks them by relevance, brain demo --remove takes them away" width="820">
</p>

```bash
brain status          where the trunk stands
brain recall <word>   search your memory
brain doctor          tree health (dead links, inconsistencies)
brain review          full audit of the trunk
brain next            your resume points
brain capsule         open the floating orb  (stop · status)
brain selftest        verify the installation
brain update          update the engine  (--check · --rollback)
                      automatic every session: --auto-off / --auto-on
brain version         installed version
```

## Compatibility

**macOS.** launchd, Electron and `open` are used.

**Claude Code** for the full experience: it is what fires the hooks (recall,
archiving, autonomous maintenance, status line). With another CLI agent, GreyMatter
installs and works **on demand** — trunk, agents, `brain`, planet, capsule — but
without the closed loop. The installer detects this and says so, rather than
pretending otherwise.

**Linux is not supported yet, and the gap is smaller than it looks.** Reading
the code rather than guessing: macOS is assumed in exactly four places — the
platform check in `install.sh`, the `launchd` job templates, the Desktop app
bundle, and the Finder `xattr` tag. Claude Code is assumed in one
file, `merge_settings.py`. Everything else — the trunk, recall, the agents, the
`brain` CLI, the hooks themselves — is portable Python and shell already.

So this is a portable core with two thin adapters, not a macOS product. The
order it will be done in: **`systemd` units in place of `launchd`, a `.desktop`
entry in place of the `.command` file, no Finder tag, and `--core-only` as the
default shape on Linux.** No date attached to that; saying which four places
have to change is more use than a promise.

## Language

`main` is English. The French original lives on the **`fr` branch** — it is the
source the engine is extracted from, and English is derived from it. See
[`docs/translation.md`](docs/translation.md).

> **In progress**: the docs, the installer, the CLI and the eight agents are
> English. The hook comments and the capsule/planet interface strings are still
> being translated.

## For the curious

- [`docs/design-doc.md`](docs/design-doc.md) — the problem, the rejected
  alternatives, the traps hit along the way and how each was closed.
- `sync.sh` + `rules.json` + `leakcheck.py` — the chain that extracts this engine
  from a real, personal Brain without letting a single line of lived experience
  escape.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how the two branches relate, and why a
  hand-edited engine file on `fr` disappears on the next sync.
- [`SECURITY.md`](SECURITY.md) — what this writes to your machine, what runs
  unattended, and how to report a hole privately.
- [`CHANGELOG.md`](CHANGELOG.md) — generated from the tags, so it cannot drift.

## Licence

**Apache 2.0** — see [LICENSE](LICENSE).

You may use it, study it, modify it, redistribute it, and build on it, including
commercially. The licence includes a patent grant, and asks only that you keep
the attribution and state your changes.

Everything you write with it — your notes, your trunk, your skills — is yours,
and this licence makes no claim on it.
