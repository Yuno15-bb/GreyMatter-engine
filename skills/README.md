# `skills/` — three that drive the tool, none that carry knowledge

There are two kinds of skill here, and conflating them is what this file exists
to prevent.

**Skills that drive C Brain** — `recall`, `distill`, `doctor` — ship with it.
They are the product's surface, the same category as the `brain` command: they
operate the tool and know nothing about you. Without them, installing the plugin
gives a user hooks they cannot see and no command they can type.

**Skills that carry a way of working** ship with nothing, by explicit decision.
That is what the rest of this file is about.

A skill encodes a way of working: it names your clients, your projects, your
context, your calibration examples. That is exactly what makes it good for its
author and useless — or indiscreet — for anyone else. Measured on the original
skill set: **20 out of 20** contained personal markers. Not one was transferable
as-is.

What travels is not the skill. It is **the standard that produces it**.

**Forge your skills in `~/.claude/skills/`** — that is the directory Claude Code
reads, and it belongs to you rather than to any tool.

> ⚠ An earlier version of this file said "the installer wires this folder in".
> It does not, and never did: `install.sh` contains no reference to `skills/` at
> all. Anyone who followed that sentence wrote skills into the engine, where
> nothing reads them — no error, no warning, just a skill that never triggers.
> The instruction is corrected above rather than deleted, because a silent
> no-op is the failure mode this project keeps having to name.

---

## The house standard

Every skill must hit these nine points. Below that, it is a generic memo, not a
skill — and a generic memo triggers badly and produces nothing good.

| # | Requirement | Why |
|---|---|---|
| 1 | **Best-in-class research**, current year | A skill written from memory freezes the state of the art from two years ago. |
| 2 | **Lessons turned into executable rules** | "Watch out for caches" helps nobody; "purge the service worker before concluding" does. |
| 3 | **A named art direction** (if visual output) | With no direction chosen, output falls back to generic by default. |
| 4 | **An ordered method**, no skippable steps | The order *is* the skill: anonymize before checking, never the reverse. |
| 5 | **Numeric standards** | "Faster" cannot be verified; "< 200 ms p95" can. |
| 6 | **A self-verifiable Definition of Done** | A checkbox you cannot honestly tick without having executed. |
| 7 | **Explicit anti-patterns** | Naming what you refuse stops you relitigating it every time. |
| 8 | **Sourced references** | The reader must be able to reach the source and contradict you. |
| 9 | **A description rich in triggers AND exclusions** | It is what drives auto-invocation. Without exclusions, two skills fight over the same request. |

### Two standing rules

1. **Every new skill goes through the forge** — the recipe above, applied in
   full. No improvised skills.
2. **Forge-on-block** — a task demanding a skill that neither your skills nor
   your local resources cover is not something to hack around: forge the best
   possible skill for that need. Filling the gap once serves every project after.

### The skill / agent boundary

This is the distinction that stops everything piling into one place:

- **Autonomous system, standing trait → agent.** It runs in the background,
  untriggered, with separated powers. C Brain's agents live in `agents/`.
- **One-off action, on demand → skill.** You invoke it, it produces, it hands
  back control.

Repackaging an agent as a skill costs it its autonomy and its separation of
powers. That is a regression, not a simplification.

### Triggering

Auto-by-description as the default. Reserve deterministic hooks for the
**critical** skills — the ones whose omission is expensive (a production write
guard, a deployment checklist). Everywhere else, the description is enough.

---

## Writing your first skill

```
~/.claude/skills/<name>/SKILL.md
```

Minimal front matter, then the method:

```markdown
---
name: <name>
description: <what it does · WHEN to trigger it · when NOT to>
---

# /<name> — <the promise, in one line>

## Method (ordered, no skippable steps)
1. …

## Encoded standards
- …

## Definition of Done
- [ ] …

## Anti-patterns
- …

## References
- …
```

The `description` is the part deserving the most care: it is the only thing
Claude reads to decide whether to invoke the skill at all. Put the words *you*
will actually use in it, and say explicitly what belongs to another skill.
