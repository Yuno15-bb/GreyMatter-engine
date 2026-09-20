"""Contre-épreuve de l'inventaire R2 — chaque détecteur doit savoir ROUGIR.

POURQUOI CE BANC EXISTE. L'inventaire R2 rend « 0 collision, 0 doublon exact,
0 quasi-doublon, 0 remplacement » sur le tronc réel. Un zéro n'est une information que si
l'instrument qui le produit est capable de rendre autre chose. Sans ce banc, ces quatre
zéros seraient des décorations — exactement le défaut décrit par
`un-controle-qui-partage-l-instrument-de-l-action-ne-peut-pas-la-contredire`.

MÉTHODE. Un tronc de fixtures jetable, hors dépôt. D'abord un TÉMOIN propre : tout doit
être à zéro. Puis un sabotage par classe, appliqué au même témoin : la classe visée doit
rougir, et le témoin prouve qu'elle n'était pas déjà rouge pour une autre raison.

Le code de détection exercé est EXACTEMENT celui de la production : ce banc appelle
`r2_inventaire.detecter`, il n'en réécrit aucune ligne.
"""
import os
import shutil
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "tools", "nettoyage"))
import r2_inventaire as R  # noqa: E402

FICHE = """---
name: {nom}
title: "{titre}"
description: "{desc}"
tags: [methode-et-principes]
metadata:
  type: lesson
  updated: 2026-08-27
---

# {titre}

## En clair

{corps}
"""

CORPS_A = ("Quand un service tiers renvoie un succes, il faut aller regarder l objet reel "
           "avant de conclure que l operation a abouti, parce que le code de sortie ne "
           "decrit que l appel et jamais son effet sur la base distante ou le disque. "
           "Cette phrase existe uniquement pour donner de la matiere aux empreintes.") * 3
CORPS_B = ("Une pile de rendu qui accepte une image cassee sans jamais retenter laisse "
           "l interface dans un etat muet, et l utilisateur ne peut pas distinguer un "
           "chargement lent d un echec definitif sans un signal explicite du client. "
           "chargement lent d un echec definitif. Matiere differente pour les empreintes.") * 5


def tronc(fichiers):
    d = tempfile.mkdtemp(prefix="r2sab-")
    for chemin, contenu in fichiers.items():
        p = os.path.join(d, chemin)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(contenu)
    return d


def mesurer(fichiers):
    d = tronc(fichiers)
    try:
        chemins = sorted(fichiers)
        info = R.construire_info(chemins, racine=d)
        return R.detecter(info, chemins, util={}, rapport=False)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def temoin():
    return {
        "lessons/succes-distant-nest-pas-effet.md": FICHE.format(
            nom="succes-distant-nest-pas-effet", titre="Succes distant n est pas effet",
            desc="Un succes renvoye par un service distant ne prouve pas l effet",
            corps=CORPS_A),
        "lessons/image-cassee-jamais-retentee.md": FICHE.format(
            nom="image-cassee-jamais-retentee", titre="Image cassee jamais retentee",
            desc="Une image cassee sans nouvelle tentative laisse l interface muette",
            corps=CORPS_B),
    }


def classes(res):
    return {c: n for c, n in res["par_classe"].items()}


CAS = []


def cas(nom, classe):
    def deco(f):
        CAS.append((nom, classe, f))
        return f
    return deco


@cas("deux chemins pour la meme identite logique", "A")
def _a(f):
    f["meta/succes-distant-nest-pas-effet.md"] = f["lessons/succes-distant-nest-pas-effet.md"] \
        .replace("Succes distant", "Succes distant bis")
    return f


@cas("copie octet pour octet sous un autre nom", "B")
def _b(f):
    f["lessons/copie-exacte.md"] = f["lessons/succes-distant-nest-pas-effet.md"]
    return f


@cas("copie a quelques mots pres", "C")
def _c(f):
    f["lessons/presque-la-meme.md"] = f["lessons/succes-distant-nest-pas-effet.md"] \
        .replace("name: succes-distant-nest-pas-effet", "name: presque-la-meme") \
        .replace("disque", "volume")
    return f


@cas("relation de remplacement declaree", "D")
def _d(f):
    f["lessons/image-cassee-jamais-retentee.md"] = f["lessons/image-cassee-jamais-retentee.md"] \
        .replace("metadata:", "relations:\n  remplace: [succes-distant-nest-pas-effet]\nmetadata:")
    return f


@cas("nom dont aucun mot n apparait dans le titre ni la description", "I")
def _i(f):
    f["lessons/verrou-launchd-plist-orphelin.md"] = FICHE.format(
        nom="verrou-launchd-plist-orphelin", titre="Sujet totalement autre",
        desc="Rien de commun avec le nom du fichier", corps=CORPS_B)
    return f


@cas("fiche au corps minuscule", "J")
def _j(f):
    f["lessons/fragment.md"] = FICHE.format(
        nom="fragment", titre="Fragment", desc="Court", corps="Trois mots.")
    return f


def main():
    base = classes(mesurer(temoin()))
    print("TÉMOIN PROPRE — ce qui doit rester muet")
    muettes = [c for c in ("A", "B", "C", "D", "I", "J") if base.get(c)]
    for c in ("A", "B", "C", "D", "I", "J"):
        print("   %s : %d" % (c, base.get(c, 0)))
    if muettes:
        print("\n❌ le témoin est déjà rouge sur %s — aucun sabotage ne prouverait rien"
              % ", ".join(muettes))
        return 1
    print("   ✅ toutes muettes\n")

    print("SABOTAGES — chaque classe doit rougir, et elle seule être visée")
    echecs = []
    for nom, classe, f in CAS:
        res = classes(mesurer(f(temoin())))
        rouge = res.get(classe, 0) > 0
        print("   %s %s  %-52s %s=%d"
              % ("✅" if rouge else "❌", classe, nom, classe, res.get(classe, 0)))
        if not rouge:
            echecs.append((classe, nom))

    print()
    if echecs:
        print("❌ %d détecteur(s) restent VERTS sous sabotage : %s"
              % (len(echecs), ", ".join("%s (%s)" % (c, n) for c, n in echecs)))
        print("   Leurs zéros sur le tronc réel ne prouvent rien.")
        return 1
    print("✅ les 6 détecteurs rougissent quand ils doivent, et se taisent sinon.")
    print("   Les zéros de l'inventaire R2 sont donc des mesures, pas des décorations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
