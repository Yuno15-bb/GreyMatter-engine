#!/usr/bin/env python3
"""motif_process_ancre — « aucun processus » n'est une preuve que si on a cherché au bon endroit.

POURQUOI CE BANC EXISTE (mesuré le 2026-09-20, entrée C3 de C bis)
    Chercher un processus est une MESURE, et une mesure a une cible. Quand la cible est
    écrite en dur — un fragment de chemin qui nomme un arbre, `claude-brain/capsule/…` —
    la mesure est juste dans cet arbre-là et silencieusement fausse partout ailleurs.

    Le cas réel : `hooks/auto_maintain.py` cherchait la capsule avec le motif
    `"claude-brain/capsule/node_modules/electron"`. Le paquet publié porte
    `"c-brain/trunk/capsule/node_modules/electron"`, qui vise l'installé (~/.c-brain/trunk)
    et ne matche NI ~/c-brain NI le plan de travail ~/c-brain-fr. Là, `pgrep` rend zéro sur
    une capsule bien vivante, le code conclut « rien ne tourne » et en relance une
    par-dessus. L'absence de processus avait été prise pour une preuve d'absence.

    C'est le troisième passage de la même famille — voir la leçon
    `pkill-motif-approximatif-mesure-une-instance-perimee`, qui le dit déjà : calibrer
    DANS LES DEUX SENS, 1 quand la cible tourne, 0 quand elle ne tourne pas.

CE QUE CE BANC VÉRIFIE — une propriété, lue dans les sources, indépendante de la machine
    Tout motif passé à `pgrep` ou `pkill` dans le code du Brain est ANCRÉ : il ne contient
    ni nom d'arbre écrit en dur (`claude-brain/`, `c-brain/`, `.c-brain/`) ni chemin absolu
    de cette machine (`/Users/…`). Un motif volontairement large et sans nom d'arbre —
    `pgrep -fl "capsule/node_modules"`, qui sert à retrouver N'IMPORTE QUELLE instance sur
    le Mac — est légitime et passe.

CE QU'IL NE VÉRIFIE PAS
    Que le motif ancré matche vraiment le processus visé : ça se calibre à la main, sur une
    cible vivante puis sur une cible absente, et aucun banc ne peut le faire sans lancer le
    programme. Il ne vérifie pas non plus que le code LIT le code de retour de `pgrep` :
    rc=0 trouvé, rc=1 rien, rc≥2 ÉCHEC — et dans ce dernier cas la sortie est vide elle
    aussi. `hooks/auto_maintain.py` refuse désormais de conclure sur rc≥2 ; les autres
    appels n'ont pas de garde équivalent.
"""
import ast
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.join(ICI, ".."))

ZONES = ["hooks", "tools", "tests", "capsule", "companion", "cbrain"]
# Ce qu'on ne lit pas : dépendances, caches, corpus de données et bacs de projection.
IGNORE = ("/node_modules/", "/__pycache__/", "/.git/", "/projection/bac/",
          "/captures/", "/admin-L1/", "/heldout/")

APPEL = re.compile(r"\b(pgrep|pkill)\b")
# Les noms d'arbre écrits en dur, et tout chemin absolu de cette machine.
EN_DUR = re.compile(r"\.?c(?:laude)?-brain/|/Users/|/home/")


def fichiers():
    for zone in ZONES:
        for dossier, _, noms in os.walk(os.path.join(BRAIN, zone)):
            for nom in noms:
                p = os.path.join(dossier, nom)
                if nom.endswith((".py", ".js", ".sh", ".mjs", ".zsh")) \
                        and not any(x in p for x in IGNORE):
                    yield p


def motifs_python(src):
    """(ligne, texte) pour chaque motif passé à pgrep/pkill, LITTÉRAL OU NOMMÉ.

    ⚠️ C'EST ICI QUE LA PREMIÈRE VERSION DE CE BANC ÉTAIT AVEUGLE (2026-09-20). Elle
    ne lisait que les lignes contenant le mot `pgrep`, alors que le vrai défaut
    s'écrit sur DEUX lignes : `MOTIF_CAPSULE = "claude-brain/capsule/…"` en tête de
    module, `subprocess.run(["pgrep", "-f", MOTIF_CAPSULE])` deux cents lignes plus
    bas. Le sabotage S1 — remettre le vrai bug — laissait le banc VERT. Il faut donc
    suivre la variable jusqu'à son affectation, pas regarder une ligne."""
    try:
        arbre = ast.parse(src)
    except SyntaxError:
        return []
    constantes = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            for c in n.targets:
                if isinstance(c, ast.Name):
                    constantes[c.id] = (n.lineno, n.value.value)
    out = []
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.List, ast.Tuple)) or not n.elts:
            continue
        tete = n.elts[0]
        if not (isinstance(tete, ast.Constant) and isinstance(tete.value, str)
                and APPEL.search(tete.value)):
            continue
        for e in n.elts[1:]:
            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                out.append((e.lineno, e.value))
            elif isinstance(e, ast.Name) and e.id in constantes:
                ligne, val = constantes[e.id]
                out.append((ligne, f"{e.id} = {val!r}  (passé à {tete.value} ligne {e.lineno})"))
    return out


def motifs_texte(lignes):
    """Shell, JavaScript : la ligne d'appel, et l'affectation des variables qu'elle cite."""
    out, noms = [], set()
    for n, ligne in enumerate(lignes, 1):
        if APPEL.search(ligne):
            out.append((n, ligne.strip()[:110]))
            noms.update(re.findall(r"\$\{?([A-Za-z_][A-Za-z_0-9]*)", ligne))
            noms.update(re.findall(r"\b([A-Z][A-Z_0-9]{2,})\b", ligne))
    for n, ligne in enumerate(lignes, 1):
        m = re.match(r"\s*(?:const |let |var )?([A-Za-z_][A-Za-z_0-9]*)\s*=", ligne)
        if m and m.group(1) in noms:
            out.append((n, ligne.strip()[:110]))
    return out


def main():
    check = "--check" in sys.argv
    fautifs, vus, lus = [], 0, 0
    for p in fichiers():
        try:
            src = open(p, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if not APPEL.search(src):
            continue
        lus += 1
        # Le fichier qui énonce la règle a le droit de citer les motifs fautifs.
        if os.path.abspath(p) == os.path.abspath(__file__):
            continue
        trouves = motifs_python(src) if p.endswith(".py") else motifs_texte(src.split("\n"))
        vus += len(trouves)
        for n, texte in trouves:
            if EN_DUR.search(texte):
                fautifs.append((os.path.relpath(p, BRAIN), n, texte))

    if fautifs:
        print("⛔ un motif de recherche de processus nomme un arbre en dur. Dans tout autre"
              " arbre il ne matchera rien, `pgrep` rendra zéro sur une cible VIVANTE, et"
              " cette absence sera prise pour une preuve d'absence :")
        for f, n, texte in sorted(set(fautifs)):
            print(f"     · {f}:{n} — {texte}")
        print("   Ancrer sur la racine du Brain (os.path.join(BRAIN, …), $BRAIN_HOME),"
              " ou retirer le nom d'arbre si la recherche est volontairement large.")
        return 1

    if not check:
        print(f"✅ motifs de processus ancrés — {vus} motif(s) suivis dans {lus} fichier(s)"
              f" qui appellent pgrep/pkill, aucun ne nomme un arbre en dur")
    return 0


if __name__ == "__main__":
    sys.exit(main())
