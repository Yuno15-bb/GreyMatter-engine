#!/bin/bash
# Regenerate trunk data before serving the committed GMTR map locally.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$(cd "$DIR/.." && pwd)"
PORT="${1:-8767}"
python3 "$ENGINE/hooks/coactivation.py"
python3 "$ENGINE/hooks/graph_export.py"
( sleep 1; open "http://127.0.0.1:$PORT" ) &
exec python3 "$DIR/serveur.py" "$PORT"
