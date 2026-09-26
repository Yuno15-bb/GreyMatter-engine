---
description: Turn what was just worked out into a C Brain note — filed in the right zone, linked to what it relates to, indexed. Use when the user says "remember this", "save that", "note it down", "distill this session", or when a non-obvious problem has just been solved and the reasoning would otherwise be lost.
---

# Distill into a note

A session ends and its reasoning goes with it unless something is written down.
This writes it down, in the shape the trunk expects.

## What deserves a note

Only what a future reader could not re-derive cheaply:

- a defect and **how it was found**, not just the fix;
- a decision, its alternatives, and why they lost;
- a constraint that is not visible in the code.

Not: what the repository already records, what only matters to this
conversation, or a summary of work anyone could read from the diff.

## Shape

One fact per file, in `~/.c-brain/trunk/<zone>/<slug>.md` where zone is
`lessons` (cross-project), `projects/<name>`, `meta` (ways of working) or
`life`.

```markdown
---
name: <short-kebab-case-slug>
description: <one line — this is what recall ranks on, so make it say the fact>
metadata:
  type: reference
---

<the fact, stated so it is useful without this conversation>

Why: <what makes it non-obvious>

How to apply: <the reflex it should produce next time>
```

Link related notes with `[[their-slug]]`. Link generously — a link to a note
that does not exist yet marks something worth writing, not an error.

## Then

- Add one line to `MEMORY.md`: `- [Title](path.md) — hook`.
- **Check first whether a note already covers it** and update that one instead.
  Two notes on one subject is how a trunk starts lying.
- Convert relative dates to absolute ones. "Last Tuesday" rots.
