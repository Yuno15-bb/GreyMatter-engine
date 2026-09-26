#!/usr/bin/env python3
"""Unsaved-repositories sensor — the work that exists ONLY on this machine.

Why it exists (2026-08-22). A client project: last commit on 13/08, then 70 modified
files and 6,306 insertions left in the working tree for NINE DAYS, about 20 of them
never tracked — so with no earlier version to recover at all. Found by chance while
reading the repository for a scoping job. The same day: 8 commits never pushed on a
second repository, a branch with no destination on a third, and a fourth with no
remote at all.

The existing total-backup setup already covered the NON-git Desktop, and its note
flagged the blind spot "a .git without a remote". The neighbouring case was missing,
and it is the more common one: a repository that HAS a remote but whose work never
went there. The setup relied on a rule ("commit + push as usual") — a rule is not a sensor.

THE OBSERVABLE IS THE REAL GIT STATE ON DISK: `git status --porcelain`, `rev-list @{u}..HEAD`,
`git remote`. Never an intention, never a script's log. A 100% local measurement: no
`fetch`, so no network and no wait at session start.

  python3 capteur_depots.py            # readable report
  python3 capteur_depots.py --hook     # block at session start (silent if everything is green)
  python3 capteur_depots.py --json     # raw state
  python3 capteur_depots.py --notify   # + a macOS notification when red (for launchd)

  REPOS_ROOTS=/path/a:/path/b          # overrides the scope — to SABOTAGE on
                                       # fixtures without touching the real repositories.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
# Overridable: a sensor you cannot break on purpose has never proved it turns red.
RACINES = [Path(p) for p in os.environ.get("REPOS_ROOTS", str(HOME / "Desktop")).split(":") if p]
PROFONDEUR = int(os.environ.get("REPOS_DEPTH", "3"))

# Work left unsaved on the same day is NORMAL (a session in progress).
# What is abnormal is that it lasts. The measured incident lasted 9 days.
ORANGE_JOURS = 1
ROUGE_JOURS = 3

ICONE = {"red": "🔴", "orange": "🟠", "green": "🟢"}


def _git(depot, *args):
    try:
        r = subprocess.run(["git", "-C", str(depot), *args],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def trouver_depots():
    vus, depots = set(), []
    for racine in RACINES:
        if not racine.is_dir():
            continue
        try:
            out = subprocess.run(
                ["find", str(racine), "-maxdepth", str(PROFONDEUR), "-name", ".git", "-type", "d"],
                capture_output=True, text=True, timeout=60).stdout
        except Exception:
            continue
        for ligne in out.splitlines():
            d = Path(ligne).parent.resolve()
            if d not in vus:
                vus.add(d)
                depots.append(d)
    return sorted(depots)


def examiner(depot):
    """One finding per repository. The level comes from measured FACTS, not from an opinion."""
    nom = depot.name
    remotes = _git(depot, "remote") or ""
    sale = len([l for l in (_git(depot, "status", "--porcelain") or "").splitlines() if l])
    dernier = _git(depot, "log", "-1", "--format=%ct")
    age = (time.time() - int(dernier)) / 86400 if dernier and dernier.isdigit() else None

    # 1. No destination: the work exists nowhere else. Structural, never tolerated.
    if not remotes:
        return dict(repo=nom, path=str(depot), level="red",
                    msg="no remote repository — this work exists only on this machine",
                    observable="git remote → (empty)", dirty=sale, ahead=0, age_d=age)

    # 2. A branch with no destination: its commits go nowhere, and `ahead` is unreadable.
    upstream = _git(depot, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    branche = _git(depot, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    if upstream is None:
        return dict(repo=nom, path=str(depot), level="red",
                    msg=f"branch '{branche}' has no destination — its commits go nowhere",
                    observable="git rev-parse @{u} → failed", dirty=sale, ahead=0, age_d=age)

    ahead_s = _git(depot, "rev-list", "--count", "@{u}..HEAD")
    ahead = int(ahead_s) if ahead_s and ahead_s.isdigit() else 0

    # 3. Work exists that is not on the remote. Its severity comes from its DURATION.
    if sale or ahead:
        if age is None:
            niveau = "red"
        elif age >= ROUGE_JOURS:
            niveau = "red"
        elif age >= ORANGE_JOURS:
            niveau = "orange"
        else:
            niveau = "green"         # same-day session: normal
        bouts = []
        if sale:
            bouts.append(f"{sale} unsaved file(s)")
        if ahead:
            bouts.append(f"{ahead} commit(s) never pushed")
        suffixe = f", last save {age:.1f} d ago" if age is not None else ""
        return dict(repo=nom, path=str(depot), level=niveau,
                    msg=" and ".join(bouts) + suffixe,
                    observable=f"git status --porcelain → {sale} · rev-list @{{u}}..HEAD → {ahead}",
                    dirty=sale, ahead=ahead, age_d=age)

    return dict(repo=nom, path=str(depot), level="green", msg="up to date on its remote",
                observable="git status --porcelain → 0 · rev-list @{u}..HEAD → 0",
                dirty=0, ahead=0, age_d=age)


def mesurer():
    constats = [examiner(d) for d in trouver_depots()]
    return {
        "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "findings": constats,
        "reds": [c for c in constats if c["level"] == "red"],
        "oranges": [c for c in constats if c["level"] == "orange"],
    }


def notifier(rouges):
    """An alert nobody sees is useless — that is exactly the defect being fixed."""
    if not rouges:
        return
    txt = " · ".join(c["repo"] for c in rouges[:4])
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{txt}" with title "Unsaved repositories" sound name "Basso"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def main():
    args = sys.argv[1:]
    etat = mesurer()
    if "--hook" in args:
        if etat["reds"]:
            print("<unsaved-repos> Work that exists only on this machine:")
            for c in etat["reds"]:
                print(f"- {c['repo']}: {c['msg']}")
            print("</unsaved-repos>")
        return 0
    if "--notify" in args:
        notifier(etat["reds"])
    if "--json" in args:
        print(json.dumps(etat, indent=2, ensure_ascii=False))
        return 0
    print(f"🗄  Unsaved repositories — {etat['when']}")
    for c in etat["findings"]:
        print(f"   {ICONE[c['level']]} {c['repo']:<28} {c['msg']}")
        print(f"      observable: {c['observable']}")
    n = len(etat["reds"])
    print("   ✅ nothing red" if not n else f"   ⚠ {n} repository(ies) red")
    return 0


if __name__ == "__main__":
    sys.exit(main())
