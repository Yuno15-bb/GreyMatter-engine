
"""Check provenance declarations on notes in the selected tree."""
import argparse
import glob
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))



BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.dirname(ICI))
sys.path.insert(0, ICI)
from provenance_invariants import controler, kind_effectif, _lire_bloc  

ZONES = ("projects", "lessons", "meta", "life")


def frontmatter(chemin):
    try:
        raw = open(chemin, encoding="utf-8").read()
    except OSError:
        return ""
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def fiches():
    out = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if rel.split(os.sep)[0] in ZONES:
            out[os.path.basename(rel)[:-3]] = (rel, frontmatter(p))
    return out


def ajoutees():
    """Check provenance declarations on notes in the selected tree."""
    try:
        s = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
                           cwd=BRAIN, capture_output=True, text=True).stdout
    except Exception:
        return set()
    return {l for l in s.split("\n")
            if l.endswith(".md") and l.split("/")[0] in ZONES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--nouvelles", action="store_true",
                    help="also require provenance on notes added in the current commit")
    a = ap.parse_args()

    toutes = fiches()
    neuves = ajoutees()
    kinds = {n: kind_effectif(_lire_bloc(fm, "provenance") or {})
             for n, (_, fm) in toutes.items()}

    declarent, fautives, manquantes, sans_extrait = [], [], [], []
    for nom, (rel, fm) in sorted(toutes.items()):
        prov = _lire_bloc(fm, "provenance")
        if not prov:
            if a.nouvelles and rel in neuves:
                manquantes.append(rel)
            continue
        declarent.append(rel)
        
        
        parent = None
        dfrom = prov.get("derived_from")
        if dfrom:
            cible = dfrom[0] if isinstance(dfrom, list) else dfrom
            parent = kinds.get(cible)
        fautes = controler(fm, parent)
        if fautes:
            fautives.append((rel, fautes))
        
        
        if (a.nouvelles and rel in neuves and prov.get("kind") != "unknown"
                and not str(prov.get("extrait") or "").strip()):
            sans_extrait.append(rel)

    print(f"Provenance in the trunk — {len(toutes)} notes\n")
    print(f"  provenance declared: {len(declarent)}")
    print(f"  no provenance (unknown by default, unchanged): {len(toutes) - len(declarent)}")
    if neuves:
        print(f"  added in this commit: {len(neuves)}")

    if fautives:
        print(f"\n❌ {len(fautives)} note(s) declare invalid provenance:")
        for rel, f in fautives[:10]:
            print(f"     {rel}\n        ↳ {f[0]}")
    if manquantes:
        print(f"\n❌ {len(manquantes)} added note(s) have no provenance:")
        for rel in manquantes[:10]:
            print(f"     {rel}")
        print("\n   A new note declares its origin. If it is unknown,")
        print("   write `provenance:\\n  kind: unknown`. Never guess.")

    if sans_extrait:
        print(f"\n❌ {len(sans_extrait)} added note(s) have no excerpt (E1):")
        for rel in sans_extrait[:10]:
            print(f"     {rel}")
        print("\n   A note that names its source must copy the sentence verbatim:")
        print("   `provenance:\\n  excerpt: \"the exact sentence\"`. If you cannot quote it,")
        print("   Do not write the claim—or declare `kind: unknown`.")

    if a.check and (fautives or manquantes or sans_extrait):
        return 1
    if a.check:
        print("\n✅ no declared provenance is invalid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
