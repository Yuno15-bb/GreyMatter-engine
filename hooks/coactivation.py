#!/usr/bin/env python3
"""coactivation — the brain's WORKING MEMORY, made computable.

One layer maps by MEANING. This layer is the brain CONSUMING its own graph:
we look at what was actually activated TOGETHER during sessions (not the declared links).

Sources : state/recall_log.jsonl ({ts,sid,path,score}) + state/read_log.jsonl ({ts,sid,path}).
  • CO-ACTIVATION: two notes surfaced/read in the SAME session = linked by usage (not a declared [[link]]).
  • HEAT: how recently a note was activated (exponential decay) → what is "hot" right now.

Output: state/coactivation.json = { heat:{path:0..1}, edges:[[a,b,w],…],
                                     live:{at,window_min,max,items:[[path,ts],…]} }.
`live` = LIVE activity (sliding window of a few minutes over notes actually READ),
not to be confused with `heat` (recency over days).
Pure stdlib, deterministic, reads ONLY the notes that are planet nodes (distilled) —
le corpus froid et les sessions/ sont exclus (ils ne sont pas sur la carte). Sort toujours 0.
"""
import os, sys, json, time, math
from collections import defaultdict

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
RECALL = os.path.join(BRAIN, "state", "recall_log.jsonl")
READ = os.path.join(BRAIN, "state", "read_log.jsonl")
GRAPH = os.path.join(BRAIN, "planet", "graph.json")
OUT = os.path.join(BRAIN, "state", "coactivation.json")

TAU_DAYS = 10.0          # approximate half-life of heat (recency)
MAX_SESSION = 25         # a session "touching" too many notes says nothing about pairs → ignored
MIN_EDGE = 2.0           # a pair must co-occur with at least this cumulative weight to count
TOP_EDGES = 120          # keep the strongest usage links (readability)

# LIVE ACTIVITY (blue ring on the planet) — a SLIDING measure, not a whole session.
# Bug history: "active" used to mean "surfaced by recall, at any point during the current
# session". A 25 h session → 68 notes out of 218 lit up (31 % of the planet):
# the ring stopped signalling anything. Two fixes:
#   - only a REAL Read counts (read_log). A note merely OFFERED by recall is not activated.
#   - sliding window from now, capped — not the span of a session.
LIVE_WINDOW_MIN = 10     # minutes: beyond that a note is no longer "live" (the visualizer fades it too)
LIVE_MAX = 12            # hard cap: beyond that the ring is noise again


def node_paths():
    """The notes that are planet nodes (file → id). Everything else is ignored."""
    try:
        g = json.load(open(GRAPH, encoding="utf-8"))
        return {n["file"]: n["id"] for n in g["nodes"]}
    except Exception:
        return {}


def read_events(path, keep):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("path") in keep and e.get("sid"):
            out.append((e["sid"], e["path"], float(e.get("ts", 0))))
    return out


def compute():
    keep = node_paths()
    events = read_events(RECALL, keep) + read_events(READ, keep)
    now = time.time()
    tau = TAU_DAYS * 86400.0

    # HEAT: sum of activations weighted by recency (exponential decay)
    heat = defaultdict(float)
    last = defaultdict(float)
    for sid, path, ts in events:
        age = max(0.0, now - ts)
        heat[path] += math.exp(-age / tau)
        last[path] = max(last[path], ts)
    hmax = max(heat.values()) if heat else 1.0
    heat_n = {p: round(v / hmax, 4) for p, v in heat.items()}

    # CO-ACTIVATION: pairs of notes seen in the same session, weighted by the session's recency
    by_sid = defaultdict(set)
    sid_ts = defaultdict(float)
    for sid, path, ts in events:
        by_sid[sid].add(path)
        sid_ts[sid] = max(sid_ts[sid], ts)
    pair = defaultdict(float)
    for sid, paths in by_sid.items():
        ps = sorted(paths)
        if len(ps) < 2 or len(ps) > MAX_SESSION:
            continue
        w = 0.5 + 0.5 * math.exp(-(now - sid_ts[sid]) / tau)   # recent sessions weigh more
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                pair[(ps[i], ps[j])] += w
    edges = [[keep[a], keep[b], round(w, 3)] for (a, b), w in pair.items() if w >= MIN_EDGE]
    edges.sort(key=lambda e: -e[2])
    edges = edges[:TOP_EDGES]

    # LIVE ACTIVITY: notes ACTUALLY read within the last LIVE_WINDOW_MIN minutes.
    # `at` + `window_min` are published so the visualizer can FADE the ring out on its own,
    # continuously, without waiting for a graph regeneration (no ring left lit by inertia).
    cutoff = now - LIVE_WINDOW_MIN * 60
    last_read = defaultdict(float)
    for _sid, path, ts in read_events(READ, keep):
        if ts >= cutoff:
            last_read[path] = max(last_read[path], ts)
    live_items = sorted(last_read.items(), key=lambda kv: -kv[1])[:LIVE_MAX]
    live = {"at": int(now), "window_min": LIVE_WINDOW_MIN, "max": LIVE_MAX,
            "items": [[p, int(ts)] for p, ts in live_items]}

    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": {"events": len(events), "hot_notes": len(heat_n),
                       "usage_links": len(edges), "live_notes": len(live_items)},
            "heat": heat_n, "edges": edges, "live": live,
            "heat_id": {keep[p]: v for p, v in heat_n.items()}}


def main():
    data = compute()
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    if sys.stdout.isatty() or "--show" in sys.argv:
        c = data["counts"]
        print(f"⚡ co-activation: {c['events']} activations · {c['hot_notes']} hot notes · "
              f"{c['usage_links']} usage links · {c['live_notes']} live (≤{LIVE_WINDOW_MIN} min)")
        top = sorted(data["heat"].items(), key=lambda kv: -kv[1])[:8]
        print("  🔥 hottest:")
        for p, v in top:
            print(f"     {v:.2f}  {os.path.basename(p)[:-3]}")
        print("  🔗 strong usage links (co-activated, not necessarily linked with [[…]]):")
        for a, b, w in data["edges"][:8]:
            print(f"     {w:.1f}  {a}  ⟷  {b}")


if __name__ == "__main__":
    main()
    sys.exit(0)
