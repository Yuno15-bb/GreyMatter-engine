#!/usr/bin/env python3
"""
carte_compaction.py — D5.3 : une projection compacte est-elle FIDÈLE ?

Une compaction n'est acceptable que si l'on n'a rien perdu de structurant. Les axes ci-dessous
sont vérifiés pour chaque candidat, et chacun a son sabotage — un garde qui ne peut pas rougir
n'autorise rien.

AXES STRUCTURELS (doivent être identiques au témoin C0) :
  membres · sections · rangs · niveaux · titres de section · sections VIDES · références

AXE ÉDITORIAL (la règle qui autorise à raccourcir) :
  toute annotation modifiée doit être un PRÉFIXE de l'originale — on coupe, on ne reformule
  jamais — et le texte retiré doit être retrouvable dans la fiche.

  python3 tests/carte_compaction.py
"""
import hashlib, json, os, re, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "tools", "cartes"))
from regle_entree import lire
import compacter as C

BUDGET = 20000
MEM = open(os.path.join(BRAIN, "MEMORY.md"), encoding="utf-8").read()
BASE = [x for x in lire(MEM) if x["classe"] == "entree"]
BASE_I = {x["fiche"]: x for x in BASE}
titres = lambda t: [l.lstrip("#").strip() for l in t.split("\n") if l.startswith("#")]
TITRES0 = titres(MEM)


def controler(texte):
    """retourne {axe: (ok, détail)} — comparé au témoin C0."""
    e = [x for x in lire(texte) if x["classe"] == "entree"]
    i = {x["fiche"]: x for x in e}
    r = {}
    r["membres"] = (set(i) == set(BASE_I), f"{len(i)} vs {len(BASE_I)}")
    r["sections"] = (all(i[k]["section"] == BASE_I[k]["section"] for k in i if k in BASE_I),
                     "section par entrée")
    r["rangs"] = (all(i[k]["rang"] == BASE_I[k]["rang"] for k in i if k in BASE_I), "rang par entrée")
    r["niveaux"] = (all(i[k]["niveau"] == BASE_I[k]["niveau"] for k in i if k in BASE_I), "étoiles")
    t = titres(texte)
    r["titres_sections"] = (t == TITRES0, f"{len(t)} vs {len(TITRES0)}")
    vides0 = [x for x in TITRES0 if not any(y["section"] == x for y in BASE)]
    vides1 = [x for x in t if not any(y["section"] == x for y in e)]
    r["sections_vides"] = (vides0 == vides1, f"{len(vides1)} vs {len(vides0)} conservées")
    # axe éditorial : préfixe strict + retrouvabilité
    mauvais = [k for k in i if k in BASE_I and i[k]["annotation"] != BASE_I[k]["annotation"]
               and not BASE_I[k]["annotation"].startswith(i[k]["annotation"])]
    r["annotations_prefixe"] = (not mauvais, f"{len(mauvais)} reformulée(s)")
    perdus = [k for k in i if k in BASE_I and i[k]["annotation"] != BASE_I[k]["annotation"]
              and not C.retrouvable(BASE_I[k]["annotation"][len(i[k]["annotation"]):], k)]
    r["texte_retire_retrouvable"] = (not perdus, f"{len(perdus)} non retrouvable(s)")
    # une annotation entièrement effacée est techniquement un « préfixe vide » : l'axe préfixe
    # ne peut pas l'attraper. Il lui faut son propre garde — trouvé par le sabotage n°4.
    effacees = [k for k in i if k in BASE_I and BASE_I[k]["annotation"] and not i[k]["annotation"]]
    r["annotations_effacees"] = (not effacees, f"{len(effacees)} effacée(s)")
    r["budget"] = (len(texte.encode()) <= BUDGET, f"{len(texte.encode())} / {BUDGET}")
    return r


print(f"{'candidat':10}" + "".join(f"{a[:11]:>13}" for a in
      ("membres","sections","rangs","niveaux","titres","vides","préfixe","effacées","retrouv.","budget")))
print("-" * 127)
empreintes = {}
for niv in ("C0", "C1", "C2", "C3", "C3p"):
    p = os.path.join(BRAIN, "tools", "cartes", "candidats", f"MEMORY.{niv}.md")
    if not os.path.exists(p): continue
    t = open(p, encoding="utf-8").read()
    empreintes[niv] = hashlib.sha256(t.encode()).hexdigest()
    r = controler(t)
    print(f"{niv:10}" + "".join(f"{'✅' if r[a][0] else '⛔':>13}" for a in
          ("membres","sections","rangs","niveaux","titres_sections","sections_vides",
           "annotations_prefixe","annotations_effacees","texte_retire_retrouvable","budget")))

# ── LES 8 SABOTAGES, sur le meilleur candidat ───────────────────────────────
print("\n── SABOTAGES sur C3 (en mémoire ; aucun fichier écrit) ──\n")
t3 = open(os.path.join(BRAIN, "tools", "cartes", "candidats", "MEMORY.C3.md"), encoding="utf-8").read()
victime = BASE[3]["fiche"]
S = []
S.append(("1 entrée supprimée",        t3.replace(f"[[{victime}]]", "", 1), "membres"))
sec = next(l for l in t3.split("\n") if l.startswith("###"))
S.append(("2 section renommée",        t3.replace(sec, sec + " MODIFIÉE", 1), "titres_sections"))
etoile = next((x for x in BASE if x["niveau"] == 2), BASE[0])
S.append(("3 niveau changé",           t3.replace(f"⭐⭐ [[{etoile['fiche']}]]", f"[[{etoile['fiche']}]]", 1), "niveaux"))
ann = next(x for x in BASE if x["annotation"])
S.append(("4 annotation entièrement perdue",
          t3.replace(f"[[{ann['fiche']}]] ({ann['annotation']})", f"[[{ann['fiche']}]]", 1),
          "annotations_effacees"))
a2 = [x for x in BASE if x["annotation"]][1]
S.append(("5 annotation reformulée",   t3.replace(f"({ann['annotation'][:30]}", "(texte entierement different", 1), "annotations_prefixe"))
vide = next((x for x in TITRES0 if not any(y["section"] == x for y in BASE)), None)
ligne_vide = next((l for l in t3.split("\n") if l.startswith("#") and l.lstrip("#").strip() == vide), None) if vide else None
S.append(("6 section vide supprimée",
          t3.replace(ligne_vide + "\n", "", 1) if ligne_vide else t3, "sections_vides"))
S.append(("7 budget dépassé",          t3 + "x" * (BUDGET + 1 - len(t3.encode())), "budget"))
for nom, texte, axe in S:
    r = controler(texte)
    rouge = not r[axe][0]
    print(f"   {nom:32} axe « {axe:24} » {'✅ ROUGIT' if rouge else '⛔ RESTE VERT'}   {r[axe][1]}")

# 8 — modification manuelle après génération
p3 = os.path.join(BRAIN, "tools", "cartes", "candidats", "MEMORY.C3.md")
apres = hashlib.sha256((open(p3, encoding="utf-8").read() + " ").encode()).hexdigest()
print(f"   {'8 retouche après génération':32} empreinte {empreintes['C3'][:12]}… → {apres[:12]}…  "
      f"{'✅ ROUGIT' if apres != empreintes['C3'] else '⛔'}")
print(f"\n   → l'empreinte de chaque candidat est enregistrée : une projection retouchée à la main")
print(f"     n'est plus celle qui a été mesurée, et ça se voit.")
json.dump(empreintes, open(os.path.join(BRAIN, "tools", "cartes", "candidats", "empreintes.json"), "w"), indent=1)
