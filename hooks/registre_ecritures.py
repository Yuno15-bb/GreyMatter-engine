#!/usr/bin/env python3
"""registre_ecritures — rendre OBSERVABLE quelle session a fait bouger une fiche du tronc.

POURQUOI CE FICHIER EXISTE (mesuré le 2026-08-28)
    `state/manual-saves.jsonl` n'avait plus reçu une seule entrée depuis le 2026-08-18,
    alors que 189 fiches du savoir portaient une date de modification postérieure. Le
    registre n'était pas cassé : reproduit sur un tronc jetable, `on_fiche_write.py`
    écrit correctement son entrée. C'est son DÉCLENCHEUR qui ne voyait plus rien —
    il n'est armé que sur `PostToolUse Write|Edit`, et le balayage des 32 transcripts
    postérieurs au 18/08 ne trouve que 9 écritures de fiche par ces deux outils, toutes
    de la session 397b659d, celle-là même dont les dernières entrées du registre datent.
    Tout le reste passe par Bash — heredoc, `sed -i`, script Python — ou par les agents
    de fond, que le registre exclut volontairement.

CE QU'IL N'EST PAS
    Ce n'est PAS un remplacement de `manual-saves.jsonl`. Celui-là a un contrat étroit et
    un consommateur unique : `auto_maintain.py` le lit pour dire au distillateur « ne
    recrée pas ces fiches, la session les a écrites à la main ». Y verser des écritures de
    script ferait taire le distillateur sur du savoir que personne n'a rédigé. Les deux
    registres coexistent, chacun avec son contrat.

CE QU'IL PROUVE, ET CE QU'IL NE PROUVE PAS
    Il observe un EFFET — une fiche dont la date de modification a dépassé le dernier
    passage — et non un MOYEN. Il couvre donc n'importe quel outil, y compris ceux qui
    n'existent pas encore. En contrepartie, l'identité qu'il note est celle de la session
    dont l'outil vient de rendre la main : c'est une attribution par COÏNCIDENCE, pas une
    preuve d'auteur. Le champ `attribution` le dit dans chaque ligne, pour qu'aucune
    lecture ultérieure ne puisse le prendre pour plus qu'il n'est.

HORS COUVERTURE, ET C'EST DÉCLARÉ
    Une écriture faite pendant qu'aucun outil ne tourne (agent de fond, tâche planifiée,
    éditeur externe) n'est vue qu'au passage suivant, et sera alors attribuée à la session
    de ce passage-là. Deux sessions actives en même temps peuvent se voler une ligne.
    Le registre répond « quelque chose a écrit cette fiche vers cette heure-ci », jamais
    « cette session l'a écrite ».
"""
import json
import os
import sys
import time

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
ZONES = ("projects", "lessons", "meta", "life", "skills")
REGISTRE = os.path.join(BRAIN, "state", "ecritures-fiches.jsonl")
JALON = os.path.join(BRAIN, "state", "ecritures-fiches.jalon")
# Un premier passage sans jalon verrait TOUT le tronc comme « modifié » et écrirait 500
# lignes de bruit. On borne : au premier passage, on pose le jalon et on ne journalise rien.
FENETRE_MAX = 3600.0


def _jalon_lu():
    try:
        return float(open(JALON, encoding="utf-8").read().strip())
    except Exception:
        return None


def _jalon_ecrit(t):
    tmp = JALON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("%.6f" % t)
    os.replace(tmp, JALON)


def fiches_modifiees(depuis):
    """Les fiches .md des zones du savoir dont la mtime dépasse `depuis`. 3,4 ms mesurés."""
    out = []
    for z in ZONES:
        racine = os.path.join(BRAIN, z)
        if not os.path.isdir(racine):
            continue
        for root, dirs, files in os.walk(racine):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for nom in files:
                if not nom.endswith(".md"):
                    continue
                chemin = os.path.join(root, nom)
                try:
                    m = os.stat(chemin).st_mtime
                except OSError:
                    continue
                if m > depuis:
                    out.append((os.path.relpath(chemin, BRAIN), m))
    return sorted(out)


def main(data):
    maintenant = time.time()
    precedent = _jalon_lu()
    _jalon_ecrit(maintenant)
    if precedent is None:
        return 0                      # premier passage : on arme, on ne journalise pas
    depuis = max(precedent, maintenant - FENETRE_MAX)
    touchees = fiches_modifiees(depuis)
    if not touchees:
        return 0
    sid = (data or {}).get("session_id") or "inconnu"
    outil = (data or {}).get("tool_name") or "inconnu"
    os.makedirs(os.path.dirname(REGISTRE), exist_ok=True)
    with open(REGISTRE, "a", encoding="utf-8") as f:
        for rel, m in touchees:
            f.write(json.dumps({"ts": int(maintenant), "sid": sid, "path": rel,
                                "mtime": int(m), "ecart_s": int(maintenant - m),
                                "outil": outil,
                                "attribution": "coincidence"}, ensure_ascii=False) + "\n")
    return len(touchees)


if __name__ == "__main__":
    try:
        charge = json.loads(sys.stdin.read() or "{}")
    except Exception:
        charge = {}
    try:
        main(charge)
    except Exception:
        pass                          # règle d'or des hooks du tronc : ne jamais bloquer
    sys.exit(0)
