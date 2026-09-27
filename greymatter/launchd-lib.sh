#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# launchd-lib.sh — WHO OWNS A LAUNCHD IDENTITY, and what may be done about it.
#
# Sourced by install.sh and uninstall.sh. One definition, two consumers, for the
# same reason engine-lib.sh exists: the script that registers a job and the one
# that removes it must agree, byte for byte, on what "ours" means.
#
# THE INCIDENT. On 2026-08-18 an install running under a throwaway $HOME took
# over the author's jobs for about 28 hours. `launchctl` indexes by Label inside
# the per-user domain (gui/<uid>) — not by $HOME, not by the path of the plist.
# `launchctl unload <path>` therefore frees whatever the registry holds under
# the Label written INSIDE that file, including a job another installation
# loaded from somewhere else. The plists on disk never changed: the substitution
# was invisible to ls, cat and shasum.
#
# THE RULE. Ownership is a RECORDED FACT, exactly as `state/engine-managed`
# records that the installer built the engine. It is NEVER inferred from:
#   · the Label, or the `com.greymatter.*` prefix   · the presence of a plist
#   · $HOME                                          · ProgramArguments
#   · the likelihood that an older GreyMatter created the job
# The absence of a record is not a proof of ownership either. When the registry
# holds an identity we cannot prove is ours, we refuse BY NAME and change
# nothing. Adopting it is a separate, deliberate operation — not a side effect
# of installing.
#
# EXIT CODES (they are the contract; callers branch on them)
#   0  done            2  bad usage
#   3  refused: the identity exists and this installation cannot prove it owns it
#   4  launchctl failed — and the record was NOT written
#
# THE REGISTRY IS THE AUTHORITY, NOT THE FILE ON DISK. Presence is asked of
# `launchctl print`, never of `ls`. Everything here goes through that one
# function so a test can substitute a launchctl and never touch a real domain.

# The record. One Label per line. Written only after an operation SUCCEEDED.
gm_launchd_record_file() {
  printf '%s\n' "${GM_LAUNCHD_RECORD:-${GM:-$HOME/.greymatter}/state/launchd-owned}"
}

gm_launchd_say()  { printf '  %s\n' "$*"; }
gm_launchd_warn() { printf '  ! %s\n' "$*" >&2; }

# ─── The two questions, kept apart ───────────────────────────────────────────
# "Does the domain hold this identity?" and "did we put it there?" are different
# questions with different instruments. Conflating them is the bug.

gm_launchd_registered() {   # <label> → 0 if the LIVE registry holds it
  launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1
}

gm_launchd_owned() {        # <label> → 0 if THIS installation recorded it
  local f; f="$(gm_launchd_record_file)"
  [ -f "$f" ] || return 1
  grep -qxF "$1" "$f" 2>/dev/null
}

gm_launchd_remember() {     # <label> — only ever called after a success
  local f; f="$(gm_launchd_record_file)"
  mkdir -p "$(dirname "$f")" || return 1
  gm_launchd_owned "$1" || printf '%s\n' "$1" >> "$f"
}

gm_launchd_forget() {       # <label>
  local f tmp; f="$(gm_launchd_record_file)"
  [ -f "$f" ] || return 0
  tmp="$f.$$"
  grep -vxF "$1" "$f" > "$tmp" 2>/dev/null || :
  mv "$tmp" "$f"
}

gm_launchd_refuse() {       # <label> — the named refusal, one voice for both scripts
  gm_launchd_warn "The service $1 already exists, and this installation holds no"
  gm_launchd_warn "  proof that it owns it. NOTHING was changed: the job that is"
  gm_launchd_warn "  running keeps running, and its plist was not touched."
  gm_launchd_warn "  If this job is yours, adopt it deliberately — installing must"
  gm_launchd_warn "  not decide that for you. A refusal that does not say what to do"
  gm_launchd_warn "  next is just an obstacle, so here it is:"
  gm_launchd_warn "    bash ${GM:-$HOME/.greymatter}/engine/greymatter/adopt-launchd.sh $1"
  return 3
}

# ─── Registering a job ───────────────────────────────────────────────────────
gm_launchd_install() {      # <label> <plist-path> → 0 | 3 refused | 4 failed
  local label="$1" plist="$2" out
  [ -n "$label" ] && [ -n "$plist" ] || return 2

  if gm_launchd_registered "$label"; then
    gm_launchd_owned "$label" || { gm_launchd_refuse "$label"; return 3; }
    # Ours: replacing it is legitimate. The RESULT is checked — the old code
    # wrote `2>/dev/null || true`, so a failed unload followed by a failed load
    # left no job and no message. cf. the lesson that an explicit success can
    # cover a mechanism in failure.
    if ! out="$(launchctl unload "$plist" 2>&1)"; then
      gm_launchd_warn "unload of $label failed: ${out:-(no output)}"
      return 4
    fi
  fi

  if ! out="$(launchctl load "$plist" 2>&1)"; then
    gm_launchd_warn "load of $label failed: ${out:-(no output)}"
    # NOT recorded. A record written on a failure would claim, at the next run,
    # ownership of an identity we never managed to register — the inference this
    # whole file exists to remove.
    return 4
  fi
  gm_launchd_remember "$label" || return 4
  gm_launchd_say "+ $label loaded"
  return 0
}

# ─── Removing a job ──────────────────────────────────────────────────────────
gm_launchd_uninstall() {    # <label> <plist-path> → 0 | 3 refused | 4 failed
  local label="$1" plist="$2" out
  [ -n "$label" ] && [ -n "$plist" ] || return 2

  # An uninstaller that removes what it did not install is the same defect
  # wearing the opposite sign. The plist ON DISK proves nothing either: a legacy
  # install of GreyMatter put its file at this very path.
  if ! gm_launchd_owned "$label"; then
    if gm_launchd_registered "$label"; then
      gm_launchd_warn "$label is running but was not registered by this installation."
    else
      gm_launchd_warn "$label was not registered by this installation."
    fi
    gm_launchd_warn "  Left alone, plist included. Nothing was unloaded."
    return 3
  fi

  if gm_launchd_registered "$label"; then
    if ! out="$(launchctl unload "$plist" 2>&1)"; then
      gm_launchd_warn "unload of $label failed: ${out:-(no output)}"
      return 4
    fi
  fi
  rm -f "$plist"
  gm_launchd_forget "$label"
  gm_launchd_say "- $label"
  return 0
}
