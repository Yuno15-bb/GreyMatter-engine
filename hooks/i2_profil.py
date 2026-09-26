#!/usr/bin/env python3
"""i2_profil — a normative bench announces UNDER WHICH STATE it gave its verdict.

I-2, lot 1: DECLARE BEFORE FIXING. This module changes no score, no order,
no state. It makes visible what was silent.

WHAT IT DECLARES — what was OBSERVED during THIS run, never a static
manifest. The 2026-08-21 measurement showed that `golden_recall` does or does NOT read
`state/recall-utility.json` depending on how fresh the cache is: a dependency announced as
"always present" would be false one time in two.

TWO LEVELS, NOT TO BE CONFUSED
    external_read_observed   this file was opened. It is a FACT, not a proof.
    verdict_dependency_proven a counter-test showed that its content CHANGES the verdict.
    "File opened" ≠ "causal dependency". The second level is only filled from
    a measurement, never from an intuition.

repo_reproducible — defined before being used:
    "At HEAD, with the versioned dependencies and the environment the bench declares,
      another run can rebuild the same experiment profile with no hidden local state."
    It is NOT: the same score guaranteed · absolute determinism · absence of cache.
    An unversioned local dependency that influences the verdict → false.
    Instrumentation unable to conclude → "unknown". NEVER true by default.

A LIMIT, VISIBLE AND NOT HIDDEN
    `sys.addaudithook` only sees the current process. A bench that delegates to a
    subprocess does not trace its child's accesses: the profile then says so, and its
    `repo_reproducible` goes to "unknown".
"""
import atexit, json, os, sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME")
                         or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

BRUIT = ("/lib/python", "site-packages", "/usr/", "encodings", "__pycache__", ".pyc",
         "Library/Caches/com.apple.python", "/dev/")

# Dependencies whose causal effect on a verdict was MEASURED (R0-R3 matrix of
# 2026-08-21: without the file P@1 0.73 and q13 1st; with it, 0.60 and q13 out of the top 3).
CAUSALES_PROUVEES = {"state/recall-utility.json"}

_etat = {"lus": set(), "ecrits": set(), "nom": None, "notes": [], "sous_processus": False}


def _hook(evenement, args):
    if evenement == "subprocess.Popen" or evenement == "os.exec":
        _etat["sous_processus"] = True
        return
    if evenement != "open":
        return
    c, mode = args[0], args[1]
    if not isinstance(c, str) or not c.startswith("/") or any(x in c for x in BRUIT):
        return
    (_etat["ecrits"] if mode and any(x in str(mode) for x in "wax+") else _etat["lus"]).add(c)


def _externe(chemin):
    """Outside the tracked repository, or in state/: what HEAD does not contain."""
    if not chemin.startswith(BRAIN + "/"):
        return chemin.startswith(os.path.expanduser("~"))
    return os.path.relpath(chemin, BRAIN).startswith("state/")


def _rel(c):
    return os.path.relpath(c, BRAIN) if c.startswith(BRAIN + "/") else c


def demarrer(nom, ordre=(), mutations=(), notes=()):
    """To call at the top of a normative bench. `ordre` and `mutations` are KNOWN,
    measured weaknesses, which lot 1 makes visible without fixing them."""
    _etat.update(nom=nom, ordre=list(ordre), mutations=list(mutations), notes=list(notes))
    sys.addaudithook(_hook)
    atexit.register(emettre)


def emettre():
    if not _etat.get("nom") or _etat.get("emis"):
        return
    _etat["emis"] = True
    # `open()` is audited on the ATTEMPT, not on success: a missing file showed up
    # in the trace. Sabotage S1 showed it — without `recall-utility.json`, the profile still
    # declared it read, which is exactly the lie this lot must prevent.
    # So only what still exists at emission time is kept.
    lus = sorted(_rel(c) for c in _etat["lus"] if _externe(c) and os.path.exists(c))
    # The temporary files of an atomic write (`.tmp`, `.NNN.tmp`) are not
    # local state: they are the writing mechanism, and they are already gone.
    ecrits = sorted(_rel(c) for c in _etat["ecrits"]
                    if _externe(c) and not c.endswith(".tmp") and os.path.exists(c))
    prouvees = [c for c in lus if c in CAUSALES_PROUVEES]
    state_root = os.path.join(BRAIN, "state")

    if _etat["sous_processus"]:
        repro = "unknown"
    elif lus or ecrits or _etat.get("ordre"):
        repro = False
    else:
        repro = True

    statut = ("I2-E" if _etat.get("ordre") else
              "I2-C" if lus or ecrits else "I2-A")

    profil = {"instrument": _etat["nom"], "brain_root": BRAIN,
              "state_root": state_root if os.path.isdir(state_root) else None,
              "external_reads_observed": lus, "verdict_dependency_proven": prouvees,
              "external_writes": ecrits, "order_dependencies": _etat.get("ordre", []),
              "mutations": _etat.get("mutations", []),
              "repo_reproducible": repro, "status": statut,
              "trace_limite_sous_processus": _etat["sous_processus"]}

    # COMPACT output, and on STDERR — not stdout.
    # WHY stderr: `tests/racine_canonique.py` probes modules by READING their
    # standard output. The first version printed the profile on stdout and turned
    # that bench red, which no longer made sense of anything. A diagnostic must never
    # contaminate another instrument's data channel.
    def print(*a, **k):
        __builtins__["print"](*a, file=sys.stderr, **k) if isinstance(__builtins__, dict) \
            else __import__("builtins").print(*a, file=sys.stderr, **k)
    print("")
    if statut == "I2-A" and repro is True:
        print("  state profile: reproducible from the repository alone")
    else:
        print(f"  ⓘ state profile [{statut}] — reproducible from the repository alone: "
              f"{'yes' if repro is True else ('unknown' if repro == 'unknown' else 'NO')}")
        for c in prouvees:
            print(f"     · verdict depends on a local state (causality MEASURED): {c}")
        for c in lus:
            if c not in prouvees:
                print(f"     · local state read: {c}")
        for c in ecrits:
            print(f"     · local state WRITTEN by the measurement: {c}")
        for o in _etat.get("ordre", []):
            print(f"     · order dependency: {o}")
        for m in _etat.get("mutations", []):
            print(f"     · known mutation: {m}")
        if _etat["sous_processus"]:
            print("     · ⚠️ this bench delegates to a subprocess: the trace does NOT cover "
                  "its accesses")
    d = os.path.join(BRAIN, "state")
    if os.path.isdir(d):
        try:
            with open(os.path.join(d, "i2-profiles.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(profil, ensure_ascii=False) + "\n")
        except OSError:
            pass
