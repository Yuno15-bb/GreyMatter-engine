#!/usr/bin/env python3
"""etat_projets — the status note of ALL projects, rebuilt on every pass.

WHY THIS FILE EXISTS (2026-08-13). The author asked for "the rundown of everything I
still have to do". The first one I produced recited July "left to do" items that had
long been settled, because it was copied from the notes instead of being measured. A
hand-written status note rots in three days; this one REGENERATES.

THE SPLIT, AND IT IS THE HEART OF THE THING:

  1. MEASURED NOW — the state of the git repositories (last commit, unsaved work,
     unpushed commits, no off-machine backup). True to the second,
     never copied, never stale.

  2. SAID BY THE NOTES — the resume points, read from `projects/**`. This is
     declarative: it can be stale, and the note SAYS so instead of hiding it.
     Every line carries the age of its source.

  3. WAITING ON THE OWNER — `projects/owner-decisions.json`, kept by hand by Claude when
     a decision belongs to the owner. Every entry carries its date: a decision that has
     been dragging for three weeks shows, instead of melting into the list.

Makes NO LLM call: it is a mechanical round, like the machinist. Free,
so it can run twice a day without ever arguing with the quota.

⚠️ WHY MEASUREMENT AND ANNOUNCEMENT ARE SEPARATE (2026-08-13, found by looking at the output).
Plugged naively into launchd, this script ran without error and returned "5 repositories"
instead of 22: macOS DENIES a launchd service access to ~/Desktop (TCC), where most
working repositories live. Exit code 0, note written, 17 projects vanished
silently — the exact defect of `brain status`, six weeks apart.

So:
  • the MEASUREMENT runs where access exists — in a Claude session (hook), which inherits
    the terminal's permissions;
  • the 8 am and 7 pm ANNOUNCEMENT reads the last measurement and STATES ITS AGE, instead of
    fabricating a false one;
  • a safeguard refuses to overwrite a complete measurement with a truncated one.

For the round to measure by itself: give Full Disk Access to /usr/bin/python3
(System Settings › Privacy). Not required — the announcement stays accurate without it.

Usage:
    python3 hooks/etat_projets.py              # measure (if possible) + note + announcement
    python3 hooks/etat_projets.py --announce   # announce from the last measurement, writes nothing
    python3 hooks/etat_projets.py --notify     # + macOS notification (launchd morning/evening)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
HOME = os.path.expanduser("~")
FICHE = os.path.join(BRAIN, "projects", "project-status.md")
# In projects/ and not state/: state/ is ignored by git, the list of decisions
# owed by the author would not survive a `git clone`. It is knowledge, not machine state.
DECISIONS = os.path.join(BRAIN, "projects", "owner-decisions.json")
CACHE = os.path.join(BRAIN, "state", "project-status.json")

# Below this fraction of the largest number of repositories ever seen, the measurement is
# held to be TRUNCATED (access denied) and overwrites nothing. 0.6 lets through the
# legitimate disappearance of a few repositories, never the vanishing of a whole folder.
SEUIL_AMPUTATION = 0.6

EXCLUS = ("/Library/", "/node_modules/", "/.venv", "/.codex/", "/_archive/", "/.Trash/")

# A repository that has not moved for longer than this is no longer "paused", it sleeps.
JOURS_ACTIF = 7
JOURS_PAUSE = 30


def _git(repo: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def depots() -> list[dict]:
    """All git repositories on the machine, with their real state."""
    try:
        r = subprocess.run(
            ["find", HOME, "-maxdepth", "7", "-name", ".git", "-not", "-path", "*/Library/*"],
            capture_output=True, text=True, timeout=120,
        )
        chemins = r.stdout.splitlines()
    except Exception:
        return []

    out = []
    aujourdhui = dt.date.today()
    for g in chemins:
        if any(x in g for x in EXCLUS):
            continue
        repo = g[: -len("/.git")]
        iso = _git(repo, "log", "-1", "--date=short", "--pretty=%ad")
        if not iso:
            continue
        try:
            jours = (aujourdhui - dt.date.fromisoformat(iso)).days
        except ValueError:
            jours = 999
        sale = len([l for l in _git(repo, "status", "--porcelain").splitlines() if l.strip()])
        non_pousse = _git(repo, "rev-list", "--count", "@{u}..HEAD")
        out.append({
            "name": os.path.basename(repo),
            "path": repo.replace(HOME, "~"),
            "last": iso,
            "days": jours,
            "dirty": sale,
            "unpushed": int(non_pousse) if non_pousse.isdigit() else None,
            "remote": bool(_git(repo, "remote")),
            "subject": _git(repo, "log", "-1", "--pretty=%s")[:90],
        })
    out.sort(key=lambda d: d["days"])
    return out


def reprises() -> list[dict]:
    """Resume points declared in the project notes (declarative, not measured)."""
    sys.path.insert(0, os.path.join(BRAIN, "hooks"))
    try:
        import brain_anticipate
        items = brain_anticipate.collect()
    except Exception:
        return []
    maintenant = dt.datetime.now().timestamp()
    for it in items:
        it["days"] = int((maintenant - it["mtime"]) // 86400)
    return items


def decisions() -> list[dict]:
    try:
        with open(DECISIONS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    aujourdhui = dt.date.today()
    for d in data:
        try:
            d["days"] = (aujourdhui - dt.date.fromisoformat(d.get("since", ""))).days
        except ValueError:
            d["days"] = None
    return data


def alertes(reps: list[dict]) -> list[str]:
    """What deserves an action, by order of severity. Empty = nothing is wrong."""
    a = []
    for d in reps:
        if not d["remote"]:
            a.append(f"**{d['name']}** has no off-machine backup (no remote repository)")
    for d in reps:
        if d["dirty"]:
            a.append(f"**{d['name']}**: {d['dirty']} working file(s) never committed "
                     f"(last commit {d['days']} d ago)")
    for d in reps:
        if d["unpushed"]:
            a.append(f"**{d['name']}**: {d['unpushed']} commit(s) never pushed")
    return a


def rendre(reps, reprs, decs) -> str:
    ts = dt.datetime.now()
    actifs = [d for d in reps if d["days"] <= JOURS_ACTIF]
    pause = [d for d in reps if JOURS_ACTIF < d["days"] <= JOURS_PAUSE]
    dorment = [d for d in reps if d["days"] > JOURS_PAUSE]
    al = alertes(reps)

    L = []
    L.append("---")
    L.append("name: project-status")
    L.append('description: "Status of ALL projects, regenerated automatically twice a day '
             "(hooks/etat_projets.py). A MEASURED part (git repositories) + a DECLARED part "
             '(resume points from the notes, possibly stale) + decisions waiting on the owner."')
    L.append("topic: client-projects")   # otherwise regeneration would erase the topic (map, 2026-09-23)
    L.append("metadata:")
    L.append("  type: project")
    L.append("  node_type: memory")
    L.append("---")
    L.append("")
    L.append("# Project status")
    L.append("")
    L.append(f"*Regenerated on {ts.strftime('%Y-%m-%d at %H:%M')}. Do not edit by hand: "
             "the next pass overwrites everything.*")
    L.append("")

    L.append("## En clair")   # i18n-ok — section name read by graph_export.EN_CLAIR
    L.append("")
    L.append("This page is the dashboard of ALL the author's projects, rebuilt by itself "
             "twice a day. Nobody writes it by hand: the next pass replaces "
             "anything typed into it.")
    L.append("")
    L.append("It separates two things that must not be confused. What is **measured** comes "
             "straight from the code repositories on the machine — work never saved, "
             "saves never sent anywhere else, a project with no copy off the Mac. "
             "What is **declared** comes from the notes I write, and is worth what the note is worth.")
    L.append("")
    L.append("It is read for one question only: is some work at risk of disappearing, "
             "and is a decision waiting on the author?")
    L.append("")

    L.append("## ⚠️ What needs an action")
    L.append("")
    if al:
        for x in al:
            L.append(f"- {x}")
    else:
        L.append("Nothing. Everything is committed, pushed, backed up off the machine.")
    L.append("")

    L.append("## 🙋 Waiting on a decision from the author")
    L.append("")
    if decs:
        for d in decs:
            age = f" — open for **{d['days']} d**" if d.get("days") is not None else ""
            L.append(f"- **{d.get('project', '?')}**: {d.get('text', '')}{age}")
    else:
        L.append("Nothing waiting.")
    L.append("")

    L.append("## 📊 Projects, by real activity")
    L.append("")
    L.append("Measured just now on the git repositories — this part cannot be stale.")
    L.append("")
    for titre, groupe in (("Active (≤ 7 days)", actifs),
                          ("Paused (8 to 30 days)", pause),
                          ("Dormant (> 30 days)", dorment)):
        L.append(f"### {titre} — {len(groupe)}")
        L.append("")
        if not groupe:
            L.append("*(none)*")
            L.append("")
            continue
        L.append("| Project | Last commit | Last subject |")
        L.append("|---|---|---|")
        for d in groupe:
            L.append(f"| `{d['name']}` | {d['last']} ({d['days']} d) | {d['subject']} |")
        L.append("")

    L.append("## 🧭 What the notes say to pick up")
    L.append("")
    L.append("⚠️ **Declarative, not measured.** These lines are written in the notes; some "
             "may have been settled since. The age says how far to distrust them — "
             "beyond 14 days, re-prove before announcing.")
    L.append("")
    for it in reprs[:12]:
        vieux = " 🕸️" if it["days"] > 14 else ""
        L.append(f"- **{it['name']}** ({it['days']} d{vieux}) — {it['reprise']}")
    L.append("")
    return "\n".join(L) + "\n"


def lire_cache() -> dict:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ecrire_cache(reps: list[dict], plafond: int) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"measured_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "repos": reps, "repos_max": plafond}, f, ensure_ascii=False, indent=1)


def amputee(reps: list[dict], cache: dict) -> bool:
    """Has the measurement lost access to part of the disk?

    Judged against the historical CEILING, not the previous measurement: otherwise two
    truncated passes in a row would lower the reference until the failure is validated.
    """
    plafond = int(cache.get("repos_max") or 0)
    return plafond > 0 and len(reps) < SEUIL_AMPUTATION * plafond


def annonce(reps, reprs, decs, age=None) -> str:
    actifs = [d for d in reps if d["days"] <= JOURS_ACTIF]
    al = alertes(reps)
    moment = "morning" if dt.datetime.now().hour < 14 else "evening"
    vu = "" if age is None else f" — measured {age}"
    lignes = [f"🌳 Project status ({moment}) — {len(reps)} repositories, "
              f"{len(actifs)} active this week{vu}."]
    if al:
        lignes.append(f"⚠️  {len(al)} thing(s) to settle: {al[0]}")
    else:
        lignes.append("✅ Nothing to settle: everything is committed, pushed, backed up.")
    if decs:
        vieille = max(decs, key=lambda d: d.get("days") or 0)
        lignes.append(f"🙋 {len(decs)} decision(s) waiting — the oldest: "
                      f"{vieille.get('project')} ({vieille.get('days')} d)")
    if reprs:
        lignes.append(f"🧭 First to pick up: {reprs[0]['name']}")
    lignes.append(f"📄 {FICHE.replace(HOME, '~')}")
    return "\n".join(lignes)


ANNONCE = os.path.join(BRAIN, "state", "round-to-announce.json")


def notifier(texte: str) -> None:
    """Announces the round through TWO channels, one of which is verifiable.

    On 2026-08-14, the user: "a summary this morning didn't launch". The service HAD run
    (`runs = 4, last exit code = 0`, a "morning" line in the log) and `osascript` had returned 0.
    But no banner ever appeared: `osascript` launched from a launchd agent posts
    its notifications on behalf of Script Editor, which is not even registered in the
    Notification Center (0 occurrences in `com.apple.ncprefs` after an attempt). In other words the
    channel fails silently AND returns 0 — a new instance of "an exit code is never
    the observable", applied this time to the announcement channel itself.

    So the banner is kept as best-effort, but above all a MARKER is dropped that the
    next Claude Code session will display: the only place where we are certain the user
    is looking is where they work.
    """
    titre = "C Brain — project status"
    corps = texte.split("\n")[1] if "\n" in texte else texte
    corps = corps.replace('"', "'").replace("**", "")
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{corps}" with title "{titre}"'],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass

    # The channel that CAN be verified: a file, read at the start of the next session.
    try:
        os.makedirs(os.path.dirname(ANNONCE), exist_ok=True)
        with open(ANNONCE, "w", encoding="utf-8") as f:
            json.dump({"text": texte, "written_at": dt.datetime.now().isoformat(),
                       "announced_at": None}, f, ensure_ascii=False, indent=2)
    except Exception as e:                      # never fatal: the round has already written its note
        print(f"⚠️  announcement marker not written: {e}")


def _age(iso: str) -> str:
    try:
        delta = dt.datetime.now() - dt.datetime.fromisoformat(iso)
    except Exception:
        return "at an unknown date"
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        return "less than an hour ago"
    if h < 24:
        return f"{h} h ago"
    return f"{h // 24} d ago"


def main() -> int:
    cache = lire_cache()
    reprs, decs = reprises(), decisions()
    reps = depots()

    degrade = amputee(reps, cache)
    if degrade or "--announce" in sys.argv:
        # We overwrite NOTHING: we speak of the last complete measurement, stating its age.
        reps = cache.get("repos", reps)
        texte = annonce(reps, reprs, decs, age=_age(cache.get("measured_at", "")))
        if degrade:
            texte += ("\n⚠️  current measurement ignored: disk access denied to this service "
                      "(the Desktop was not readable). The note was not touched.")
    else:
        ecrire_cache(reps, max(len(reps), int(cache.get("repos_max") or 0)))
        os.makedirs(os.path.dirname(FICHE), exist_ok=True)
        with open(FICHE, "w", encoding="utf-8") as f:
            f.write(rendre(reps, reprs, decs))
        texte = annonce(reps, reprs, decs)

    print(texte)
    if "--notify" in sys.argv:
        notifier(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
