#!/usr/bin/env python3
"""BANC — le sujet écrit dans une fiche est-il RELISIBLE, et le mauvais est-il REFUSÉ ?

Le banc exerce `hooks/topics_fiche.py`, c'est-à-dire EXACTEMENT le code que l'outil
d'écriture utilise en production. Un banc qui réimplémenterait la lecture prouverait
seulement que deux copies s'accordent — la faute mesurée le 20/08, où deux lecteurs de
`MEMORY.md` fabriquaient la divergence qu'ils mesuraient.

Aucune fiche du tronc n'est touchée : tout se joue sur des textes en mémoire.
"""
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(ICI), "hooks"))
import topics_fiche as T  # noqa: E402

FICHE = """---
name: fiche-de-banc
description: "Une fiche d'essai."
tags: [le-cerveau]
metadata:
  type: lesson
---

# Corps

Texte inchangé.
"""

SANS_TAGS = """---
name: fiche-sans-tags
description: "Pas de tags ici."
metadata:
  type: lesson
---

Corps.
"""


def main():
    ids = T.ids_canoniques()
    echecs = []

    print("Lecture — ce qui est écrit se relit à l'identique")
    cas = [
        ("un sujet, aucun secondaire", "preuve-et-verification", []),
        ("un sujet, un secondaire", "le-brain", ["preuve-et-verification"]),
        ("un sujet, deux secondaires", "projets-clients",
         ["interfaces-et-rendu", "preuve-et-verification"]),
    ]
    for nom, topic, secs in cas:
        sorti = T.ecrire(FICHE, topic, secs, ids)
        relu_t, relu_s = T.lire(sorti)
        ok = (relu_t == topic and relu_s == secs)
        print("   %s %s" % ("✅" if ok else "❌", nom))
        if not ok:
            echecs.append("relecture : " + nom)

    # le corps ne bouge pas — un seul champ ajouté, rien d'autre
    sorti = T.ecrire(FICHE, "le-brain", ["preuve-et-verification"], ids)
    ajoutees = [l for l in sorti.split("\n") if l not in FICHE.split("\n")]
    retirees = [l for l in FICHE.split("\n") if l not in sorti.split("\n")]
    propre = (sorted(ajoutees) == ["topic: le-brain",
                                   "topics_secondaires: [preuve-et-verification]"]
              and retirees == [])
    print("   %s le diff ne contient QUE les deux lignes de sujet" % ("✅" if propre else "❌"))
    if not propre:
        echecs.append("diff pollué : + %s / - %s" % (ajoutees, retirees))

    # place d'insertion : après tags quand il existe, après description sinon
    apres_tags = T.ecrire(FICHE, "le-brain", [], ids).split("\n")
    i_tags = next(i for i, l in enumerate(apres_tags) if l.startswith("tags:"))
    bien_place = apres_tags[i_tags + 1] == "topic: le-brain"
    sans = T.ecrire(SANS_TAGS, "le-brain", [], ids).split("\n")
    i_desc = next(i for i, l in enumerate(sans) if l.startswith("description:"))
    bien_place2 = sans[i_desc + 1] == "topic: le-brain"
    print("   %s inséré après `tags:`, ou après `description:` s'il n'y en a pas"
          % ("✅" if bien_place and bien_place2 else "❌"))
    if not (bien_place and bien_place2):
        echecs.append("place d'insertion")

    # réécrire remplace, n'empile pas
    deux_fois = T.ecrire(T.ecrire(FICHE, "le-brain", [], ids),
                         "preuve-et-verification", ["machine-et-processus"], ids)
    # compter des LIGNES, pas des sous-chaînes : « topics_secondaires: » ne contient pas
    # « topic: », mais une assertion écrite sur `str.count` s'est trompée ici avant d'être
    # corrigée — le code était juste, la mesure ne l'était pas.
    lignes_fm = T.bloc_frontmatter(deux_fois).split("\n")
    n_topic = sum(1 for l in lignes_fm if l.startswith("topic:"))
    n_sec = sum(1 for l in lignes_fm if l.startswith("topics_secondaires:"))
    relu_t, relu_s = T.lire(deux_fois)
    remplace = (n_topic == 1 and n_sec == 1
                and relu_t == "preuve-et-verification"
                and relu_s == ["machine-et-processus"])
    print("   %s réécrire REMPLACE la clé au lieu de l'empiler" % ("✅" if remplace else "❌"))
    if not remplace:
        echecs.append("empilement de clés")

    print("\nCONTRE-ÉPREUVE — chaque faute doit être REFUSÉE, jamais corrigée en silence")
    refus = [
        ("sujet principal inconnu", "sujet-invente", []),
        ("ancien 13e sujet, retiré de la source", "methodes-de-fabrication", []),
        ("aucun sujet principal", None, []),
        ("sujet principal vide", "", []),
        ("secondaire inconnu", "le-brain", ["pas-un-sujet"]),
        ("secondaire identique au principal", "le-brain", ["le-brain"]),
        ("secondaire en double", "le-brain", ["preuve-et-verification",
                                              "preuve-et-verification"]),
        ("deux sujets principaux", ["le-brain", "preuve-et-verification"], []),
    ]
    for nom, topic, secs in refus:
        try:
            T.valider(topic, secs, ids)
            rouge = False
        except T.SujetInvalide:
            rouge = True
        print("   %s %s" % ("✅ refusé" if rouge else "❌ ACCEPTÉ —", nom))
        if not rouge:
            echecs.append("accepté à tort : " + nom)

    # deux `topic:` écrits à la main dans le fichier : la LECTURE doit le signaler
    double = FICHE.replace("tags: [le-cerveau]",
                           "tags: [le-cerveau]\ntopic: le-brain\ntopic: projets-clients")
    lu, _ = T.lire(double)
    vu = isinstance(lu, list)
    print("   %s deux `topic:` dans le fichier sont VUS comme une faute, pas départagés"
          % ("✅" if vu else "❌"))
    if not vu:
        echecs.append("double topic départagé au lieu d'être signalé")

    # la source fait autorité : un id valide aujourd'hui doit cesser de l'être si on le retire
    ids_ampute = [i for i in ids if i != "le-brain"]
    try:
        T.valider("le-brain", [], ids_ampute)
        suit = False
    except T.SujetInvalide:
        suit = True
    print("   %s un sujet retiré de la source devient invalide immédiatement"
          % ("✅" if suit else "❌"))
    if not suit:
        echecs.append("la validation ne suit pas la source")

    print()
    if echecs:
        print("❌ BANC ROUGE : " + " · ".join(echecs))
        return 1
    print("✅ BANC VERT — le sujet se relit à l'identique, le diff ne porte que lui, "
          "et les dix fautes sont refusées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
