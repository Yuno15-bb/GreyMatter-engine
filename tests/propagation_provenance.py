
"""Track provenance through successive transformations."""
import argparse
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "fixtures_propagation.json")
sys.path.insert(0, ICI)
from provenance_invariants import KINDS, kind_effectif  



def propager(source, transformation, propager_vraiment=True):
    """Track provenance through successive transformations."""
    if not propager_vraiment:
        return {"id": f"{source['id']}+{transformation}", "kind": "internal_experience",
                "ref": "rewritten and filed in the trunk", "validated": False}
    sortie = {
        "id": f"{source['id']}+{transformation}",
        "kind": kind_effectif(source),
        "validated": False,               
        "derived_from": source["id"],     
        "transformation": transformation,
    }
    if source.get("sources"):
        
        
        sortie["sources"] = [dict(s) for s in source["sources"]]
    if source.get("ref"):
        sortie["ref"] = source["ref"]
    return sortie


def remonter_origine(maillon, par_id):
    """Track provenance through successive transformations."""
    vu = set()
    while maillon.get("derived_from") and maillon["derived_from"] not in vu:
        vu.add(maillon["derived_from"])
        maillon = par_id[maillon["derived_from"]]
    if maillon.get("ref"):
        return maillon["ref"]
    for s in maillon.get("sources") or ():          
        if s.get("role") == "basis":
            return s.get("ref")
    return None


def jouer(chaine, propager_vraiment=True):
    racine = chaine["root"]
    par_id = {racine["id"]: racine}
    courant = racine
    for t in chaine["steps"]:
        courant = propager(courant, t, propager_vraiment)
        par_id[courant["id"]] = courant
    profondeur = 0
    m = courant
    while m.get("derived_from"):
        profondeur += 1
        m = par_id[m["derived_from"]]
    return courant, remonter_origine(courant, par_id), profondeur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sans-propagation", action="store_true",
                    help="SABOTAGE: the transformation discards all provenance")
    a = ap.parse_args()
    vrai = not a.sans_propagation

    chaines = json.load(open(FIXTURES, encoding="utf-8"))["chains"]
    titre = "" if vrai else "   ⚠️ SABOTAGE: provenance propagation disabled"
    print(f"Provenance propagation — {len(chaines)} chains{titre}\n")

    echecs = 0
    for idx, ch in enumerate(chaines, 1):
        final, origine, prof = jouer(ch, vrai)
        att = ch["expected"]
        fautes = []
        if final["kind"] != att["kind_final"]:
            fautes.append(f"kind {final['kind']} ≠ {att['kind_final']}")
        if final["validated"] is not att["validated_final"]:
            fautes.append(f"validated {final['validated']}")
        if "external_origin" in att and origine != att["external_origin"]:
            fautes.append(f"source reference was lost: {origine!r}")
        if prof != att["depth"]:
            fautes.append(f"chain depth {prof} ≠ {att['depth']}")
        if att.get("preserved_sources") is not None:
            n = len(final.get("sources") or [])
            if n != att["preserved_sources"]:
                fautes.append(f"{n} source(s) preserved; expected {att['preserved_sources']}")
        if att.get("web_still_present"):
            if not any(s["kind"] == "web" for s in final.get("sources") or []):
                fautes.append("the web illustration disappeared from provenance")
        if final["kind"] not in KINDS:
            fautes.append(f"kind outside vocabulary: {final['kind']}")

        echecs += bool(fautes)
        step_names = {"distillation": "distillation", "synthesis": "synthesis",
                      "rewrite": "rewrite"}
        steps = " → ".join(step_names.get(step, step) for step in ch["steps"])
        print(f"  {'✅' if not fautes else '❌'} Chain {idx:<48} {steps}")
        if fautes:
            for f in fautes:
                print(f"        ↳ {f}")

    print(f"\n  {len(chaines) - echecs}/{len(chaines)} chains conform")
    if a.check and echecs:
        print("\n❌ provenance was not preserved through the transformations")
        return 1
    if a.check:
        print("\n✅ I7 holds across the transformations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
