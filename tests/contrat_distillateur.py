#!/usr/bin/env python3
"""
contrat_distillateur.py — ce que le distillateur DOIT écrire, rendu exécutable.

LE PROBLÈME QU'IL RÉSOUT. Le distillateur est un prompt (agents/narcissus.md, section « MISSION — distillateur »), donc on
ne peut pas le tester comme une fonction. Mais son CONTRAT, lui, est déterministe : pour
une source donnée, il n'y a qu'un bloc `provenance:` correct. Ce fichier écrit ce bloc, et
vérifie qu'il passe le contrôleur d'invariants. Le prompt peut alors pointer une référence
exécutable au lieu de décrire un format en prose — et une prose ne rougit jamais.

LA SITUATION AU 2026-08-16, à connaître avant de s'inquiéter. Le dépôt refuse désormais
une fiche neuve sans provenance (pre-commit). Le distillateur produisait l'ancien format.
**Si un hook refuse une distillation, ce n'est pas le hook qui est cassé : c'est le
producteur qui est en retard.** Ce fichier est là pour que le retard se rattrape sans
deviner le format.

LE DISTILLATEUR NE DÉCIDE PAS DE L'AUTORITÉ. Il transporte ce qu'il sait déjà de la
source. Les quatre cas ci-dessous couvrent tout ce qu'il a le droit de produire.

Lancer :
  python3 tests/contrat_distillateur.py
  python3 tests/contrat_distillateur.py --check
  python3 tests/contrat_distillateur.py --sans-provenance   # SABOTAGE : l'ancien format
  python3 tests/contrat_distillateur.py --sans-extrait      # SABOTAGE : E1 non tenu

E1 — L'EXTRAIT, DEPUIS LE 2026-09-18. Le distillateur ne se contente plus de nommer sa
source : il en recopie la phrase, mot pour mot, dans `provenance.extrait`. La raison est
mécanique, pas morale — une reformulation ne se vérifie pas, un extrait se recherche au
caractère près. Seul `kind: unknown` en est dispensé : une origine perdue n'a rien à
citer, et lui réclamer un extrait la pousserait à en inventer un. Le refus au moment du
commit est prouvé à part, par tests/extrait_obligatoire.py.
"""
import argparse
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from provenance_invariants import controler  # noqa: E402


def bloc_provenance(cas, ecrire=True, extrait=True):
    """Le bloc `provenance:` / `authority:` canonique pour une source donnée.

    `ecrire=False` est le SABOTAGE : on produit l'ancien format, sans provenance —
    exactement ce que fait le distillateur d'avant. Le contrôle doit le refuser.
    """
    if not ecrire:
        return ""

    kind = cas["kind"]
    ref = cas.get("ref", "")
    scope = cas.get("scope", "repository")
    lignes = ["provenance:", f"  kind: {kind}"]

    if kind != "unknown":
        # L'observable est OBLIGATOIRE dès qu'on prétend connaître l'origine. Sans lui,
        # la provenance est une affirmation, pas une trace.
        lignes.append(f'  ref: "{ref}"')
        lignes.append(f"  captured_at: {cas['captured_at']}")
        # E1 : la phrase exacte de la source. `extrait=False` est le SABOTAGE — le
        # distillateur qui nomme sa source sans jamais la citer.
        if extrait:
            lignes.append(f'  extrait: "{cas["extrait"]}"')
    if cas.get("derived_from"):
        lignes.append(f"  derived_from: [{cas['derived_from']}]")

    # validated : JAMAIS une décision du distillateur. Il le pose uniquement quand la
    # source elle-même porte sa preuve — une citation directe, ou un rejeu déterministe.
    validee = (
        (kind == "user_decision" and bool(ref))
        or (kind == "internal_experience" and bool(cas.get("commande")))
    )
    lignes += ["authority:",
               f"  validated: {'true' if validee else 'false'}",
               f"  scope: {scope}",
               f"  confidence: {cas.get('confidence', 'medium')}"]

    if validee and kind == "internal_experience":
        lignes += ["validation:", "  method: deterministic_replay",
                   f'  command: "{cas["commande"]}"', "  result: pass",
                   f"  at: {cas['captured_at']}"]
    return "\n".join(lignes)


# Les quatre cas, et RIEN d'autre. Un cinquième cas voudrait dire que le distillateur
# s'est mis à juger.
CAS = [
    {"nom": "source web", "kind": "web", "ref": "https://exemple.test/billet",
     "extrait": "le billet dit : « le cache reste chaud 30 s »",
     "captured_at": "2026-08-16", "derived_from": "source-issue-du-web",
     "confidence": "low", "attendu_validated": False},
    {"nom": "décision de l'auteur", "kind": "user_decision",
     "ref": "l'auteur, 2026-08-16 : « on garde BM25 »", "captured_at": "2026-08-16",
     "extrait": "on garde BM25",
     "scope": "project", "confidence": "high", "attendu_validated": True},
    {"nom": "expérience interne rejouable", "kind": "internal_experience",
     "ref": "tests/golden_recall.py", "captured_at": "2026-08-16",
     "extrait": "P@1 0.67 · P@3 0.87 · MRR 0.77",
     "commande": "python3 tests/golden_recall.py --check",
     "confidence": "high", "attendu_validated": True},
    {"nom": "origine inconnue", "kind": "unknown", "captured_at": "2026-08-16",
     "confidence": "low", "attendu_validated": False},
    # Une expérience interne SANS rejeu : le distillateur ne peut pas la valider. C'est le
    # cas qui distingue « j'ai observé » de « je peux le prouver à quelqu'un d'autre ».
    {"nom": "expérience interne sans rejeu", "kind": "internal_experience",
     "ref": "observé en session", "captured_at": "2026-08-16",
     "extrait": "le hook a refusé le commit sans rien afficher",
     "confidence": "medium", "attendu_validated": False},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sans-provenance", action="store_true",
                    help="SABOTAGE : le distillateur d'avant, qui n'écrit rien")
    ap.add_argument("--sans-extrait", action="store_true",
                    help="SABOTAGE : il nomme sa source mais ne la cite jamais (E1)")
    a = ap.parse_args()
    ecrire = not a.sans_provenance
    extrait = not a.sans_extrait

    titre = ""
    if not ecrire:
        titre = "   ⚠️ SABOTAGE : ancien format, sans provenance"
    elif not extrait:
        titre = "   ⚠️ SABOTAGE : source nommée, jamais citée"
    print(f"Contrat du distillateur — {len(CAS)} sources{titre}\n")
    echecs = 0
    for c in CAS:
        bloc = bloc_provenance(c, ecrire, extrait)
        fautes = controler(bloc) if bloc else ["aucun bloc provenance produit"]
        # E1 : tout ce qui n'est pas `unknown` revendique une source, donc la cite.
        if bloc and c["kind"] != "unknown" and 'extrait: "' not in bloc:
            fautes.append("E1 : source nommée sans extrait recopié")
        validee = "validated: true" in bloc
        if validee is not c["attendu_validated"]:
            fautes.append(f"validated={validee}, attendu {c['attendu_validated']}")
        echecs += bool(fautes)
        print(f"  {'✅' if not fautes else '❌'} {c['nom']:32} "
              f"{c['kind']:22} validated={str(validee).lower()}")
        for f in fautes:
            print(f"        ↳ {f}")

    print(f"\n  {len(CAS) - echecs}/{len(CAS)} sources produisent un bloc conforme")
    if a.check and echecs:
        print("\n❌ le distillateur ne produirait pas un bloc acceptable")
        return 1
    if a.check:
        print("\n✅ contrat tenu — le producteur est aligné sur le garde-fou")
    return 0


if __name__ == "__main__":
    sys.exit(main())
