# GreyMatter

[![CI](https://github.com/Yuno15-bb/GreyMatter-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Yuno15-bb/GreyMatter-engine/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Yuno15-bb/GreyMatter-engine?sort=semver&color=6b8afd)](https://github.com/Yuno15-bb/GreyMatter-engine/releases/latest)
[![Licence](https://img.shields.io/github/license/Yuno15-bb/GreyMatter-engine?color=8a8f98)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-8a8f98)](#compatibility)

**GreyMatter turns each session with your CLI agent into memory it can reuse —
distilled into a note, filed, linked, and handed back the moment you ask for
it. From any project, and without leaving your machine.**

<p align="center">
  <img src="docs/media/map.webp" alt="GreyMatter.app on a Mac at night, filmed on a test trunk of 792 made-up notes. The start square assembles the logo and asks for the access code; the map opens with its 21 regions. We enter a region, point at notes, search for a word, then click the logo to come back to the whole map. The graph view spreads every note in volume by meaning; the cloud turns and a hovered note lights up its links. Along the bottom, the regions, the session log and the lines being written." width="880">
</p>

Your agent is brilliant within a session and amnesic between two. Solve
something on Monday, explain it again on Thursday. GreyMatter is the part that
remembers.

The more work piles up, the more useful the tree gets — the opposite of a
conversation history, which only gets longer.

**Contents**

- [What it does](#what-it-does)
- [Install](#install)
- [How it works](#how-it-works) — from a session to a note, and the one idea holding it together
- [Commands](#commands)
- [The capsule and the map](#the-capsule-and-the-map)
- [How well it recalls](#how-well-it-recalls) — a synthetic bench, a real trunk, a public benchmark
- [What it does not do](#what-it-does-not-do)
- [Compatibility](#compatibility) · [Language](#language) · [Going further](#going-further) · [Licence](#licence)

---

## What it does

**The memory itself** — this is the product, and it is all you need:

- **A trunk.** Your lessons, projects and method, as markdown on your machine, versioned with git.
- **Recall on request.** Ask — `brain recall "…"`, `?brain` in a message, or a plain
  "any notes on…" — and the two or three notes that match are handed to your agent.
  `BRAIN_RECALL_AUTO=1` makes it fire on every prompt instead ([why it no longer does](#on-a-real-trunk)).
- **It does not go round in circles.** Notes are ranked by relevance alone, and one slot
  in three is kept for notes the search rarely surfaces, so the same few do not win forever.
- **It knows its own age.** Notes never re-checked enter a review queue, dated from the git history.
- **Four agents, eight missions.** Narcissus distills each session and files the result;
  Sulaco challenges, links and archives; Anesidora writes syntheses across projects;
  Nostromo repairs the wiring and watches the machine.
- **A closed loop.** Session ends → archive → distill → file, without being asked.
- **Updates.** The engine updates itself **every session**; **your notes are never touched**.

**And two ways to look at it**, which are extensions and install separately —
`./install.sh --core-only` leaves both out:

- **A capsule.** A pill in your menu bar showing the agents at work, live.
- **A map.** Everything you wrote as one navigable 3D map, rebuilt on every launch.

## Install

**As a Claude Code plugin** — the short way, and the one that updates itself:

```
/plugin marketplace add Yuno15-bb/GreyMatter-engine
/plugin install greymatter@greymatter
```

That gives you the whole memory: the trunk, recall, the four agents,
the `brain` command inside Claude Code (your own terminal gets it from the full
install below), and three commands you can type — `/greymatter:recall`,
`/greymatter:distill`, `/greymatter:doctor`. It creates `~/.greymatter/trunk` on your first session and
tells you so. It does **not** set up the capsule, the map or the scheduled
jobs — a plugin cannot install a background service, and pretending otherwise
would leave you with a window that never opens.

**The full install** — everything above, plus the capsule, the map and the
unattended maintenance:

```
Install GreyMatter: clone https://github.com/Yuno15-bb/GreyMatter-engine into ~/dev/greymatter, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

Or by hand: `git clone … && cd greymatter && ./install.sh`

**The memory and nothing else** — no menu bar pill, no map app, no
background job:

```bash
./install.sh --core-only
```

The `brain` command lands in `~/.local/bin`. If your shell says
`command not found`, that folder is not on your `PATH` yet — the installer
prints the one line to add to your shell profile.

Details, prerequisites and uninstall: **[INSTALL.md](INSTALL.md)**.

<details>
<summary><b>Upgrading from an older version</b></summary>

**From v2.0.x?** `brain update` carries you across the rename to GreyMatter on
its own; [docs/UPGRADING.md](docs/UPGRADING.md) says what moves and how to roll
back.

**From v1.28.1 or earlier?** Read [docs/UPGRADING.md](docs/UPGRADING.md) first —
a one-time warning about uncommitted changes in your engine checkout, the
renamed agents, and recall on request. Your notes are not affected.

</details>

## How it works

### From a session to a note

<p align="center">
  <img src="docs/media/architecture.png" alt="How a session becomes memory, top to bottom. You work with your agent, in any project. When you ask — brain recall, ?brain, or a plain request — the few notes that match are handed to your agent: a lexical search, 2 ms at 1,000 notes and 15 ms at 5,000. During the session, what is written and read is noted. At session end, the session is archived and the agents wake up. Every time, NARCISSUS distills the session into notes, then files and links them; it files and links only if distilling succeeded. Sometimes, at most one ship runs — SULACO checks the notes, NOSTROMO repairs the wiring — only when its own sensor decides, never twice in 12 hours. Everything lands in your trunk — plain markdown on your disk, versioned with git — which feeds the next recall. Three ways to look at it: the menu bar pill, the map app and the brain CLI." width="880">
</p>

### The idea holding it all together

```
~/.greymatter/engine  ← link to the ACTIVE version under versions/. Code, replaceable, disposable.
~/.greymatter/trunk     ← the TRUNK. Your notes. Changes only when YOU write.
```

The two never mix. That is what lets an update land with zero risk to your work —
and lets `uninstall.sh` remove everything while leaving your knowledge intact.

Both live behind a leading dot, out of the way. Your notes should not: the
install puts a **`GreyMatter` shortcut in your home folder**, tagged, so the one
part that is yours is the one part you can see.

<p align="center">
  <img src="docs/media/where-it-lands.png" alt="A home folder in Finder: the usual Applications, Desktop, Documents, Downloads, Movies, Music and Pictures — plus a red-tagged GreyMatter folder, with an arrow pointing at it" width="900">
</p>

Since v2.1.0 the engine carries one name everywhere — folder, commands, launchd
jobs, plugin. An older install is moved over by its own updater: the root moves
once, the old path stays behind as a link to it, and your notes are not
rewritten. What changes and how to go back: [docs/UPGRADING.md](docs/UPGRADING.md).

## Commands

Inside your agent, once the plugin is installed:

```
/greymatter:recall <subject>   what the trunk already knows about it
/greymatter:distill            turn what was just worked out into a note
/greymatter:doctor             check the wiring and the trunk
```

And in any shell once `install.sh` has run — with the plugin alone, ask Claude to run them:

```bash
brain status          where the trunk stands
brain recall <word>   search your memory
brain doctor          tree health (dead links, inconsistencies)
brain review          full audit of the trunk
brain next            your resume points
brain capsule         open the menu bar pill  (stop · status)
brain selftest        verify the installation
brain update          update the engine  (--check · --rollback)
                      automatic every session: --auto-off / --auto-on
brain version         installed version
```

## The capsule and the map

This repository provides two desktop interfaces, and only these two, both native
macOS programs built on your Mac by the installer — no Electron, no browser tab:

- **`GreyMatter.app`** on your Desktop opens the **map**, in a window of its own.
- **The capsule** is a pill in the menu bar, showing the agents at work.

Neither of the two is the product. They are how you *watch* it — pleasant,
optional, and skipped entirely by `./install.sh --core-only`. The plugin install
never sets them up at all, because a plugin cannot install a background service.

Both need Swift, which comes with Apple's Command Line Tools
(`xcode-select --install`). Without it, the installer skips only these two and
says so; the memory works the same.

### The capsule

A small pill in the menu bar: an orb, the name of the agent at work and what it
is doing — `NARCISSUS distilling`. The orb's colour and motion follow the kind
of work, so it reads at a glance without the words.

Click it and a panel drops down: the task, how long it has run, its detail, and
a track of the agents that took part, one station each, until the work is done.

<p align="center">
  <img src="docs/media/pill.webp" alt="The capsule: a pill in the macOS menu bar naming the agent at work, and the panel it drops — agent, elapsed time, activity and detail, the run's stations, and the live orb." width="520">
</p>

It reflects **real** operations — the hooks write `state/status.json` on every
action and the pill reads it; it invents nothing. `brain capsule` opens it,
`brain capsule stop` closes it. How it is built and how to keep it off:
[capsule/README.md](capsule/README.md).

### The map

`GreyMatter.app` opens with a short self-test, then asks for your access code:
the map is locked behind one, chosen on first launch and stored only as a hash.

What opens is every region of your trunk as a small cluster, with its number of
notes. Click a region to enter it: its notes unfold into a sphere you turn with
the mouse. Point at a note and its preview appears; click it and it opens in two
layers — the plain-language section for you, the complete note for the model.
The **graph** view spreads every note out in volume by meaning, each region
kept together, so two notes about the same thing sit side by side even with no
link between them; point at a note and its links light up. Placing by meaning
needs the optional embeddings index (the one `brain recall --semantic` uses);
without it, the graph view keeps the panel's layout.

Along the bottom, three panes: the regions and their share of notes, what this
session has read, written and committed, and the lines being written right now.

It is read-only: nothing you do in the map changes a note. It is rebuilt from
your trunk on every launch, and quitting the app stops its local server.

## How well it recalls

Three measurements, from the most controlled to the most real. Each one says
what it does not show.

### On a synthetic bench

Measured, not asserted — `tests/recall_benchmark.py`, on a synthetic corpus
where finding the answer means picking one note out of ~120 that share its
subject and most of its vocabulary:

| notes | P@1 | P@3 | MRR | off-topic in what it hands back | per search (median) |
|---|---|---|---|---|---|
| 100 | 0.94 | 0.98 | 0.96 | 35% | 0.2 ms |
| 1000 | 0.79 | 0.93 | 0.86 | 24% | 2.4 ms |
| 5000 | 0.46 | 0.84 | 0.64 | 39% | 15 ms |

Measured 2026-09-27 on an Apple-silicon Mac. "Per search" is the search
alone; a fresh `brain recall` also loads its cached index first, about
0.1 s at 1,000 notes.

It holds to about a thousand notes and degrades sharply past that. Published
here because a memory tool that will not say how well it remembers is asking
for trust it has not earned. The CI enforces these numbers as thresholds.

<details>
<summary><b>This bench does NOT measure everything</b></summary>

Its corpus is synthetic, so its vocabulary is coherent by construction: it says
nothing about morphology ("ranger" versus "rangement") nor about the
French/English mix, which are two real causes of an unfindable note. Its
numbers did not move when those two points were fixed — that is a limit of the
bench, not the absence of an effect.

</details>

### On a real trunk

Measured on 2026-08-12 against the author's living Brain (312 notes), 10
questions about real facts of the author's work, 50 runs isolated from one another:

| what the assistant has | right answers | tokens per exchange |
|---|---|---|
| nothing | **0/10** | 178 k |
| the trunk + the map, **without** recall | **8/10** | 264 k |
| **the full system**, recall on every prompt | **10/10** | **168 k** |

When the question is about the trunk, recall does not cost context, it **saves**
it: with no suggestion the assistant has to search, and searching burns turns.
The detail of the protocol — and the three campaigns that had to be thrown away
before an honest measurement came out — lives in the author's trunk, not here.

<details>
<summary><b>Why recall now waits to be asked</b></summary>

Most prompts are not questions about the trunk. Over the following month of
daily use, 3,256 notes were offered on their own and 139 of them were opened
afterwards — 4.27 %. The suggestion block cost its noise on every message for a
service rendered about four times in a hundred, so since 2026-09-09 it fires
only when you ask. The search itself did not change: the numbers above still
hold whenever you do.

</details>

### On a public benchmark

[LongMemEval](https://github.com/xiaowu0162/LongMemEval) asks 500 questions,
each hidden in a long history of past conversations: about 48 of them per
question in its S set, about 475 in its M set. We measured **retrieval only** —
is a conversation holding the answer among the five handed back
(recall-any@5)? — not whether an agent then answers correctly. Measured
2026-09-26, same questions and same scoring for every system:

| system | S (~48 conversations) | M (~475 conversations) |
|---|---|---|
| **GreyMatter**, default search | **96.8 %** | **86.4 %** |
| a plain BM25, nothing else | 96.8 % | 86.8 % |
| claude-mem's search alone (Chroma, one message per entry) | 96.4 % | 83.0 % |
| agentmemory hybrid, its own code at `bcf4f0d` | 95.6 % | 78.6 % |
| GreyMatter, semantic mode | 88.2 % | 61.0 % |

**Read it for what it says.** GreyMatter's default search ties a plain BM25 —
the textbook keyword ranking — on both sets (no significant difference:
p = 1.0 on S, p = 0.77 on M). It is ahead of claude-mem's search on M
(p = 0.046), and only its search: claude-mem's full memory was not tested.
agentmemory advertises 95.2 %; we measured 95.6 % on S and 78.6 % on M. So the
bench shows GreyMatter is not behind — not that it is better than the simplest
baseline. Its semantic mode (`brain recall --semantic`, static embeddings) loses on
both sets; it stays off unless you ask for it.

## What it does not do

- **It makes no request of its own.** No telemetry, no network call beyond
  `git pull`. What travels is what your prompts already carry: when you ask
  for recall, the hook adds the name, description and path of two or three
  notes to that prompt, and agents you start read whole notes. Both go to your
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

## Compatibility

**macOS.** launchd and `open` are used; the capsule and the map app are built
with Swift from Apple's Command Line Tools.

**Claude Code** for the full experience: it is what fires the hooks (recall,
archiving, autonomous maintenance, status line). With another CLI agent, GreyMatter
installs and works **on demand** — trunk, agents, `brain`, map, capsule — but
without the closed loop. The installer detects this and says so, rather than
pretending otherwise.

<details>
<summary><b>Linux is not supported yet, and the gap is smaller than it looks</b></summary>

Reading the code rather than guessing: macOS is assumed in exactly four places —
the platform check in `install.sh`, the `launchd` job templates, the Desktop app
bundle, and the Finder `xattr` tag. Claude Code is assumed in one
file, `merge_settings.py`. Everything else — the trunk, recall, the agents, the
`brain` CLI, the hooks themselves — is portable Python and shell already.

So this is a portable core with two thin adapters, not a macOS product. The
order it will be done in: **`systemd` units in place of `launchd`, a `.desktop`
entry in place of the `.command` file, no Finder tag, and `--core-only` as the
default shape on Linux.** No date attached to that; saying which four places
have to change is more use than a promise.

</details>

## Language

`main` is the product, and it is English: the docs, the installer, the CLI,
the agents, the hooks and the capsule and map interfaces. The French
original lives on the **`fr` branch**, the staging copy the engine is extracted
from; see [`docs/translation.md`](docs/translation.md).

Recall understands requests in French as well as English. A single setting
that switches every surface to French, without a second install, is planned
and not built.

## Going further

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
