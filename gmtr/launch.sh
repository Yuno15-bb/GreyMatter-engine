#!/bin/bash
# Regenerate trunk data before serving the committed GMTR map locally.
#
# FIRST LAUNCH ASKS FOR AN ACCESS CODE. The map is locked behind one, and a
# launcher double-clicked from the Desktop has no terminal to type it into: a
# missing code would open a browser on a lock nobody can open. So the code is
# asked here, in a native dialog when there is no terminal, and asked twice —
# a typo in a hidden field would lock the user out of their own map.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$(cd "$DIR/.." && pwd)"
PORT="${1:-8767}"

demander() {   # $1 = prompt; prints the answer, fails if cancelled
  if [ -t 0 ]; then
    local r; read -r -s -p "$1 " r; echo >&2; printf '%s' "$r"
  else
    osascript -e "text returned of (display dialog \"$1\" default answer \"\" with hidden answer with title \"GreyMatter\")" 2>/dev/null
  fi
}
prevenir() {
  if [ -t 1 ]; then echo "$1" >&2
  else osascript -e "display alert \"GreyMatter\" message \"$1\"" >/dev/null 2>&1 || true; fi
}

if ! python3 "$DIR/serveur.py" --code-present; then
  CODE="$(demander "Choose an access code for your map (4 characters or more):")" || exit 0
  ENCORE="$(demander "Type the same code again:")" || exit 0
  if [ "$CODE" != "$ENCORE" ]; then prevenir "The two codes differ. Nothing was saved: launch again."; exit 1; fi
  if ! printf '%s' "$CODE" | python3 "$DIR/serveur.py" --definir-code >/dev/null; then
    prevenir "Code too short: four characters or more. Nothing was saved: launch again."; exit 1
  fi
fi

python3 "$ENGINE/hooks/coactivation.py"
python3 "$ENGINE/hooks/graph_export.py"
# GreyMatter.app shows the map in its own window and sets GMTR_NO_BROWSER.
[ -n "${GMTR_NO_BROWSER:-}" ] || ( sleep 1; open "http://127.0.0.1:$PORT" ) &
exec python3 "$DIR/serveur.py" "$PORT"
