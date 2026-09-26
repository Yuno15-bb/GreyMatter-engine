#!/bin/bash
# Launches the Knowledge Planet: regenerates the graph, serves planet/ locally, opens the browser.
# (A server is required because the globe loads graph.json through fetch() — impossible over file://.)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
BRAIN="$(cd "$DIR/.." && pwd)"
PORT="${1:-8765}"

python3 "$BRAIN/hooks/coactivation.py"            # heat + current session, up to date
python3 "$BRAIN/hooks/graph_export.py"            # graph up to date before opening

# kill any server already on this port (clean restart)
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill 2>/dev/null || true

echo "📟  Trunk planet — MOTHER signature — http://localhost:$PORT  (Ctrl+C to stop)"
( sleep 1; open "http://localhost:$PORT" ) &
cd "$DIR"
exec python3 -m http.server "$PORT"
