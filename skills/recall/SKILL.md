---
description: Search the C Brain trunk for notes relevant to a subject, and read the ones that matter. Use when the user asks what they already know about something, wants past decisions on a topic, says "did we solve this before", "what do I have on X", "check my notes", or when a task smells like something already worked out once.
---

# Recall from the trunk

Retrieve what is already known before working something out again.

## How

Run the recall, top 5, and read what comes back:

```bash
brain recall "$ARGUMENTS"
```

If `brain` is not on the PATH, the plugin ships it — call it directly:
`"${CLAUDE_PLUGIN_ROOT}/bin/brain" recall "$ARGUMENTS"`.

Each result gives a score, a note name and a path relative to the trunk
(`~/.c-brain/trunk`). **Open the ones above the noise floor and actually read
them** — the ranking is lexical, so it tells you where to look, never what is
true.

## Then

- Say what the notes establish, and cite each one by its path so the user can
  check you.
- Say plainly when nothing relevant came back. A confident answer assembled
  from three weakly-matching notes is worse than "the trunk has nothing on
  this" — it looks like memory and is not.
- Never rewrite a note as a side effect of reading it.

## Scale

Recall holds well to about a thousand notes and degrades past that
(`tests/recall_benchmark.py` publishes the numbers). On a large trunk, prefer
several narrow queries over one broad one.
