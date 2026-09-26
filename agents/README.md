---
name: readme
description: Guide to the four ships (NOSTROMO, NARCISSUS, SULACO, ANESIDORA) and their eight missions — roles, boundaries, launch and autonomous thresholds
metadata:
  type: reference
---

# 🤖 Trunk agents

## In plain terms

This guide explains the agents that maintain the trunk and the boundaries between them.
Since 2026-09-20, the eight roles have been grouped into **four ships**. A ship is what
gets launched; a **mission** is the work assigned when it wakes. The task names the
mission, and each mission keeps its own tools and write permissions. `hooks/robots_permissions.py`
enforces rights by mission: the challenger can still write only `state/challenges.json`
even though it shares SULACO with the architect.

The mission that creates knowledge does not file the whole tree. The one that files it
does not create new facts. The one that doubts exposes evidence without correcting notes.
The one that connects notes does not judge their truth. The archivist never deletes alone.
These narrow boundaries keep each kind of error visible and separately testable.

The ships' names come from the *Alien* films and remain proper nouns. Mission names are
English identifiers throughout this package. The canonical files are versioned here;
`~/.claude/agents/` points to them for Claude Code discovery.

## The four ships

### 🛠 [NOSTROMO](nostromo.md) — the machine

The industrial tug maintains the engine room, reactor and wiring. In Italian,
*nostromo* means boatswain: the person who runs the ship without deciding its cargo.

- **`mechanic`** repairs hooks, wiring, symlinks and the capsule; never note content.
- **`machinist`** watches RAM, CPU, heat, battery, abandoned processes and permanent
  animations; never the trunk's knowledge or software infrastructure.

### ⚗️ [NARCISSUS](narcissus.md) — end of session

The shuttle records what deserves to survive a session and then files it.

- **`distiller`** turns session archives and transcripts into durable notes and lessons,
  or updates an existing note with new facts. It does not reorganise the whole tree.
- **`gardener`** files and deduplicates notes, maintains the `MEMORY.md` and
  `lessons/INDEX.md` map, repairs obvious `[[...]]` links, masks secrets and checks
  coherence and utility. It does not create knowledge.

### 🔭 [SULACO](sulaco.md) — knowledge watch

The watch carries specialists to examine the tree; at most one mission wakes per pass.

- **`challenger`** tests stale, false, contradicted, unsupported and oversold claims;
  records evidenced doubts in `state/challenges.json` and corrects no note.
- **`architect`** reads the whole graph topology to connect isolated notes, detached
  components and meaningful cross-domain bridges. The gardener works note by note;
  the architect works across the entire tree.
- **`archivist`** checks freshness and dead weight, then proposes archiving. It never
  deletes or archives without human approval.

### 🕸 [ANESIDORA](anesidora.md) — synthesis on demand

The recovery ship reads what earlier missions learned. It has no schedule.

- **`synthesizer`** writes a dense cross-project essay in `lessons/` containing
  second-order knowledge that no individual note states alone.

> **Eight missions, one team.** The distiller writes; the gardener files locally;
> the architect connects globally; the challenger tests; the synthesizer draws
> a wider conclusion; the archivist proposes cold storage; the mechanic repairs
> infrastructure; the machinist cares for the physical machine.

## How to launch them

In a Claude Code session, ask for a ship and name its mission. For example,
"launch NARCISSUS on my last session, first as distiller and then as gardener".
Alternatively, use `--agent narcissus` with a task beginning with the desired
mission. The automatic launchers send only the matching `## MISSION — <name>`
section, avoiding the cost and confusion of the other missions.

After a substantial session:

1. `narcissus` as `distiller` extracts durable notes.
2. `narcissus` as `gardener` checks their placement, links and map coverage.

## Reinstalling the agent surface

```bash
mkdir -p ~/.claude/agents
# Link all four ships; README.md is a guide, not an agent.
for a in ~/.c-brain/trunk/agents/*.md; do
  [ "$(basename "$a")" = "README.md" ] && continue
  ln -sf "$a" ~/.claude/agents/"$(basename "$a")"
done
```

`model:` is the manual-launch default. An automatic pass chooses its model **per
mission**, rather than using the ship's front matter. A dedicated inter-project
linking agent and an autonomous architect watch have already been implemented
as SULACO's architect mission and `hooks/brain_upkeep.py`.

## The second autonomous layer — cohesion watch

After the NARCISSUS SessionEnd sequence (`distiller` → `gardener`),
`hooks/brain_upkeep.py` runs a separate watch:

1. Mechanical sensors refresh topology, utility and accumulated coherence data.
2. A mission is eligible only when its sensor passes a work threshold and its
   12-hour cooldown has elapsed.
3. At most **one** mission wakes per pass, in this order: challenger → architect →
   archivist → mechanic (`brain_upkeep.ORDER`). This bounds model cost.

Thresholds: architect (at least one isolated note, three questionable placements,
two components or eight missing links); challenger (at least one actionable `(a,b)`
pair in `coherence.json`); archivist (three dead-weight notes); mechanic (one
infrastructure defect in `doctor.json`). Arbitration notes alone do not wake the
challenger. The watch is best effort: a quota or login failure skips a pass without
losing source data. Inspect the choice with `python3 hooks/brain_upkeep.py decide`.

The **mechanic does run automatically** when the doctor reports a defect. Its task is
bounded to defects the doctor lists, and its automatic permissions restrict writes.
Review its runs in `sessions/gardening.log` because an attempted infrastructure
repair is not always replayable.

Every wake writes a per-mission line to `state/agents.jsonl` with the mission, ship,
layer and duration. Layer one is recorded there too. After gardening,
`auto_maintain` reruns `brain_doctor --json` and logs any remaining defects, so the
gardener is not the sole judge of its own work. ANESIDORA remains manual until a
meaningful thematic-density sensor exists.

`python3 tests/invariants_brain.py` checks sensors, legacy-entry tolerance,
mission models and tasks, and agent discovery. `hooks/selftest.sh` runs it too.
