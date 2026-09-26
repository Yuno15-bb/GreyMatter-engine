#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# Copy an allowlisted subset of the living Brain into this public package.
# The source is read only. --check compares source fingerprints without copying.
set -euo pipefail

SRC="${CBRAIN_SRC:-$HOME/claude-brain}"
DEST="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CBRAIN_CLAUDE_DIR:-$HOME/.claude}"

MODE="copy"
[ "${1:-}" = "--check" ] && MODE="check"

RSYNC_FLAGS=(-a --delete --itemize-changes --exclude '*.bak')
[ "$MODE" = "check" ] && RSYNC_FLAGS+=(--dry-run)

# A sync on main would overwrite the English translation with French sources.
BRANCHE="$(git -C "$DEST" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
if [ "$BRANCHE" = "main" ] && [ "${CBRAIN_ALLOW_SYNC_ON_MAIN:-}" != "1" ]; then
  echo "❌ Run ./sync.sh on the fr branch, not main."
  echo "   main is the translation; a sync would overwrite it with French source files."
  echo "   → git checkout fr    (or set CBRAIN_ALLOW_SYNC_ON_MAIN=1 deliberately)"
  exit 1
fi

[ -d "$SRC" ] || { echo "❌ Source not found: $SRC"; exit 1; }
[ "$SRC" = "$DEST" ] && { echo "❌ Source and destination are identical."; exit 1; }

MANIFEST="$DEST/.sync-manifest"

# Keep these exclusions aligned with the rsync rules below. Path based rules
# avoid hiding another file with the same name elsewhere in the source.
empreinte_source() {
  {
    shasum -a 256 "$SRC/brain" "$CLAUDE_DIR/statusline.py" \
                  "$SRC/config/ranking.json" 2>/dev/null
    find "$SRC/hooks" "$SRC/agents" "$SRC/capsule" "$SRC/planet" \
         "$SRC/companion" "$SRC/tests" -type f \
         ! -path "*/node_modules/*" ! -name "*.pyc" ! -name ".DS_Store" \
         ! -name "*.bak" \
         ! -name "desktop_sync.py" \
         ! -name "capteur_fraicheur.py" \
         ! -name "com.dgc.fraicheur.plist.template" \
         ! -name "com.*.desktop-sync.plist.template" \
         ! -name "com.claudebrain.resume.plist" \
         ! -path "*/tests/golden_recall.py" \
         ! -path "*/tests/golden_recall.json" \
         ! -path "*/tests/heldout/*" \
         ! -path "*/tests/navigation/*" \
         ! -path "*/tests/banc_navigation_hors_index.py" \
         ! -path "*/tests/banc_carte_lisibilite.py" \
         ! -path "*/tests/feuilles_de_style_intactes.py" \
         ! -path "*/tests/legende_ne_promet_que_des_touches_vivantes.py" \
         ! -path "*/tests/banc-retrieval/resultats.json" \
         ! -path "*/tests/sabotages.json" \
         ! -path "*/tests/en_clair_dette.txt" \
         ! -path "*/tests/a86_classe2.json" \
         ! -path "*/tests/banc-course-git/resultats-git-guard.json" \
         ! -path "*/capsule/assets/*" \
         ! -path "*/capsule/lottie/*" \
         ! -path "*/capsule/hand/*" \
         ! -path "*/capsule/index.html" ! -path "*/capsule/index-v2.html" \
         ! -path "*/capsule/dock-geometry.js" \
         ! -path "*/capsule/test_dock_geometry.js" \
         ! -path "*/capsule/test_verrou_parle.sh" \
         ! -path "*/capsule/main.js" \
         ! -path "*/planet/*.json" \
         ! -path "*/planet/launch-mother.sh" \
         ! -path "*/planet/archive/*" 2>/dev/null \
      | sort | xargs shasum -a 256 2>/dev/null
  } | sed "s|$SRC/||; s|$CLAUDE_DIR/||" | sort -k2
}

if [ "$MODE" = "check" ]; then
  echo "🔄 C Brain — has the living Brain changed since the last copy?"
  if [ ! -f "$MANIFEST" ]; then
    echo "  ⚠️  no fingerprint recorded — run ./sync.sh once."
    exit 1
  fi
  DIFF="$(diff <(cat "$MANIFEST") <(empreinte_source) || true)"
  if [ -z "$DIFF" ]; then
    echo "  ✅ unchanged — the package is current."
    exit 0
  fi
  CHANGES="$(printf '%s\n' "$DIFF" | grep -E '^[<>]' | awk '{print "      " $1 " " $3}' | sort -u)"
  N_CHANGES="$(printf '%s\n' "$CHANGES" | wc -l | tr -d ' ')"
  echo "  ⚠️  source changed — $N_CHANGES item(s):"
  printf '%s\n' "$CHANGES" | head -20
  if [ "$N_CHANGES" -gt 20 ]; then
    echo "      … and $((N_CHANGES - 20)) more not shown."
  fi
  echo
  echo "  → Run ./sync.sh to carry the changes, then review the git diff."
  exit 1
fi

DIVERGED=0
report() {  # report <label> <rsync output>
  if [ -n "$2" ]; then
    DIVERGED=1
    echo "  ~ $1"
    printf '%s\n' "$2" | sed 's/^/      /'
  else
    echo "  = $1"
  fi
}

sync_dir() {  # sync_dir <relative directory> <exclusions...>
  local rel="$1"; shift
  local excludes=()
  for e in "$@"; do excludes+=(--exclude "$e"); done
  mkdir -p "$DEST/$rel"
  local out
  out="$(rsync "${RSYNC_FLAGS[@]}" ${excludes[@]+"${excludes[@]}"} \
        "$SRC/$rel/" "$DEST/$rel/" 2>/dev/null || true)"
  report "$rel/" "$out"
}

sync_file() {  # sync_file <absolute source> <relative destination>
  local src="$1" dst="$DEST/$2"
  if [ ! -f "$src" ]; then
    DIVERGED=1; echo "  ! $2 — source missing ($src)"; return
  fi
  if cmp -s "$src" "$dst" 2>/dev/null; then
    report "$2" ""
  else
    report "$2" ">f  content differs"
    if [ "$MODE" = "copy" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$src" "$dst"
    fi
  fi
  return 0
}

echo "🔄 C Brain — syncing from $SRC"
[ "$MODE" = "check" ] && echo "   (--check mode: no files are written)"
echo

sync_file "$SRC/brain" "brain"

# Package-only hook metadata must survive rsync --delete. Local desktop jobs
# and files containing personal paths must never enter the public package.
sync_dir hooks \
  'desktop_sync.py' \
  'capteur_fraicheur.py' \
  'com.dgc.fraicheur.plist.template' \
  'com.*.desktop-sync.plist.template' \
  'com.claudebrain.resume.plist' \
  'hooks.json' \
  '__pycache__' '*.pyc'

sync_dir agents

# The package ships the orb. Old capsule screens, local assets and the
# author's instance-lock test belong to the living Brain; the translated
# package test is protected from --delete on this side.
sync_dir capsule 'node_modules' 'assets' 'lottie' 'index-v2.html' 'main.js' 'hand' \
                 'index.html' 'dock-geometry.js' 'test_dock_geometry.js' \
                 'test_verrou_parle.sh' 'test_lock_speaks.sh'

# All generated Planet JSON belongs to the user's trunk, including files
# introduced after this allowlist was written.
sync_dir planet '*.json' 'launch-mother.sh' 'archive'

sync_dir companion '__pycache__' '*.pyc'

# Keep package-only tests; exclude private golden sets and local result files.
sync_dir tests 'plugin_manifest.py' 'english_only.py' 'update_tag_family.sh' \
  'navigation' 'banc_navigation_hors_index.py' \
  'banc_carte_lisibilite.py' 'feuilles_de_style_intactes.py' \
  'legende_ne_promet_que_des_touches_vivantes.py' \
  'recall_benchmark.py' 'recall_cache.py' 'update_rollback.sh' 'plugin_install.sh' \
  'e2e_occupied_surfaces.sh' \
  'update_auto.sh' 'docs_aligned.py' \
  'golden_recall.py' 'golden_recall.json' \
  'heldout' 'resultats.json' 'regles_non_muettes.py' \
  'sabotages.json' 'en_clair_dette.txt' 'a86_classe2.json' \
  'resultats-git-guard.json' \
  'a84_temoins.json' 'fixtures_detection.json' '_embed_pairs.py' \
  '__pycache__' '*.pyc'

sync_file "$SRC/config/ranking.json" "skeleton/config/ranking.json"

sync_file "$CLAUDE_DIR/statusline.py" "statusline.py"

# Generalize immediately after copying, then record the source fingerprint.
# Recording it earlier would mark a failed generalization as current.
echo
echo "───"
python3 "$DEST/generalize.py"

empreinte_source > "$MANIFEST"

echo
echo "✅ Synced and generalized. Final check: python3 leakcheck.py"
