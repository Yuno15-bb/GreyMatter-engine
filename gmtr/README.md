# GMTR

GMTR is the local, read-only interface for a GreyMatter trunk. It opens with a self-test and access-code prompt, then shows the map, agent panel, and activity stream.

Run `gmtr/launch.sh` from the engine checkout or installed engine. It uses port 8767 by default; pass a port as the first argument to change it. The launcher refreshes the trunk graph and heat data, builds `gmtr/carte/index.html` from the engine's `planet/index.html`, then serves GMTR at `127.0.0.1`.

Set or change the access code before opening protected screens:

```sh
printf '%s' 'your-code' | python3 gmtr/serveur.py --definir-code
```

The server stores only a PBKDF2 hash in `<trunk>/state/gmtr-code`. It refuses protected routes until a code is set. `BRAIN_HOME` selects the trunk; otherwise the engine's `brain_racine.py` uses `~/.greymatter/trunk`.

The opening screen reads the startup inventory from `/amorce.json`. The map uses the engine's `planet/index.html` and the trunk's `planet/graph.json` and `planet/textes.json`. The agent panel reads `state/agents.jsonl`. The activity stream reads `state/note-writes.jsonl`, `state/read_log.jsonl`, `state/recall_log.jsonl`, and `state/git-journal.jsonl`. The map's live writing column observes trunk file changes and, if `GMTR_COMPANION` is set, JSONL diff files in that directory. `/etat.json` reads graph counts, doctor and session state, and the write journal. Missing state is reported as unavailable.
