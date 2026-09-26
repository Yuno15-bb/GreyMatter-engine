#!/usr/bin/env bash
# demo.sh — three example notes, placed and taken away on demand.
#
# WHY. The number one abandonment point of a memory tool is the first screen:
# you install, type `brain status`, see emptiness, uninstall. An empty trunk
# shows neither what a note looks like, nor what recall can find, nor why the
# links matter. These three notes show it — and leave cleanly once they have.
#
# Usage:
#   brain demo            place the notes
#   brain demo --remove   take them away
#   brain demo --status   report where they stand
set -euo pipefail

ENGINE="${CBRAIN_ENGINE:-$HOME/.c-brain/engine}"
TRUNK="${CBRAIN_TRUNK:-$HOME/.c-brain/trunk}"
SRC="$ENGINE/demo"

# Boundaries of the index block. Writing between two markers rather than "at the
# end" keeps removal an exact operation, even if the user has written below it.
BEGIN="<!-- c-brain:demo:begin -->"
END="<!-- c-brain:demo:end -->"

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

[ -d "$SRC" ]   || { echo "❌ demo notes not found ($SRC)"; exit 1; }
[ -d "$TRUNK" ] || { echo "❌ trunk not found ($TRUNK)"; exit 1; }

# Relative note paths, derived from the source folder — never hand-listed. A
# hardcoded list drifts from the content on the first addition, and removal then
# leaves orphans nothing knows about any more.
notes() { (cd "$SRC" && find . -name '*.md' | sed 's|^\./||' | sort); }

# Is a note still exactly as we placed it?
untouched() {  # untouched <relative path>
  cmp -s "$SRC/$1" "$TRUNK/$1"
}

index_block() {
  echo "$BEGIN"
  echo "*(demo notes — \`brain demo --remove\` takes them away)*"
  echo
  while read -r rel; do
    name=$(sed -n 's/^name: *//p' "$SRC/$rel" | head -1)
    desc=$(sed -n 's/^description: *//p' "$SRC/$rel" | head -1 | cut -c1-90)
    echo "- [$name]($rel) — $desc"
  done < <(notes)
  echo "$END"
}

drop_block() {  # removes the block from MEMORY.md, if present
  local mem="$TRUNK/MEMORY.md"
  [ -f "$mem" ] || return 0
  python3 - "$mem" "$BEGIN" "$END" <<'PY'
import re, sys
path, begin, end = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
# \n* on both sides: without it, every place/remove cycle leaves one more blank
# line behind and the file swells a little each time.
new = re.sub(r"\n*" + re.escape(begin) + r".*?" + re.escape(end) + r"\n*",
             "\n", text, flags=re.S)
if new != text:
    open(path, "w", encoding="utf-8").write(new)
PY
}

case "${1:-install}" in

  --status)
    n=0; modified=0
    while read -r rel; do
      if [ -f "$TRUNK/$rel" ]; then
        n=$((n + 1))
        untouched "$rel" || modified=$((modified + 1))
      fi
    done < <(notes)
    if [ "$n" = "0" ]; then
      say "no demo notes in place (\`brain demo\` to place them)"
    else
      say "$n demo note(s) in place$([ "$modified" -gt 0 ] && echo ", $modified of them edited by you")"
    fi
    ;;

  --remove)
    removed=0; kept=0
    while read -r rel; do
      dst="$TRUNK/$rel"
      [ -f "$dst" ] || continue
      # An edited note is no longer a demo note: it is work. We leave it.
      # Erasing somebody's content "because we put it there" is exactly what a
      # memory tool never does.
      if untouched "$rel"; then
        rm -f "$dst"
        removed=$((removed + 1))
      else
        warn "kept (you edited it): $rel"
        kept=$((kept + 1))
      fi
    done < <(notes)
    # Project subfolders left empty. `-mindepth 1` is mandatory: without it, a
    # trunk whose projects/ ends up empty would lose projects/ itself — we would
    # have removed a demo and taken a structural folder with it.
    find "$TRUNK/projects" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    drop_block
    say "$removed note(s) removed$([ "$kept" -gt 0 ] && echo ", $kept kept")"
    [ "$kept" = "0" ] && say "the index is clean — the trunk is yours"
    ;;

  install|"")
    placed=0; skipped=0
    while read -r rel; do
      dst="$TRUNK/$rel"
      if [ -f "$dst" ] && ! untouched "$rel"; then
        warn "already there and different, not overwritten: $rel"
        skipped=$((skipped + 1))
        continue
      fi
      mkdir -p "$(dirname "$dst")"
      cp "$SRC/$rel" "$dst"
      placed=$((placed + 1))
    done < <(notes)

    mem="$TRUNK/MEMORY.md"
    drop_block   # drop the old block first: re-running must not stack blocks
    { [ -f "$mem" ] && cat "$mem"; echo; index_block; } > "$mem.tmp" && mv "$mem.tmp" "$mem"

    say "$placed note(s) placed$([ "$skipped" -gt 0 ] && echo ", $skipped skipped")"
    echo
    say "Try now:"
    say "  brain recall cache deploy    ← what recall finds"
    say "  brain status                 ← the state of the trunk"
    say "  brain demo --remove          ← once you no longer need them"
    ;;

  *)
    echo "Usage: brain demo [--remove|--status]"
    exit 1
    ;;
esac
