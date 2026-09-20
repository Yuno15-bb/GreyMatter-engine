#!/usr/bin/env python3
"""BANC — la surface d'écriture des relations proposées (tools/relecture/poser.py).

Il exerce le VRAI outil, dans un TRONC JETABLE désigné par BRAIN_HOME : aucune fiche du
Brain n'est lue ni touchée, donc le banc ne peut pas rougir parce qu'une autre session a
écrit pendant qu'il tournait — défaut mesuré le 17/09 sur le témoin du chantier rappel.

CE QU'IL PROTÈGE, ET POURQUOI CHAQUE CAS EXISTE
    L'outil écrit dans le frontmatter de vraies fiches et sait défaire un lot entier. Les
    deux opérations sont destructrices par nature : une pose qui déforme l'en-tête, ou un
    retrait qui emporte une relation écrite à la main, coûtent plus cher que l'absence de
    l'outil. Les sabotages sont donc des fautes RÉELLES du protocole, pas des variantes.

    S1  `lie_a` est refusé à la porte — la consigne du juge l'interdit (mesuré le 18/09 :
        62 % des propositions, ~975 liens projetés contre 575 dans tout le graphe).
    S2  une fiche modifiée entre le jugement et la pose rend la proposition PÉRIMÉE, et
        la fiche n'est pas touchée : le juge a lu un texte qui n'existe plus.
    S3  une cible inexistante est refusée — 4 relations du tronc pointaient déjà dans le
        vide le 17/09.
    S4  une relation qui existait AVANT le lot est épargnée par le retrait. C'est le cas
        qui rend un retrait utilisable : sinon défaire une passe efface du travail humain.
    S5  une proposition sans raison ou sans emplacement est refusée — ce sont les deux
        champs qui empêchent de rebaptiser un voisinage en dépendance.

L'INVARIANT (A1-A3) EST L'AUTRE MOITIÉ DE LA PREUVE. Poser puis retirer sur une fiche que
personne n'a touchée rend le fichier OCTET POUR OCTET identique, sur les trois formes de
frontmatter qui vivent dans le tronc : sans bloc `relations:`, avec la forme courte
`base_sur: [a]`, avec la forme à tirets. Un outil qui « range » l'en-tête au passage a un
effet de bord, et un effet de bord dans un outil de retrait le rend inutilisable.

Lancer : python3 tests/relations_proposees.py [--check]   (rc != 0 si un contrôle rate)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTIL = os.path.join(RACINE, "tools", "relecture", "poser.py")

FICHE_SANS = """---
name: fiche-a
description: "la fiche qu'on relit"
---

Corps de la fiche A, qui ne doit jamais bouger.
"""
FICHE_COURTE = """---
name: fiche-b
description: "déjà une relation, forme courte"
relations:
  base_sur: [cible-un]
---

Corps de B.
"""
FICHE_TIRETS = """---
name: fiche-c
description: "déjà une relation, forme à tirets"
relations:
  precise:
    - cible-un
---

Corps de C.
"""
CIBLE = """---
name: cible-un
description: "la candidate"
---

Corps de la cible.
"""
CIBLE2 = """---
name: cible-deux
description: "la seconde candidate"
---

Corps.
"""


def tronc():
    d = tempfile.mkdtemp(prefix="relations-proposees-")
    for z in ("lessons", "state", "hooks", "tools/relecture"):
        os.makedirs(os.path.join(d, z), exist_ok=True)
    shutil.copy(os.path.join(RACINE, "hooks", "graph_export.py"), os.path.join(d, "hooks"))
    for nom, txt in (("fiche-a", FICHE_SANS), ("fiche-b", FICHE_COURTE),
                     ("fiche-c", FICHE_TIRETS), ("cible-un", CIBLE), ("cible-deux", CIBLE2)):
        open(os.path.join(d, "lessons", f"{nom}.md"), "w", encoding="utf-8").write(txt)
    return d


def file_attente(d, fiches):
    """La file que `a_relire.py` produit — on en pose une à la main, sans lancer le calcul."""
    a = [{"path": f"lessons/{n}.md", "name": n, "ecrite_le": 0, "deja_citees": [],
          "candidates": [{"name": "cible-un", "path": "lessons/cible-un.md",
                          "desc": "la candidate", "sim": 0.3},
                         {"name": "cible-deux", "path": "lessons/cible-deux.md",
                          "desc": "la seconde", "sim": 0.2}]} for n in fiches]
    json.dump({"a_relire": a}, open(os.path.join(d, "state", "relecture.json"), "w"))


def lancer(d, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e["BRAIN_HOME"] = d
    r = subprocess.run([sys.executable, OUTIL, *args], capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


def verdicts(d, cas):
    p = os.path.join(d, "v.json")
    json.dump({"modele": "banc", "verdicts": cas}, open(p, "w", encoding="utf-8"))
    return p


def dernier_lot(d):
    return json.load(open(os.path.join(d, "state", "relations-lots.json"),
                          encoding="utf-8"))["lots"][-1]


def etats(lot):
    return sorted(p["etat"].split(":")[0] for p in lot["propositions"])


def bon(nom, ok, dit=""):
    print(f"  {'✅' if ok else '⛔'} {nom}{(' — ' + dit) if dit and not ok else ''}")
    return 0 if ok else 1


def main():
    rates = 0
    print("A1-A3 — poser puis retirer rend la fiche identique à l'octet près")
    for nom, fiche in (("sans bloc", "fiche-a"), ("forme courte", "fiche-b"),
                       ("forme à tirets", "fiche-c")):
        d = tronc()
        avant = open(os.path.join(d, "lessons", f"{fiche}.md"), "rb").read()
        file_attente(d, [fiche])
        lancer(d, "--cas")
        lancer(d, "--proposer", verdicts(d, [{"id": fiche, "relations": [
            {"ref": "c02", "type": "base_sur", "raison": "r", "ou": "§1"}]}]))
        lot = dernier_lot(d)["id"]
        lancer(d, "--appliquer", lot)
        milieu = open(os.path.join(d, "lessons", f"{fiche}.md"), "rb").read()
        pose = b"cible-deux" in milieu
        lancer(d, "--retirer", lot)
        apres = open(os.path.join(d, "lessons", f"{fiche}.md"), "rb").read()
        rates += bon(f"{nom} : posée puis retirée", pose and avant == apres,
                     "posée" if pose else "PAS posée")
        shutil.rmtree(d)

    print("S1 — `lie_a` refusé à la porte")
    d = tronc(); file_attente(d, ["fiche-a"]); lancer(d, "--cas")
    _, s = lancer(d, "--proposer", verdicts(d, [{"id": "fiche-a", "relations": [
        {"ref": "c01", "type": "lie_a", "raison": "r", "ou": "§1"}]}]))
    rates += bon("aucune proposition retenue", not dernier_lot(d)["propositions"] and "lie_a" in s)
    shutil.rmtree(d)

    print("S2 — fiche modifiée depuis le jugement : périmée, fiche intacte")
    d = tronc(); file_attente(d, ["fiche-a"]); lancer(d, "--cas")
    lancer(d, "--proposer", verdicts(d, [{"id": "fiche-a", "relations": [
        {"ref": "c01", "type": "base_sur", "raison": "r", "ou": "§1"}]}]))
    p = os.path.join(d, "lessons", "fiche-a.md")
    open(p, "a", encoding="utf-8").write("\nUne autre session a écrit ici.\n")
    avant = open(p, "rb").read()
    lancer(d, "--appliquer", dernier_lot(d)["id"])
    rates += bon("marquée périmée et rien d'écrit",
                 etats(dernier_lot(d)) == ["perimee"] and open(p, "rb").read() == avant)
    shutil.rmtree(d)

    print("S3 — cible inexistante refusée")
    d = tronc(); file_attente(d, ["fiche-a"]); lancer(d, "--cas")
    os.remove(os.path.join(d, "lessons", "cible-un.md"))
    lancer(d, "--proposer", verdicts(d, [{"id": "fiche-a", "relations": [
        {"ref": "c01", "type": "base_sur", "raison": "r", "ou": "§1"}]}]))
    lancer(d, "--appliquer", dernier_lot(d)["id"])
    rates += bon("refusée, pas posée", etats(dernier_lot(d)) == ["refusee"])
    shutil.rmtree(d)

    print("S4 — une relation écrite AVANT le lot survit au retrait")
    d = tronc(); file_attente(d, ["fiche-b"]); lancer(d, "--cas")
    lancer(d, "--proposer", verdicts(d, [{"id": "fiche-b", "relations": [
        {"ref": "c01", "type": "base_sur", "raison": "r", "ou": "§1"}]}]))   # cible-un DÉJÀ là
    lot = dernier_lot(d)["id"]
    lancer(d, "--appliquer", lot)
    lancer(d, "--retirer", lot)
    reste = open(os.path.join(d, "lessons", "fiche-b.md"), encoding="utf-8").read()
    rates += bon("épargnée par le retrait",
                 etats(dernier_lot(d)) == ["deja_la"] and "cible-un" in reste)
    shutil.rmtree(d)

    print("S5 — proposition sans raison ni emplacement refusée")
    d = tronc(); file_attente(d, ["fiche-a"]); lancer(d, "--cas")
    lancer(d, "--proposer", verdicts(d, [{"id": "fiche-a", "relations": [
        {"ref": "c01", "type": "base_sur", "raison": "", "ou": ""}]}]))
    rates += bon("aucune proposition retenue", not dernier_lot(d)["propositions"])
    shutil.rmtree(d)

    print("M1 — une pose normale est lue par l'export du graphe, et ne touche que l'en-tête")
    d = tronc(); file_attente(d, ["fiche-a"]); lancer(d, "--cas")
    lancer(d, "--proposer", verdicts(d, [{"id": "fiche-a", "relations": [
        {"ref": "c01", "type": "precise", "raison": "r", "ou": "§1"}]}]))
    lancer(d, "--appliquer", dernier_lot(d)["id"])
    sys.path.insert(0, os.path.join(d, "hooks"))
    txt = open(os.path.join(d, "lessons", "fiche-a.md"), encoding="utf-8").read()
    import importlib
    ge = importlib.import_module("graph_export")
    lue = ge._relations(txt)
    rates += bon("relation lisible par le graphe, corps intact",
                 lue.get("precise") == ["cible-un"]
                 and "Corps de la fiche A, qui ne doit jamais bouger." in txt, str(lue))
    shutil.rmtree(d)

    print(f"\n{'✅ tous les contrôles passent' if not rates else f'⛔ {rates} contrôle(s) en échec'}")
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(main())
