#!/usr/bin/env python3
"""BANC — le registre d'écritures voit-il réellement une fiche bouger, et peut-il ROUGIR ?

Le registre remplacé ici est resté vert-silencieux dix jours : il n'écrivait plus rien, et
rien ne le disait. Un banc qui se contenterait de vérifier « une ligne a été écrite » aurait
le même défaut. On exige donc, à chaque fois, qu'un SABOTAGE du mécanisme rende le contrôle
ROUGE — sinon le contrôle ne regarde pas ce qu'il prétend regarder.

Aucune écriture ne touche le tronc réel : tout se joue dans un BRAIN_HOME jetable.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

ICI = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(ICI), "hooks", "registre_ecritures.py")


def charger(brain):
    """Charge le hook avec BRAIN_HOME pointé sur le tronc jetable."""
    os.environ["BRAIN_HOME"] = brain
    spec = importlib.util.spec_from_file_location("registre_ecritures_%d" % time.time_ns(), HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tronc():
    d = tempfile.mkdtemp(prefix="banc-registre-")
    for z in ("projects", "lessons", "meta", "life", "skills", "state"):
        os.makedirs(os.path.join(d, z), exist_ok=True)
    return d


def lignes(brain):
    p = os.path.join(brain, "state", "ecritures-fiches.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def ecrire(brain, rel, texte):
    """Écrit une fiche SANS passer par un outil tracé — exactement le cas qui échappait."""
    p = os.path.join(brain, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(texte)


def scenario(mod, brain):
    """Rend (n_traces_1, n_traces_2, entrees) pour deux écritures indépendantes."""
    mod.main({"session_id": "SID-A", "tool_name": "Bash"})          # arme le jalon
    time.sleep(1.05)
    ecrire(brain, "lessons/fixture-une.md", "# une\ntexte\n")
    n1 = mod.main({"session_id": "SID-A", "tool_name": "Bash"})
    time.sleep(1.05)
    ecrire(brain, "projects/fixture-deux.md", "# deux\ntexte\n")
    n2 = mod.main({"session_id": "SID-B", "tool_name": "Write"})
    return n1, n2, lignes(brain)


def conforme(n1, n2, entrees):
    """L'assertion COMPLÈTE — utilisée telle quelle par la preuve positive ET par chaque
    sabotage. Les avoir séparées est ce qui a laissé passer le sabotage « mtime inventée » :
    la contre-épreuve ne comparait que des COMPTES, et deux lignes fausses comptent comme
    deux lignes justes. Un agrégat ne voit pas une permutation."""
    return (n1 == 1 and n2 == 1 and len(entrees) == 2
            and entrees[0]["path"] == "lessons/fixture-une.md"
            and entrees[0]["sid"] == "SID-A" and entrees[0]["outil"] == "Bash"
            and entrees[1]["path"] == "projects/fixture-deux.md"
            and entrees[1]["sid"] == "SID-B" and entrees[1]["outil"] == "Write"
            and all(e["attribution"] == "coincidence" for e in entrees)
            # ecart_s doit être petit quand l'écriture vient d'avoir lieu : c'est lui qui
            # permet de distinguer « cette session a écrit » de « elle a seulement vu ».
            and all(0 <= e["ecart_s"] <= 5 for e in entrees))


def main():
    echecs = []

    # ── 1. PREUVE POSITIVE ────────────────────────────────────────────────────────
    brain = tronc()
    try:
        mod = charger(brain)
        n1, n2, entrees = scenario(mod, brain)
        print("Preuve positive — deux écritures indépendantes, hors outil tracé")
        for e in entrees:
            print("   %s  sid=%-6s outil=%-5s %s" % (e["ts"], e["sid"], e["outil"], e["path"]))
        ok = conforme(n1, n2, entrees)
        print("   %s chemin, session, outil et écart temporel justes, une trace par écriture"
              % ("✅" if ok else "❌"))
        if not ok:
            echecs.append("preuve positive")
        # le premier passage ne doit RIEN journaliser (sinon 500 lignes de bruit au démarrage)
        b2 = tronc()
        m2 = charger(b2)
        ecrire(b2, "lessons/avant.md", "# avant\n")
        m2.main({"session_id": "S", "tool_name": "Bash"})
        vide = lignes(b2) == []
        print("   %s premier passage : arme le jalon, ne journalise rien" % ("✅" if vide else "❌"))
        if not vide:
            echecs.append("premier passage bruyant")
        shutil.rmtree(b2, ignore_errors=True)
    finally:
        shutil.rmtree(brain, ignore_errors=True)

    # ── 2. SABOTAGES — chacun doit rendre la preuve positive ROUGE ────────────────
    print("\nCONTRE-ÉPREUVE — le banc rougit-il quand le mécanisme est cassé ?")
    sabotages = [
        ("le balayage ne voit plus rien",
         lambda m: setattr(m, "fiches_modifiees", lambda depuis: [])),
        ("aucune zone n'est couverte",
         lambda m: setattr(m, "ZONES", ())),
        ("le jalon n'avance jamais",
         lambda m: setattr(m, "_jalon_ecrit", lambda t: None)),
        ("le balayage rend une mtime inventée (ecart_s faux)",
         lambda m: setattr(m, "fiches_modifiees",
                           lambda depuis: [("lessons/fixture-une.md", 0.0)])),
    ]
    for nom, casser in sabotages:
        b = tronc()
        try:
            m = charger(b)
            casser(m)
            try:
                n1, n2, entrees = scenario(m, b)
                rouge = not conforme(n1, n2, entrees)
            except Exception:
                rouge = True
            print("   %s %s" % ("✅" if rouge else "❌ RESTE VERT —", nom))
            if not rouge:
                echecs.append("sabotage muet : " + nom)
        finally:
            shutil.rmtree(b, ignore_errors=True)

    # ── 3. PÉRIMÈTRE DÉCLARÉ — ce que le registre ne voit PAS, par conception ─────
    print("\nPérimètre déclaré (ces absences sont voulues, pas des défauts)")
    b = tronc()
    try:
        m = charger(b)
        m.main({"session_id": "S", "tool_name": "Bash"})
        time.sleep(1.05)
        ecrire(b, "tools/hors-zone.md", "# hors zone\n")
        n = m.main({"session_id": "S", "tool_name": "Bash"})
        print("   %s une écriture hors des cinq zones du savoir n'est pas journalisée"
              % ("✅" if n == 0 else "❌"))
        if n != 0:
            echecs.append("périmètre débordé")
    finally:
        shutil.rmtree(b, ignore_errors=True)

    print()
    if echecs:
        print("❌ BANC ROUGE : " + " · ".join(echecs))
        return 1
    print("✅ BANC VERT — le registre voit une écriture hors outil tracé, "
          "et les quatre sabotages le font rougir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
