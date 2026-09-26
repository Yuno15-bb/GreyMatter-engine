#!/usr/bin/env python3
"""Animation test run: walks through EVERY activity, 8 s per step, refreshing
the timestamp to stay 'busy' (idle threshold = 6 s)."""
import json, time, os

# Derived from $HOME, not __file__: it is the TRUNK's state we drive.
STATUS = os.path.join(os.path.expanduser('~'), '.c-brain', 'trunk', 'state', 'status.json')

# ordre du pipeline → couvre les 11 activités reconnues par index.html (idle exclu)
STEPS = [
    ("distilling",   "DISTILLER — extracting notes"),
    ("gardening",    "GARDENER — filing & [[ ]] links"),
    ("filing",       "GARDENER — sorting into MEMORY.md"),
    ("correcting",   "GARDENER — fixing a note"),
    ("mapping",      "GARDENER — mapping the index"),
    ("architecting", "ARCHITECT — cross-domain bridges"),
    ("challenging",  "CHALLENGER — putting knowledge to the test"),
    ("archiving",    "ARCHIVIST — pruning dead weight"),
    ("synthesizing", "SYNTHESIZER — cross-cutting essay"),
    ("auditing",     "MECHANIC — auditing the machine"),
    ("committing",   "COMMITTING — saving to git"),
]

HOLD = 8.0       # seconds per step
REFRESH = 2.5    # rewrite the timestamp so it never falls back to idle (<6 s)

def write(state, activity=None, detail=None):
    with open(STATUS, 'w') as f:
        json.dump({"state": state, "activity": activity, "detail": detail,
                   "source": "test", "ts": time.time()}, f)

print(f"▶ Test run — {len(STEPS)} steps × {HOLD:.0f}s")
for i, (act, detail) in enumerate(STEPS, 1):
    print(f"  [{i}/{len(STEPS)}] {act} — {detail}")
    t_end = time.time() + HOLD
    while time.time() < t_end:
        write("busy", act, detail)
        time.sleep(min(REFRESH, max(0.1, t_end - time.time())))
write("idle")
print("■ Test run over — back to IDLE")
