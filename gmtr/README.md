# GMTR

GMTR is the local, read-only interface for a GreyMatter trunk. It opens with a self-test and access-code prompt, then shows the map, agent panel, and activity stream.

Run `gmtr/launch.sh` from the engine checkout or installed engine. It uses port 8767 by default; pass a port as the first argument to change it. The launcher refreshes the trunk graph and heat data, then serves the committed `gmtr/carte/index.html` at `127.0.0.1`.

Set or change the access code before opening protected screens:

```sh
printf '%s' 'your-code' | python3 gmtr/serveur.py --definir-code
```

**What the code protects, and what it does not.** It is a screen lock: it keeps
the map from another person at your Mac and from web pages. The server listens
on 127.0.0.1 only, answers only to the names `127.0.0.1` and `localhost`, locks
for 30 s after five wrong codes (even when they arrive at once), and a session
expires after 12 hours. It does not protect your notes from a program running
under your own account: that program can read the notes themselves, and the
hash below. The four-character minimum fits a screen lock, not a secret.

The server stores only a PBKDF2 hash in `<trunk>/state/gmtr-code`. It refuses protected routes until a code is set. `BRAIN_HOME` selects the trunk; otherwise the engine's `brain_racine.py` uses `~/.greymatter/trunk`.

The opening screen reads the startup inventory from `/amorce.json`. The map uses its committed HTML and the trunk's `planet/graph.json` and `planet/textes.json`. The agent panel reads `state/agents.jsonl`. The activity stream reads `state/note-writes.jsonl`, `state/read_log.jsonl`, `state/recall_log.jsonl`, and `state/git-journal.jsonl`. The map's live writing column observes trunk file changes and, if `GMTR_COMPANION` is set, JSONL diff files in that directory. `/etat.json` reads graph counts, doctor and session state, and the write journal. Missing state is reported as unavailable.
