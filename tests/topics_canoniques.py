"""La taxonomie codée ne doit pas pouvoir diverger de la taxonomie validée.

POURQUOI CE CONTRÔLE EXISTE. Le 2026-08-27, l'instrument de classement affichait encore les
noms de la PROPOSITION et déclarait 13 sujets, alors que la supervision en avait validé 12
et réfuté le treizième deux lots plus tôt. Personne ne l'a vu pendant trois lots : la
divergence n'était visible que si on relisait le code en connaissant la décision.

Deux verrous, et le premier vaut mieux que le second :
  1. `meta/topics.json` est la SOURCE. `tools/nettoyage/topics_proposition.py` la LIT au
     lieu de redéclarer les noms — il n'y a donc plus de second endroit où écrire la vérité.
  2. Ce banc gèle la liste validée et refuse tout écart : nombre, identifiants, libellés,
     et retour du treizième sujet.

Le second verrou existe parce que le premier peut être défait par une édition future.
"""
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# GELÉ le 2026-08-27 sur la décision de supervision. Modifier cette liste demande une
# décision écrite, pas une retouche : c'est elle qui rend le banc capable de rougir.
VALIDES = [
    ("preuve-et-verification", "Preuve et vérification"),
    ("projets-clients", "Projets clients et applications terrain"),
    ("le-brain", "Mémoire et architecture du Brain"),
    ("interfaces-et-rendu", "Interfaces et expérience utilisateur"),
    ("machine-et-processus", "Machine et système local"),
    ("git-et-travail-a-plusieurs", "Git et travail à plusieurs"),
    ("mise-en-ligne-et-services", "Mise en ligne et services distants"),
    ("travailler-avec-dylan", "Méthode de travail avec l'auteur"),
    ("agents-et-sessions", "Agents autonomes et sessions"),
    ("vie-et-carriere", "Vie, carrière et cadre personnel"),
    ("documents-et-livrables", "Documents et livrables"),
    ("securite-et-confidentialite", "Sécurité et confidentialité"),
]
RETIRE = "methodes-de-fabrication"


def controler(canon):
    fautes = []
    topics = canon.get("topics", [])
    if len(topics) != len(VALIDES):
        fautes.append("nombre de sujets : %d au lieu de %d" % (len(topics), len(VALIDES)))
    vus = {t.get("id"): t.get("nom") for t in topics}
    attendus = dict(VALIDES)
    for cle in vus:
        if cle == RETIRE:
            fautes.append("le 13e sujet retiré est réapparu : %s" % RETIRE)
        elif cle not in attendus:
            fautes.append("identifiant inconnu : %s" % cle)
    for cle, nom in VALIDES:
        if cle not in vus:
            fautes.append("identifiant manquant : %s" % cle)
        elif vus[cle] != nom:
            fautes.append("libellé de %s : « %s » au lieu de « %s »" % (cle, vus[cle], nom))
    return fautes


def main():
    canon = json.load(open(os.path.join(RACINE, "meta", "topics.json"), encoding="utf-8"))
    fautes = controler(canon)

    # L'instrument lit-il RÉELLEMENT la source, ou en a-t-il refait une copie ?
    sys.path.insert(0, os.path.join(RACINE, "tools", "nettoyage"))
    import topics_proposition as T
    codes = [c for c, _k in T.TOPICS]
    if codes != [c for c, _n in VALIDES] and sorted(codes) != sorted(c for c, _n in VALIDES):
        fautes.append("l'instrument déclare %d sujets : %s" % (len(codes), ", ".join(codes)))
    for cle, nom in VALIDES:
        if T.NOMS.get(cle) != nom:
            fautes.append("l'instrument affiche « %s » pour %s" % (T.NOMS.get(cle), cle))

    print("Taxonomie canonique — meta/topics.json")
    print("  sujets déclarés : %d" % len(canon.get("topics", [])))
    print("  sujets exercés par l'instrument : %d" % len(T.TOPICS))
    if fautes:
        print("\n❌ LA TAXONOMIE CODÉE A DIVERGÉ DE LA TAXONOMIE VALIDÉE :")
        for f in fautes:
            print("   · %s" % f)
        return 1
    print("\n✅ les 12 sujets validés, mêmes identifiants et mêmes libellés, une seule source.")

    # Contre-épreuve : le banc doit savoir rougir. Quatre atteintes, sur une COPIE en
    # mémoire — le fichier réel n'est jamais touché.
    import copy
    print("\nCONTRE-ÉPREUVE — le banc rougit-il quand il le doit ?")
    cas = [
        ("un sujet retiré", lambda c: c["topics"].pop()),
        ("un identifiant inconnu", lambda c: c["topics"][0].__setitem__("id", "inventé")),
        ("un libellé modifié", lambda c: c["topics"][3].__setitem__("nom", "Interfaces et rendu visuel")),
        ("le 13e sujet réapparaît", lambda c: c["topics"].append({"id": RETIRE, "nom": "Méthodes de fabrication"})),
    ]
    ok = True
    for nom, saboter in cas:
        c = copy.deepcopy(canon)
        saboter(c)
        rouge = bool(controler(c))
        print("   %s %s" % ("✅" if rouge else "❌", nom))
        ok = ok and rouge
    if not ok:
        print("\n❌ un sabotage reste VERT : le contrôle ne protège pas.")
        return 1
    print("   les quatre atteintes sont détectées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
