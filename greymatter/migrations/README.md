# Migrations

One script per change that requires an adaptation on an already-installed
machine. Named `001-something.sh`, run **in order**, **exactly once** (the log
lives at `~/.greymatter/state/applied-migrations.txt`).

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

TRUNK="$HOME/.greymatter/trunk"

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
| 001 | `001-rename-user-dir.sh` | `~/claude-brain` → `~/.greymatter/trunk`, plus a compatibility link at the old location. |
| 002 | `002-rename-root.sh` | `~/.c-brain` → `~/.greymatter`, plus a compatibility link at the old location. <!-- pre-rename --> |

**001 in two lines.** The user directory carried an Anthropic trademark inside a
public product, and made a fourth name for a single thing. After it: one root,
`~/.greymatter`, engine and trunk side by side.

It only **moves**. The rewiring (engine symlinks, `settings.json`, launchd
plists, Desktop launcher) is redone right after by `install.sh`, which
`update.sh` calls anyway. A migration that rewired too would duplicate that
logic — and the two copies would drift.

The compatibility link stays **permanently**. GreyMatter no longer needs it, but
everything GreyMatter does not know about does: the CLI agent's memory link,
personal scripts, a path written down somewhere.

**002 in two lines.** Until v2.1.0 the root, the Home shortcut, the launchd jobs
and the plugin still said C Brain while the product said GreyMatter. <!-- pre-rename -->
One name now, everywhere; the old root stays reachable through a permanent link.

It follows 001 to the letter: it only moves, a replay does nothing, a collision
(both folders exist and are different) stops dead. `install.sh` runs it before
anything else, so a fresh `git pull && ./install.sh` migrates too, and 001 calls
it first, so a machine two versions behind never grows a second, empty root.
The old launchd jobs, the old hook commands in `settings.json`, the old Desktop
app and the old Home shortcut are retired by `install.sh`, only when they are
provably ours (label, bundle id, link target).

## Why a `cbrain/migrations/` folder still exists <!-- pre-rename -->

An updater from v2.0.x runs the candidate's migrations from that folder
and from nowhere else. That folder therefore keeps one forwarding stub per
script, which `exec`s the real one here. It is the only place the old name
survives in the tree (`tests/one_name.py` skips it by path). It can go once no
v2.0.x install is left to update.
