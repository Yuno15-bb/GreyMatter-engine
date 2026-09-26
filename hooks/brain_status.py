#!/usr/bin/env python3
"""
Shared status of the trunk — writes state/status.json, which the capsule reads.
Best effort: never fails, never blocks a hook.

Possible activities (each mapped to an animation in the capsule):
  distilling   ⚗️  extracting notes (distiller)
  gardening    🌱  tidying the whole tree (gardener)
  filing       📁  filing a note
  correcting   ✏️  correcting / masking a secret
  mapping      🗺️  updating the map
  committing   💾  git backup
  challenging  🔴  putting knowledge to the test (challenger)
  archiving    🍂  sorting the cold / archiving (archivist)
  synthesizing 🕸️  cross-cutting weave (synthesizer)
  auditing     🔧  auditing/repairing the machine (mechanic)
  architecting 🏗️  global cohesion / cross-domain bridges (architect)
  idle             at rest (a sleeping Tamagotchi)

CLI usage:  python3 brain_status.py <state> [activity] [detail]
"""
import json, os, time, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, legitimate
from brain_racine import brain_root

# I-1 (2026-08-21). A HUMAN diagnostic surface: a status tool that silently reads
# ~/.c-brain/trunk while being asked about another Brain makes a FALSE statement
# that looks authoritative. Measured on 2026-08-20: `brain doctor` run inside a
# worktree reported the author trunk's metrics, without the slightest sign.
STATE_DIR = os.path.join(brain_root(__file__), "state")
STATUS = os.path.join(STATE_DIR, "status.json")

# THE canonical freshness windows, read from the file the capsule reads too. Defaults are
# a fallback for a broken install, NOT a second definition: they must stay equal to the
# file's values, and a test holds them there.
FRESHNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status_freshness.json")
LIVENESS_STALE, ACTIVITY_STALE = 30, 120
try:
    _f = json.load(open(FRESHNESS, encoding="utf-8"))
    LIVENESS_STALE = float(_f.get("liveness_stale_seconds", LIVENESS_STALE))
    ACTIVITY_STALE = float(_f.get("activity_stale_seconds", ACTIVITY_STALE))
except Exception:
    pass


def _tmp_path():
    """A temp file THIS process owns alone.

    No sweeper is needed: `os.replace` consumes the file on the happy path, and the
    `except Exception: pass` path leaves at most one small orphan per crashed process.
    """
    return f"{STATUS}.{os.getpid()}.tmp"

def write_status(state, activity=None, detail=None, source=None):
    if source is None:
        source = "agent" if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1" else "you"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        # ⚠️ THE TEMP PATH MUST BE UNIQUE PER PROCESS. It used to be a single fixed
        # `status.json.tmp` shared by both writers of this file, and during a gardening
        # pass there are two BY DESIGN: the heartbeat calling `touch` every 5 s, and the
        # pipeline calling `busy <activity>` at each stage. `os.replace` is atomic for the
        # RENAME; it serialises nothing about the writes INTO the temp file. One writer
        # truncating with "w" while the other had written a longer payload leaves a splice
        # of both, and the reader gets `Extra data: line 1 column 120`. Observed on a real
        # install, 2026-08-16 (a tester):
        #     {"state": "busy", …, "ts": 1786874328.244719}79}
        # the trailing `79}` being the tail of the other writer's timestamp.
        # With one temp file per process, `os.replace` becomes the only contended
        # operation — which is the whole reason it was chosen.
        tmp = _tmp_path()
        with open(tmp, "w", encoding="utf-8") as f:
            # `ts` = LIVENESS ("still working"), refreshed by every heartbeat.
            # `activity_ts` = when this LABEL was set, and only whoever knows the activity
            # sets it. Writing an activity is also proof of life, so both move here — but
            # a heartbeat moves `ts` alone, which is the whole point of the split.
            now = time.time()
            json.dump({"state": state, "activity": activity, "detail": detail,
                       "source": source, "ts": now, "activity_ts": now}, f,
                      ensure_ascii=False)
        os.replace(tmp, STATUS)  # atomic write
    except Exception:
        pass

AGENTS_JOURNAL = os.path.join(STATE_DIR, "agents.jsonl")

def journal_agent(agent, phase, **champs):
    """One line per AGENT PASS, append-only — the trace that status.json cannot
    carry.

    Why this file exists (19/09/2026): status.json keeps only ONE global state,
    overwritten by the next pass; upkeep.json only counts totals; cost.jsonl
    carries the cost but NO agent name. With those three, there is no way to say
    what a given agent did and when. A per-agent panel (eight lights, one per
    mission) needs this line, otherwise all eight boxes show the same thing.

    `phase` is "start" or "end". Best-effort like the rest of the module: never
    fails, never blocks a hook.
    """
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        ligne = {"agent": agent, "phase": phase, "ts": time.time()}
        # THE SHIP ON TOP OF THE MISSION (20/09/2026). Since the missions were grouped
        # into ship families, `agent` names the mission; a per-ship display would otherwise
        # rebuild the mapping table on its own side, and the two would drift.
        try:
            from robots_permissions import FAMILLE
            if agent in FAMILLE:
                ligne["ship"] = FAMILLE[agent]
        except Exception:
            pass
        ligne.update({k: v for k, v in champs.items() if v is not None})
        with open(AGENTS_JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne["ts"]
    except Exception:
        return None


def touch_status():
    """HEARTBEAT: refreshes only `ts` on the current status, without touching
    state/activity/detail. Called in a loop by auto_maintain during long
    agent passes (a `claude -p` lasts minutes) → the capsule stays "busy"
    throughout, instead of flickering to idle when its freshness window expires.
    No-op if the file does not exist / is unreadable (best-effort, breaks nothing)."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            cur = json.load(f)
        cur["ts"] = time.time()
        tmp = _tmp_path()          # per-process, same reason as in write_status()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

def heartbeat():
    """SESSION LIVENESS: a tool just ran, so Claude is working. Refreshes `ts` and asserts
    `busy` — and deliberately does NOT touch `activity`, `detail` or `activity_ts`.

    THE DEFECT THIS EXISTS TO FIX, measured on a real machine on 2026-08-17: the status
    read `busy / correcting`, written 654 s earlier by the last note write, while the
    session had been working continuously ever since. No PostToolUse hook covered more
    than a slice of the tools (`Read` for one, `Write|Edit` for another), so Bash, Grep and
    Task — most of a working session — emitted nothing at all. The capsule read the stale
    timestamp as idle and hid the orb mid-work.

    WHY IT DOES NOT REFRESH THE ACTIVITY. Refreshing everything would have been one line
    less, and it would have turned an 11-minute-old label into a fresh-looking one: the orb
    would have announced `correcting` for as long as the session lasted. A heartbeat proves
    that work is happening, never what the work IS.

    WHY IT ASSERTS `busy` RATHER THAN PRESERVING THE STATE. A tool running IS the liveness
    signal. Left as a pure `touch`, a session opening on the `idle` written at the end of
    the previous one would keep a fresh timestamp on a dead state, and the orb would stay
    hidden through the whole session — the same silence, one level down.

    Distinct from `touch_status()`, which the SessionEnd pass uses to hold whatever state
    its own pulses set. Both refresh liveness; only this one claims the work is live.
    """
    try:
        try:
            with open(STATUS, "r", encoding="utf-8") as f:
                cur = json.load(f)
            if not isinstance(cur, dict):
                cur = {}
        except Exception:
            cur = {}          # no status yet (fresh install, 1st tool of the 1st session)
        cur["state"] = "busy"
        cur["ts"] = time.time()
        cur.setdefault("activity", None)
        cur.setdefault("activity_ts", 0)   # never named an activity → nothing to show
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _tmp_path()      # per-process, same reason as in write_status()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass


STATES = ("busy", "idle")   # the 1st argument is a STATE; the activity is the 2nd


def show_status():
    """SHOWS the current status. NEVER writes it.

    Exists since 2026-08-04. Before that: `brain status` called `brain_status.py show`,
    but this file was only a WRITER — so "show" was taken for a state and RECORDED in
    status.json. Result: the CLI's flagship command displayed nothing (empty output,
    exit 0, so the `||` fallbacks in the `brain` script never fired) and corrupted, in
    passing, the very state the capsule reads. Two faults in one line."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("(no status: state/status.json is missing)")
        return 0
    except Exception as e:
        print(f"(unreadable status: {e})")
        return 1
    age = time.time() - (s.get("ts") or 0)
    # The SAME window the capsule uses, from the same file. This used to read `age < 120`
    # against the capsule's 30 s: two answers to one question, and `brain status` could
    # call "fresh" a status the orb had already given up on.
    fresh = age < LIVENESS_STALE
    act_age = time.time() - (s.get("activity_ts") or 0)
    state = s.get("state") or "?"
    if state not in STATES:
        state += "  ⚠️ unknown state (status.json was corrupted by a faulty call)"
    print(f"state    : {state}")
    act = s.get("activity") or "—"
    if act != "—" and act_age >= ACTIVITY_STALE:
        act += f"   ⚠️ {int(act_age)} s old — the orb shows 'working' instead"
    print(f"activity : {act}")
    print(f"detail   : {s.get('detail') or '—'}")
    print(f"source   : {s.get('source') or '—'}")
    when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.get('ts') or 0))
    print(f"since    : {when}  ({int(age)} s — {'fresh' if fresh else 'STALE, the capsule reads it as idle'})")
    return 0



if __name__ == "__main__":
    a = sys.argv
    cmd = a[1] if len(a) > 1 else "idle"
    if cmd == "touch":
        touch_status()
    elif cmd == "heartbeat":
        heartbeat()
    elif cmd == "journal":
        # `journal <mission> <start|end> [key=value ...]` — the command-line door to
        # journal_agent, opened on 20/09/2026 for layer 1. auto_maintain launches the
        # distiller and the gardener through a shell, not through Python: without this
        # verb, the TWO most-used agents wrote no line at all, and any per-agent display
        # declared them "never seen".
        if len(a) < 4:
            print("Usage: brain_status.py journal <mission> <start|end> [key=value ...]",
                  file=sys.stderr)
            sys.exit(2)
        champs = {}
        for kv in a[4:]:
            k, _, v = kv.partition("=")
            try:
                champs[k] = float(v) if v.replace(".", "", 1).isdigit() else v
            except Exception:
                champs[k] = v
        journal_agent(a[2], a[3], **champs)
    elif cmd in ("show", "status"):
        sys.exit(show_status())
    elif cmd in STATES:
        write_status(cmd, a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else None)
    else:
        # REFUSE rather than record: any word at all was accepted as a state, so a typo
        # silently poisoned the very file the capsule reads.
        print(f"unknown state: {cmd!r} — expected {' | '.join(STATES)} (or touch / show).",
              file=sys.stderr)
        print("Usage: brain_status.py <busy|idle> [activity] [detail]  ·  ... touch  ·  ... show",
              file=sys.stderr)
        sys.exit(2)
