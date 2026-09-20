#!/usr/bin/env python3
"""projection_source_fraiche — un mode d'exception ne se désarme pas tout seul.

POURQUOI CE BANC EXISTE (mesuré le 2026-09-20)
    `config/claude-hooks.json` est la SOURCE de la projection des hooks Claude Code.
    Elle porte des « modes d'exception » : des retraits temporaires décidés pour une
    campagne, chacun avec sa condition de levée écrite en toutes lettres.

    `_aveuglement_annotation` a été armé le 2026-08-21 pour la campagne L1, avec
    `_leve_quand: « les projections sont générées et le scoring est fait »`. La
    campagne a été CLOSE le 2026-08-25 (acte 5d3025f7). Personne n'est revenu.
    VINGT-SIX JOURS plus tard, `settings_projection.py --diff` proposait encore de
    retirer `inject_recall.py` de ~/.claude/settings.json — c'est-à-dire de couper le
    rappel à la demande (`?brain`) au nom d'une expérience terminée.

    LA LEÇON, ET C'EST ELLE QU'ON VERROUILLE : un outil d'alignement aligne sur sa
    source. Si la source est périmée, s'aligner N'EST PAS se réparer, c'est régresser.
    Une condition de levée écrite en français n'est lue par aucun programme ; ce qu'un
    programme peut exiger, c'est que quelqu'un soit REVENU REGARDER, et le date.

CE QUE CE BANC VÉRIFIE — quatre propriétés, aucune ne dépend de cette machine
    A · la source est un JSON valide et chaque script déclaré existe vraiment
    B · chaque marqueur `i3` est un de ceux que le projecteur comprend
    C · un mode encore ARMÉ porte un `_revu_le` d'au plus 30 jours
    D · un mode LEVÉ porte un `_leve_le` — une levée est datée, jamais silencieuse

CE QU'IL NE VÉRIFIE PAS
    Que la condition de levée est remplie : elle est écrite pour un humain et aucun
    programme ne sait la lire. Ce banc n'exige pas le bon jugement, il exige qu'un
    jugement ait eu lieu et qu'il porte une date. Il ne regarde pas non plus
    ~/.claude/settings.json — c'est l'état d'UNE machine, et `settings_projection.py
    --verifie` est l'instrument de cette question-là.
"""
import datetime
import json
import os
import sys

BRAIN = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SOURCE = os.path.join(BRAIN, "config", "claude-hooks.json")
I3_CONNUS = {"ancre", "differe"}
PEREMPTION_JOURS = 30


def _date(txt):
    """La date en tête d'une valeur ('2026-09-20 — pourquoi'), ou None."""
    if not isinstance(txt, str):
        return None
    try:
        return datetime.date.fromisoformat(txt.strip()[:10])
    except ValueError:
        return None


def main():
    aujourdhui = datetime.date.today()
    try:
        source = json.load(open(SOURCE, encoding="utf-8"))
    except Exception as e:
        print(f"⛔ A · la source de projection est illisible : {e}")
        return 1

    manquants, i3_inconnus, perimes, levees_muettes = [], [], [], []

    for evenement, entrees in source.get("hooks", {}).items():
        for e in entrees:
            commande = e.get("commande", "")
            chemin = commande.replace("__BRAIN__", BRAIN).split()
            script = next((m for m in chemin if m.endswith(".py")), None)
            if script and not os.path.exists(script):
                manquants.append(f"{evenement} · {os.path.basename(script)}")
            i3 = e.get("i3")
            if i3 is not None and i3 not in I3_CONNUS:
                i3_inconnus.append(f"{evenement} · {os.path.basename(commande)} → {i3!r}")

    for cle, mode in source.items():
        if not (isinstance(mode, dict) and "actif" in mode):
            continue
        if mode["actif"]:
            revu = _date(mode.get("_revu_le"))
            if revu is None:
                perimes.append(f"{cle} — armé depuis {mode.get('depuis','?')}, aucun `_revu_le`")
            elif (aujourdhui - revu).days > PEREMPTION_JOURS:
                perimes.append(f"{cle} — dernier regard le {revu}, il y a {(aujourdhui - revu).days} jours")
        elif not _date(mode.get("_leve_le")):
            levees_muettes.append(f"{cle} — levé sans `_leve_le` daté")

    if manquants:
        print("⛔ A · la source déclare un hook dont le script n'existe pas — la projection "
              "installerait une commande qui ne peut pas tourner :")
        for m in manquants:
            print(f"     · {m}")
        return 1

    if i3_inconnus:
        print("⛔ B · marqueur `i3` inconnu du projecteur. Il ne vaut pas « autre chose » : "
              "il vaut SILENCIEUSEMENT « pas de BRAIN_HOME », et le hook mesurera le mauvais "
              "tronc sans que rien ne le dise :")
        for m in i3_inconnus:
            print(f"     · {m}")
        return 1

    if perimes:
        print(f"⛔ C · un mode d'exception est encore armé et personne n'est revenu le "
              f"regarder depuis plus de {PEREMPTION_JOURS} jours. Un retrait temporaire ne "
              f"se désarme pas tout seul : tant qu'il tient, `settings_projection.py "
              f"--installe` RÉAPPLIQUE ce retrait, et s'aligner devient une régression. "
              f"Relire sa condition de levée, puis soit la lever, soit dater un `_revu_le` :")
        for m in perimes:
            print(f"     · {m}")
        return 1

    if levees_muettes:
        print("⛔ D · un mode a été levé sans date. Une levée silencieuse ne laisse aucune "
              "trace de qui a décidé, ni quand, ni sur quelle mesure :")
        for m in levees_muettes:
            print(f"     · {m}")
        return 1

    modes = [k for k, v in source.items() if isinstance(v, dict) and "actif" in v]
    armes = [k for k in modes if source[k]["actif"]]
    n = sum(len(v) for v in source.get("hooks", {}).values())
    print(f"✅ source de projection saine — {n} hooks déclarés, tous présents, "
          f"{len(modes)} mode(s) d'exception dont {len(armes)} armé(s) et revu(s) "
          f"depuis moins de {PEREMPTION_JOURS} jours")
    return 0


if __name__ == "__main__":
    sys.exit(main())
