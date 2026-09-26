#!/usr/bin/env python3
"""capsule_liveness.py — does the orb know that Claude is still working?

THE INVARIANT, in two halves that must not be confused:

    LIVENESS  "is Claude still working?"  -> `ts`, refreshed by EVERY tool call
    ACTIVITY  "what is it doing?"         -> `activity` + `activity_ts`, set only
                                             by whoever actually knows

THE FAILURE THIS EXISTS TO PREVENT. Measured on a real machine on 2026-08-17, mid-session:

    state: busy      activity: correcting      ts: 654 s old

The session had not stopped for a second. The status was written once, by the last note
write, and nothing refreshed it afterwards: no PostToolUse hook covered more than a slice
of the tools (`Read` for one, `Write|Edit` for another), so Bash, Grep and Task — most of a
working session — emitted nothing. The capsule read the stale timestamp as idle and hid the
orb while the work was going on.

WHY THE ACTIVITY IS CHECKED SEPARATELY. The cheap fix — refresh the whole status on every
tool — trades a hidden orb for a lying one: an 11-minute-old `correcting` would look fresh
for the rest of the session. So the heartbeat must be seen NOT refreshing the label.

WHY THE WINDOWS ARE CHECKED AT ALL. "Is the status fresh?" used to have three answers:
30 s in capsule/main.js, 30 s again in capsule/orbe.html, 120 s in brain_status.py. Three
copies of one question, already 4x apart. They now come from `hooks/status_freshness.json`,
and this test is what keeps a literal from creeping back.

Run:
  python3 tests/capsule_liveness.py
  python3 tests/capsule_liveness.py --check
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATUS_CLI = os.path.join(ROOT, "hooks", "brain_status.py")
FRESHNESS = os.path.join(ROOT, "hooks", "status_freshness.json")
HOOKS_JSON = os.path.join(ROOT, "hooks", "hooks.json")
MAIN_JS = os.path.join(ROOT, "capsule", "main.js")
ORBE = os.path.join(ROOT, "capsule", "orbe.html")

# The real 2026-08-17 measurement, replayed as the fixture's stale age.
REAL_STALE_AGE = 654


def run(sandbox, *args):
    """Run the REAL brain_status.py against a sandboxed HOME.

    HOME is the right lever here and not a shortcut: the script derives its state
    directory through `expanduser`, so a sandboxed HOME really does move the file it
    writes — while `status_freshness.json`, resolved from `__file__`, stays the repo's.
    """
    subprocess.run([sys.executable, STATUS_CLI, *args], check=False, timeout=60,
                   capture_output=True, env=dict(os.environ, HOME=sandbox))


def read_status(sandbox):
    p = os.path.join(sandbox, ".c-brain", "trunk", "state", "status.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_status_file(sandbox, payload):
    p = os.path.join(sandbox, ".c-brain", "trunk", "state", "status.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def main():
    check = "--check" in sys.argv
    trouble = []

    windows = json.load(open(FRESHNESS, encoding="utf-8"))
    live_w = windows["liveness_stale_seconds"]
    act_w = windows["activity_stale_seconds"]
    print(f"Capsule liveness — windows: liveness {live_w}s · activity {act_w}s\n")

    with tempfile.TemporaryDirectory() as sandbox:
        # ---------- 1. tools are running -> the orb must read BUSY ----------
        run(sandbox, "busy", "correcting", "a note")
        s = read_status(sandbox)
        if s.get("activity_ts") is None:
            trouble.append("write_status does not stamp `activity_ts`: the label carries "
                           "no age, so a stale activity cannot be told from a current one")

        # Replay the real defect: the status is 654 s old, the session never stopped.
        aged = dict(s, ts=time.time() - REAL_STALE_AGE,
                    activity_ts=time.time() - REAL_STALE_AGE)
        write_status_file(sandbox, aged)

        before = read_status(sandbox)
        orb_before = (time.time() - before["ts"]) < live_w
        print(f"  the 654 s case, before the heartbeat   orb sees busy: {orb_before}")
        if orb_before:
            trouble.append("the fixture does not reproduce the defect: a 654 s old status "
                           "is still read as live, so this test cannot see the bug it "
                           "exists for")

        # ---------- 2. a tool runs -> the heartbeat revives LIVENESS ONLY ----------
        run(sandbox, "heartbeat")
        after = read_status(sandbox)
        live_age = time.time() - after["ts"]
        act_age = time.time() - (after.get("activity_ts") or 0)
        orb_after = live_age < live_w
        label_fresh = act_age < act_w

        print(f"  after one heartbeat                    orb sees busy: {orb_after}")
        print(f"  liveness age                           {live_age:.1f}s")
        print(f"  activity age                           {act_age:.0f}s  "
              f"(label shown: {'activity' if label_fresh else 'working'})")

        if not orb_after:
            trouble.append("a tool ran and the orb still reads idle: the heartbeat does "
                           "not refresh liveness — this is the 654 s defect itself")
        if after.get("state") != "busy":
            trouble.append(f"the heartbeat left state={after.get('state')!r}: a session "
                           "opening on the previous session's `idle` would keep a fresh "
                           "timestamp on a dead state, and the orb would never come back")
        if act_age < REAL_STALE_AGE - 60:
            trouble.append(f"the heartbeat refreshed the activity label (age {act_age:.0f}s "
                           f"instead of ~{REAL_STALE_AGE}s): an 11-minute-old `correcting` "
                           "would be presented as what Claude is doing right now")
        if label_fresh:
            trouble.append("a stale activity is still offered as the current one: the orb "
                           "must fall back to `working` rather than name it")

        # ---------- 3. tools stop -> liveness must decay to IDLE ----------
        stopped = dict(after, ts=time.time() - live_w - 5)
        write_status_file(sandbox, stopped)
        s3 = read_status(sandbox)
        still_busy = (time.time() - s3["ts"]) < live_w
        print(f"  no tool for {live_w + 5:.0f}s                     orb sees busy: {still_busy}")
        if still_busy:
            trouble.append("liveness never decays: the orb would stay lit after the work "
                           "has stopped, which is the opposite blindness")

    # ---------- 4. one canonical window, no rivals ----------
    print()
    cfg = json.load(open(FRESHNESS, encoding="utf-8"))
    src_py = open(STATUS_CLI, encoding="utf-8").read()
    src_js = open(MAIN_JS, encoding="utf-8").read()
    src_orbe = open(ORBE, encoding="utf-8").read()

    for who, src, needle in (("brain_status.py", src_py, "status_freshness.json"),
                             ("capsule/main.js", src_js, "status_freshness.json"),
                             ("capsule/orbe.html", src_orbe, "status_freshness.json")):
        ok = needle in src
        print(f"  {who:20} reads the canonical file  {'yes' if ok else 'NO'}")
        if not ok:
            trouble.append(f"{who} does not read {needle}: it decides freshness on its "
                           "own again, which is exactly the 30 s / 30 s / 120 s split")

    # The Python fallbacks are a broken-install net, not a second opinion.
    m = re.search(r"LIVENESS_STALE,\s*ACTIVITY_STALE\s*=\s*(\d+),\s*(\d+)", src_py)
    if m and (int(m.group(1)) != cfg["liveness_stale_seconds"]
              or int(m.group(2)) != cfg["activity_stale_seconds"]):
        trouble.append(f"brain_status.py's fallbacks ({m.group(1)}, {m.group(2)}) disagree "
                       f"with status_freshness.json ({cfg['liveness_stale_seconds']}, "
                       f"{cfg['activity_stale_seconds']}): a broken install would answer "
                       "differently from a healthy one")

    # ---------- 5. the consumer really gates the label ----------
    # `st.activity_ts`, not the bare word: the file EXPLAINS the split in prose, so
    # matching `activity_ts` anywhere stayed green when a sabotage stripped the logic and
    # left the comment behind. The accessor only appears where the field is really read.
    gates = "st.activity_ts" in src_orbe
    print(f"  {'capsule/orbe.html':20} gates the label on activity_ts  "
          f"{'yes' if gates else 'NO'}")
    if not gates:
        trouble.append("the orb never reads `activity_ts`: it shows whatever label is in "
                       "the file, however old — the heartbeat would make the lie look fresh")

    # The SUBTITLE is half of the same claim. Gating only the label was the real defect the
    # first fix shipped: on screen the orb read `WORKING…` — honest — over a line still
    # reading `Organizing the tree`. The precise half is the one that misleads.
    detail_gated = re.search(r"actFraiche\s*\?\s*surQuoi\(st\.detail\)", src_orbe)
    print(f"  {'capsule/orbe.html':20} gates the SUBTITLE too  "
          f"{'yes' if detail_gated else 'NO'}")
    if not detail_gated:
        trouble.append("the subtitle is not gated on activity_ts: the label falls back to "
                       "`working` while the line under it still names the stale operation")

    # ---------- 6. the producer is wired to EVERY tool ----------
    hooks = json.load(open(HOOKS_JSON, encoding="utf-8"))
    post = (hooks.get("hooks") or hooks).get("PostToolUse", [])
    wired = [e for e in post
             if e.get("matcher") == "*"
             and any("heartbeat" in h.get("command", "") for h in e.get("hooks", []))]
    print(f"  {'hooks.json':20} heartbeat on every tool  {'yes' if wired else 'NO'}")
    if not wired:
        trouble.append("no PostToolUse entry matching `*` runs the heartbeat: a session "
                       "spent in Bash or Grep emits no sign of life, and the orb hides "
                       "mid-work — the 2026-08-17 defect, restored")

    if trouble:
        print("\n❌ the capsule cannot tell working from finished:")
        for t in trouble:
            print(f"     {t}")
        return 1

    print("\n✅ liveness and activity are separate, and both reach the orb")
    if not check:
        print("   (a tool revives the orb; a stale label stops being named)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
