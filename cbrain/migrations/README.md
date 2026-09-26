# Migrations

One script per change that requires an adaptation on an already-installed
machine. Named `001-something.sh`, run **in order**, **exactly once** (the log
lives at `~/.c-brain/state/applied-migrations.txt`).

## The three rules

1. **Never destructive to content.** `lessons/`, `projects/`, `meta/`, `life/`,
   `sessions/` are not modified here. A migration touches the installation, not
   somebody's knowledge.
2. **Idempotent anyway.** The log can be lost (restore, new machine). Replaying a
   migration must break nothing.
3. **Failure means stop.** A non-zero exit halts the update and lets
   `brain update --rollback` do its job. Better to stop dead than proceed
   halfway.

## Template

```bash
#!/usr/bin/env bash
# 001-example.sh — <what it adapts, and why it was needed>
set -euo pipefail

TRUNK="$HOME/.c-brain/trunk"

# Check BEFORE acting: that is what makes a replay harmless.
if [ -f "$TRUNK/state/old-file.json" ]; then
  mv "$TRUNK/state/old-file.json" "$TRUNK/state/new-file.json"
  echo "  state renamed"
else
  echo "  nothing to do"
fi
```

## Migrations written so far

| # | Script | What it adapts |
|---|---|---|
| 001 | `001-rename-user-dir.sh` | `~/claude-brain` → `~/.c-brain/trunk`, plus a compatibility link at the old location. |

**001 in two lines.** The user directory carried an Anthropic trademark inside a
public product, and made a fourth name for a single thing. After it: one root,
`~/.c-brain`, engine and trunk side by side.

It only **moves**. The rewiring (engine symlinks, `settings.json`, launchd
plists, Desktop launcher) is redone right after by `install.sh`, which
`update.sh` calls anyway. A migration that rewired too would duplicate that
logic — and the two copies would drift.

The compatibility link stays **permanently**. C Brain no longer needs it, but
everything C Brain does not know about does: the CLI agent's memory link,
personal scripts, a path written down somewhere.
