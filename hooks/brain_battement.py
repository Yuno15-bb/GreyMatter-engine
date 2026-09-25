#!/usr/bin/env python3
"""brain_battement — le pouls du compagnon de bureau.

Hook PostToolUse sur TOUS les outils : un appel d'outil, c'est la définition
même de « quelque chose travaille ».

24/09/2026 — aussi sur UserPromptSubmit et PreToolUse, et `--fin` sur Stop.
Avec l'orbe dans l'encoche, le seul PostToolUse ne suffisait plus : pendant que
Claude réfléchit ou écrit sa réponse, aucun outil ne finit, le pouls se périme
et l'orbe rentrait en plein travail. L'utilisateur : « je ne la vois plus travailler ».

⚠ LE DÉFAUT QU'IL CORRIGE (2026-07-31). `on_fiche_write` écrivait `busy` dans
state/status.json, et RIEN ne réécrivait jamais `idle` avant la fin de session.
`touch_status()` existait dans brain_status.py mais n'était appelé par AUCUN
hook. Résultat : le fichier restait sur `busy` avec un horodatage périmé —
relevé à 1754 s — la capsule appliquait sa garde de fraîcheur de 30 s, retombait
en repos, et le compagnon se figeait PENDANT que Claude travaillait.
L'utilisateur : « il est figé sur le bureau immobile et ça fait souvent ça ».

Effet de bord heureux : la garde de fraîcheur devient le détecteur de FIN. Plus
d'appel d'outil → plus de battement → au bout de 30 s le compagnon s'arrête tout
seul. Aucun hook de fin de tour n'est nécessaire.

⚠ On ne vole pas la main à un agent : si un agent travaille et que son statut est
frais, on se contente de rafraîchir son horodatage — sa teinte et son libellé
restent les siens.

Sort toujours 0 : un pouls ne doit jamais faire échouer un outil.
"""
import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    try:
        from brain_status import write_status, touch_status, STATUS
    except Exception:
        return
    try:
        try:
            with open(STATUS, "r", encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}
        frais = (time.time() - cur.get("ts", 0)) < 30
        # --fin (hook Stop, 24/09) : la réponse est finie, l'orbe rentre dans
        # l'encoche tout de suite au lieu d'attendre que le pouls se périme.
        # Seulement si c'est NOTRE statut : un agent qui tourne garde le sien.
        if "--fin" in sys.argv:
            if cur.get("source", "you") == "you":
                write_status("idle")
            return
        if cur.get("state") == "busy" and frais:
            touch_status()                      # on prolonge ce qui tourne déjà
        else:
            write_status("busy", "working", None, source="you")
    except Exception:
        pass

if __name__ == "__main__":
    main()
    sys.exit(0)
