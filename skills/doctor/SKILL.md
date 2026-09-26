---
description: Check the health of the C Brain installation and trunk — dead links, unindexed notes, broken hooks, stale state. Use when recall seems to return nothing, when notes are not being saved, when the user says C Brain "is not working", or before trusting the trunk for something important.
---

# Check the trunk and the wiring

Two commands, and they answer different questions. Run both.

```bash
brain selftest    # is the ENGINE wired correctly? (hooks, links, permissions)
brain doctor      # is the TRUNK coherent? (dead [[links]], orphans, index gaps)
```

## Reading the result

- **selftest red** → the installation is the problem. Re-run `install.sh`; it
  is idempotent and repairs its own wiring.
- **doctor red** → the notes are the problem. Dead `[[links]]` and notes missing
  from `MEMORY.md` are the two that actually cost recall.
- **Both green but recall returns nothing** → the query, not the machinery. Try
  narrower terms; the ranking is lexical, so it matches words, not meaning.

## What not to conclude

A silent hook is not a healthy hook. If notes are not being saved and both
commands are green, check that the hooks are registered at all — a hook whose
path no longer resolves does not fail loudly, it simply stops recording.
