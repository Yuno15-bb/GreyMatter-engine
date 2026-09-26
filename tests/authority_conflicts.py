#!/usr/bin/env python3
"""Resolve conflicting authority for the synthetic ADR-0008 cases.

UNRESOLVED is a valid outcome: neither unknown nor agent inference gains
authority merely because a decision is requested. The case author specifies
whether a contradiction exists; this test measures resolution, not detection.
This benchmark is independent of the retrieval golden set.
"""
import argparse
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "authority_conflicts.json")

# Only kinds carrying normative authority.
sys.path.insert(0, ICI)
from provenance_invariants import kind_effectif  # noqa: E402
# Share the effective-kind logic with provenance invariants.

NORMATIFS = {"user_decision", "internal_experience"}

# Factual authority excludes user decisions. Unknown and inference have zero weight.
POIDS_FACTUEL = {"internal_experience": 4, "official_documentation": 3,
                 "external_document": 2, "web": 1, "agent_inference": 0, "unknown": 0}
# Normative authority governs working conventions.
POIDS_NORMATIF = {"user_decision": 4, "internal_experience": 2,
                  "official_documentation": 0, "external_document": 0,
                  "web": 0, "agent_inference": 0, "unknown": 0}


def s_applique(cote, question, mode_scope="strict"):
    """Whether this side may speak for the question's domain."""
    if mode_scope == "sans":                     # sabotage: ignore scope
        return True
    dom_c, dom_q = cote.get("domain"), question["domain"]
    if mode_scope == "large":                    # sabotage: all domains match
        return True
    if cote.get("scope") == "global":
        return question["nature"] == "normative"
    if dom_c == dom_q:
        return True
    return False


def resoudre(cas, mode_scope="strict"):
    if not cas.get("contradiction", True):
        return "COMPATIBLE"

    q = cas["question"]
    poids = POIDS_NORMATIF if q["nature"] == "normative" else POIDS_FACTUEL
    cotes = {}
    for nom in ("A", "B"):
        c = cas[nom]
        if not s_applique(c, q, mode_scope):
            continue                              # outside its domain
        k = kind_effectif(c)
        p = poids.get(k, 0)
        # Validation strengthens an existing authority but cannot create one.
        if c.get("validated") and p > 0:
            p += 1
        if c.get("superseded"):                   # superseded evidence has no weight
            p = 0
        cotes[nom] = p

    if not cotes:
        return "UNRESOLVED"                       # both sides out of scope
    if len(cotes) == 1:
        seul = next(iter(cotes))
        # A sole candidate still needs positive authority.
        return f"{seul}_WINS" if cotes[seul] > 0 else "UNRESOLVED"
    if cotes["A"] == cotes["B"]:
        return "UNRESOLVED"                       # tied authority
    gagnant = max(cotes, key=cotes.get)
    return f"{gagnant}_WINS" if cotes[gagnant] > 0 else "UNRESOLVED"


def mesurer(cas_tous, mode_scope="strict"):
    res = [(c, resoudre(c, mode_scope)) for c in cas_tous]
    n = len(res)
    justes = sum(1 for c, v in res if v == c["expected"])

    tranchables = [(c, v) for c, v in res if c["expected"] in ("A_WINS", "B_WINS")]
    sel = (sum(1 for c, v in tranchables if v == c["expected"]) / len(tranchables)
           if tranchables else 0.0)

    dits_unres = [(c, v) for c, v in res if v == "UNRESOLVED"]
    unres_prec = (sum(1 for c, _ in dits_unres if c["expected"] == "UNRESOLVED")
                  / len(dits_unres) if dits_unres else 1.0)

    # Did an out-of-scope side win?
    viol = 0
    for c, v in res:
        if v in ("A_WINS", "B_WINS"):
            cote = c[v[0]]
            if not s_applique(cote, c["question"], "strict"):
                viol += 1
    return {"res": res, "n": n, "justes": justes,
            "conflict_resolution_accuracy": justes / n,
            "authority_selection_accuracy": sel,
            "unresolved_precision": unres_prec,
            "scope_violation_rate": viol / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--scope-large", action="store_true", help="SABOTAGE: broaden scope")
    ap.add_argument("--sans-scope", action="store_true", help="SABOTAGE: ignore scope")
    a = ap.parse_args()
    mode = "large" if a.scope_large else ("sans" if a.sans_scope else "strict")

    cas_tous = json.load(open(FIXTURES, encoding="utf-8"))["cases"]
    m = mesurer(cas_tous, mode)

    titre = {"strict": "", "large": "  ⚠️ SABOTAGE: broadened scopes",
             "sans": "  ⚠️ SABOTAGE: ignored scope"}[mode]
    print(f"Authority conflicts — {m['n']} cases{titre}\n")
    for c, v in m["res"]:
        ok = v == c["expected"]
        print(f"  {'✅' if ok else '❌'} {c['id']:48} {c['expected']:11} → {v}")

    print(f"\n  conflict_resolution_accuracy  {m['conflict_resolution_accuracy']:.2f}")
    print(f"  authority_selection_accuracy  {m['authority_selection_accuracy']:.2f}")
    print(f"  unresolved_precision          {m['unresolved_precision']:.2f}"
          "   (was declining to decide correct?)")
    print(f"  scope_violation_rate          {m['scope_violation_rate']:.2f}"
          "   (did an out-of-scope side win?)")

    if a.check:
        if m["justes"] != m["n"]:
            print(f"\n❌ {m['n'] - m['justes']} divergent cases")
            return 1
        if m["scope_violation_rate"] > 0:
            print("\n❌ an out-of-scope side was declared the winner")
            return 1
        print("\n✅ resolution conforms to ADR-0008")
    return 0


if __name__ == "__main__":
    sys.exit(main())
