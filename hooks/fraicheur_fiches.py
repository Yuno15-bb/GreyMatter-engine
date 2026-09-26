#!/usr/bin/env python3
"""fraicheur_fiches — closes the time → freshness loop.

THE PROBLEM. Nothing invalidates a stale note. The `challenger` can contest a fact, but
it is an agent you launch by hand: no note carries any trace of the last time somebody
checked it is still true. So an error written one day can stay true forever in the eyes
of the system.

WHAT IT DOES. Computes, for each note, the date of its last VALIDATION:
  • the frontmatter field `last_validated: YYYY-MM-DD` when it exists;
  • otherwise the date of the last COMMIT that touched the file;
  • only as a very last resort, the file's mtime.

⚠️ WHY NOT MTIME FIRST. That was the plan, and it is wrong here: the machine restore of
2026-07-22 rewrote every file in the trunk. Measured, the oldest file on disk was **20
days** old while notes date back to May — mtime claimed everything was fresh and the
review queue came out empty. Git history, on the other hand, survives a restore.

Past THRESHOLD_DAYS without validation, the note enters a **low-priority** review queue:
`state/to-revalidate.json`. It is a list you consult, never an alert that blocks — the
goal is not to turn maintenance into a chore.

WHY THE FIELD IS NOT WRITTEN IN BULK. The "put the mtime into all 312 notes" migration
would produce a huge diff for zero new information: the mtime is already on disk. So the
field only appears the day somebody actually validates the note.

WHO WRITES THE FIELD. The **gardener**, never the challenger: the challenger records its
verdicts in `state/`, it touches no note (separation of powers, cf.
[[separation-pouvoirs-agent-teams]]). The gardener reads `state/reviews.json` and stamps.

Usage:
  fraicheur_fiches.py           recompute state/to-revalidate.json
  fraicheur_fiches.py --report  recompute and print the queue
"""
import os, re, sys, json, time, glob, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
OUTPUT = os.path.join(BRAIN, "state", "to-revalidate.json")
FOLDERS = ("projects", "lessons", "meta", "life")

# Tunable from the environment — otherwise the 90-day threshold makes the mechanism
# UNVERIFIABLE while the trunk is young: it returns 0 notes, and a computation that never
# returns anything proves nothing. `THRESHOLD_DAYS=30 fraicheur_fiches.py --report` must
# list notes; if it stays empty, it is the computation that is broken.
THRESHOLD_DAYS = int(os.environ.get("THRESHOLD_DAYS", "90"))   # ~3 months, cf. gardening rules §5
FM_VALID = re.compile(r"^\s*last_validated:\s*\"?(\d{4}-\d{2}-\d{2})\"?\s*$", re.M)
FM_NAME = re.compile(r"^\s*name:\s*[\"']?([^\"'\n]+)[\"']?\s*$", re.M)


def _frontmatter(text):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def git_dates():
    """{relative path: timestamp of the last commit}. A single walk of the history —
    314 separate `git log` calls would take seconds on every hook."""
    try:
        output = subprocess.run(
            ["git", "-C", BRAIN, "log", "--name-only", "--format=@%at", "--no-renames"],
            capture_output=True, text=True, timeout=25).stdout
    except Exception:
        return {}
    dates, ts = {}, None
    for line in output.splitlines():
        if line.startswith("@"):
            try: ts = int(line[1:])
            except ValueError: ts = None
        elif line and ts and line.endswith(".md"):
            dates.setdefault(line, ts)       # first seen = most recent (log is reverse-chronological)
    return dates


def analyse():
    now = time.time()
    git = git_dates()
    notes = []
    for folder in FOLDERS:
        for path in glob.glob(os.path.join(BRAIN, folder, "**", "*.md"), recursive=True):
            rel = os.path.relpath(path, BRAIN)
            try:
                text = open(path, encoding="utf-8").read()
                mtime = os.path.getmtime(path)
            except Exception:
                continue
            fm = _frontmatter(text)
            name = FM_NAME.search(fm)
            m = FM_VALID.search(fm)
            if m:
                try:
                    ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
                    source = "validated"
                except Exception:
                    ts, source = git.get(rel, mtime), "commit"   # unreadable date → fall back on git
            elif rel in git:
                ts, source = git[rel], "commit"
            else:
                ts, source = mtime, "file"
            notes.append({
                "path": rel,
                "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
                "days": int((now - ts) / 86400),
                "source": source,
            })
    return notes


def main():
    notes = analyse()
    to_revalidate = sorted((n for n in notes if n["days"] > THRESHOLD_DAYS),
                           key=lambda n: -n["days"])
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    tmp = f"{OUTPUT}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"threshold_days": THRESHOLD_DAYS, "computed_on": time.strftime("%Y-%m-%d"),
                   "total_notes": len(notes), "notes": to_revalidate},
                  f, ensure_ascii=False)
    os.replace(tmp, OUTPUT)

    if "--report" not in sys.argv:
        return 0
    never = sum(1 for n in notes if n["source"] != "validated")
    print(f"{len(notes)} notes · {never} have never been explicitly validated")
    print(f"past {THRESHOLD_DAYS} days: {len(to_revalidate)} notes in the review queue "
          f"(low priority, no alert)")
    for n in to_revalidate[:12]:
        print(f"  {n['days']:4d} d  ({n['source']})  {n['path']}")
    if len(to_revalidate) > 12:
        print(f"  … and {len(to_revalidate) - 12} more — see {os.path.relpath(OUTPUT, BRAIN)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
