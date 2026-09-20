#!/usr/bin/env python3
"""recall_feedback — ferme la boucle usage → classement.

LE PROBLÈME QU'IL RÉSOUT. `inject_recall.py` écrit dans `state/recall_log.jsonl` en
mode « a » et **personne ne relit ce fichier**. Idem pour `state/read_log.jsonl`, relu
seulement par la visualisation 3D. Le Brain journalisait donc depuis des mois ce qui a
servi et ce qui n'a jamais servi, et n'en tirait rien : 2,3 % des fiches suggérées sont
réellement ouvertes, et rien ne corrigeait ce taux.

CE QU'IL CALCULE. Pour chaque fiche, le nombre de fois où elle a été **suggérée puis
réellement ouverte dans la même session**. C'est le seul signal honnête disponible :
« suggérée » seul ne prouve rien, « ouverte » seul peut venir d'une recherche manuelle.

CE QU'IL NE FAIT PAS, DÉLIBÉRÉMENT.
  • Aucune pénalité pour les fiches jamais ouvertes. Une fiche peut être excellente et
    mal décrite ; la punir au classement l'enterre définitivement et personne ne le voit.

    ⚠️ ET SURTOUT : « souvent proposée, jamais ouverte » N'EST PAS un défaut.
    Vérifié à la main sur les 50 fiches concernées — **une seule** avait une description
    réellement vague. Les autres sont dans l'autre cas, exactement inverse : leur
    description répond DÉJÀ à la question, donc ne pas ouvrir la fiche est un SUCCÈS.
    Exemple : `separation-pouvoirs-agent-teams`, proposée 73 fois, jamais ouverte — sa
    description dit tout en une ligne.
    Le fichier de sortie s'appelait `a-revoir-description.json` : ce nom présupposait le
    défaut et aurait poussé à réécrire 50 fiches, c'est-à-dire à détruire ce qui marche.
    Il décrit maintenant l'OBSERVATION, pas un verdict. C'est un point de départ
    d'enquête, à lire fiche par fiche.
  • Aucune suppression. Ce fichier ne touche à aucune fiche.

Sorties :
  state/recall-utilite.json                  {chemin: {sugg, hit, dernier}} — lu par brain_recall
  state/souvent-proposee-jamais-ouverte.json  observation brute, PAS un verdict (cf. plus bas)

Usage :
  recall_feedback.py            recalcule les deux fichiers
  recall_feedback.py --rapport  recalcule et imprime un résumé lisible
"""
import os, sys, json, collections, datetime

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
ETAT = os.path.join(BRAIN, "state")
UTILITE = os.path.join(ETAT, "recall-utilite.json")
SOUVENT_JAMAIS = os.path.join(ETAT, "souvent-proposee-jamais-ouverte.json")

# Une lecture qui précède de peu sa suggestion compte quand même : les horodatages du
# hook et de l'outil de lecture ne sont pas posés au même instant.
TOLERANCE_S = 60
# Au-delà, « souvent proposée, jamais ouverte » cesse d'être du hasard.
SEUIL_A_REVOIR = 8


def _lire(nom):
    p = os.path.join(ETAT, nom)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for ligne in f:
            try:
                d = json.loads(ligne)
            except Exception:
                continue                      # ligne tronquée par un hook tué : on saute
            if d.get("path") and d.get("sid"):
                out.append(d)
    return out


def calculer():
    suggestions, premiere = collections.defaultdict(set), {}
    for d in _lire("recall_log.jsonl"):
        suggestions[d["path"]].add(d["sid"])
        cle = (d["path"], d["sid"])
        premiere[cle] = min(premiere.get(cle, d["ts"]), d["ts"])

    lectures = collections.defaultdict(list)
    for d in _lire("read_log.jsonl"):
        lectures[(d["path"], d["sid"])].append(d["ts"])

    # ADR-0018 / M5 (2026-09-19) : l'usage ne classe plus, il ANNOTE. Une annotation qui
    # ne dit pas QUAND ne vaut rien — « ouverte 5 fois » peut dater de trois mois. La date
    # se calcule ici, dans la boucle qui tient déjà les horodatages : le rappel, lui, lit
    # un nombre déjà écrit et ne paie rien de plus à chaque prompt.
    utilite = {}
    for chemin, sids in suggestions.items():
        derniers = []
        for sid in sids:
            vues = [ts for ts in lectures.get((chemin, sid), ())
                    if ts >= premiere[(chemin, sid)] - TOLERANCE_S]
            if vues:                          # même règle qu'avant : au moins une lecture
                derniers.append(max(vues))    # qui suit la suggestion, à la tolérance près
        utilite[chemin] = {"sugg": len(sids), "hit": len(derniers)}
        if derniers:
            utilite[chemin]["dernier"] = datetime.datetime.fromtimestamp(
                max(derniers)).strftime("%Y-%m-%d")

    a_revoir = sorted(
        ({"path": c, "sugg": v["sugg"]} for c, v in utilite.items()
         if v["hit"] == 0 and v["sugg"] >= SEUIL_A_REVOIR),
        key=lambda x: -x["sugg"])
    return utilite, a_revoir


def ecrire(chemin, donnees):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    tmp = f"{chemin}.{os.getpid()}.tmp"          # atomique : jamais de demi-fichier
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False)
    os.replace(tmp, chemin)


def main():
    utilite, a_revoir = calculer()
    ecrire(UTILITE, utilite)
    ecrire(SOUVENT_JAMAIS, a_revoir)

    if "--rapport" not in sys.argv:
        return 0
    sugg = sum(v["sugg"] for v in utilite.values())
    hit = sum(v["hit"] for v in utilite.values())
    print(f"{len(utilite)} fiches suggérées · {sugg} couples (fiche, session)")
    print(f"suggérées PUIS ouvertes : {hit} ({hit / sugg * 100:.1f} %)" if sugg else "aucune suggestion")
    porteuses = sorted((v["hit"], v["sugg"], c) for c, v in utilite.items() if v["hit"])
    print(f"\nfiches qui servent vraiment ({len(porteuses)}) :")
    for h, s, c in sorted(porteuses, reverse=True)[:8]:
        print(f"  {h:3d}/{s:<3d}  {c}")
    print(f"\nproposées ≥{SEUIL_A_REVOIR}× et jamais ouvertes ({len(a_revoir)}) — observation,")
    print("pas un défaut : une description qui répond déjà rend la lecture inutile.")
    for x in a_revoir[:8]:
        print(f"  {x['sugg']:3d}×  {x['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
