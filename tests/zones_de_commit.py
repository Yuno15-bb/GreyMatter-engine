#!/usr/bin/env python3
"""BANC — les zones de commit : une seule table, et l'exception skills instruite.

DEUX CONCEPTS DIFFÉRENTS, ET C'EST VOULU
    La « zone » du pre-commit répond à : *qu'est-ce qui n'a aucune raison d'être commité
    ensemble ?* — c'est une question de RÉCIT. L'« univers canonique » de
    `tools/nettoyage/univers.py` répond à : *qu'est-ce qui est un objet de connaissance
    référençable ?* — c'est une question d'IDENTITÉ. La preuve qu'ils ne se confondent pas :
    `agents/` est en zone **savoir** et pourtant EXCLU de l'univers (« acteur du système, pas
    un objet de connaissance »). Ce banc ne cherche donc pas à les aligner.

CE QU'IL VÉRIFIE, ET POURQUOI
    1. Les DEUX tables — celle du hook shell et sa copie Python dans `commit_par_zone.py` —
       disent la même chose. Le commentaire de ce dernier affirme « on emploie SA table, pas
       une copie qui divergerait au premier dossier nouveau » : c'est faux, c'est bien une
       copie. Tant qu'elle existe, il faut un contrôle qui rougisse quand elles s'écartent.
    2. `skills/` est en zone **savoir**. Ce n'était pas un choix mais un OUBLI, mesuré : le
       commit `6aedfb2` du 2026-08-15 s'intitule « les skills entrent dans le Brain — même
       patron que les agents », et n'a pas touché la table où `agents/` figure déjà.
    3. Le hook installé et sa version versionnée sont identiques — sinon le dépôt documente
       une règle que la machine n'applique pas.
"""
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
HOOK_VERSIONNE = os.path.join(BRAIN, "tools", "git-hooks", "pre-commit")
HOOK_INSTALLE = os.path.join(BRAIN, ".git", "hooks", "pre-commit")
COMMIT_PAR_ZONE = os.path.join(BRAIN, "hooks", "commit_par_zone.py")


def table_shell(chemin):
    """{préfixe: zone} lu dans le `case` de la fonction zone() du hook."""
    txt = open(chemin, encoding="utf-8").read()
    m = re.search(r"^zone\(\) \{(.*?)^\}", txt, re.S | re.M)
    if not m:
        return {}
    out = {}
    for motifs, zone in re.findall(r"^\s*([^\n)]*?)\)\s*echo \"(\w+)\"", m.group(1), re.M):
        for motif in motifs.split("|"):
            motif = motif.strip()
            if motif and motif != "*":
                out[motif.rstrip("*")] = zone
    return out


def table_python(chemin):
    """{préfixe: zone} lu dans la constante ZONES de commit_par_zone.py."""
    txt = open(chemin, encoding="utf-8").read()
    m = re.search(r"^ZONES = \((.*?)\)\n", txt, re.S | re.M)
    if not m:
        return {}
    return {p: z for p, z in re.findall(r'\("([^"]+)",\s*"(\w+)"\)', m.group(1))}


def main():
    echecs = []
    shell = table_shell(HOOK_VERSIONNE)
    py = table_python(COMMIT_PAR_ZONE)
    print("Les deux tables de zones")
    print("   hook shell : %d préfixes · commit_par_zone : %d préfixes" % (len(shell), len(py)))
    ecarts = sorted(set(shell.items()) ^ set(py.items()))
    if ecarts:
        print("   ❌ elles divergent : %s" % ecarts)
        echecs.append("tables divergentes")
    else:
        print("   ✅ elles disent exactement la même chose")

    print("\nL'exception skills, instruite le 2026-08-28")
    for prefixe, attendu in (("skills/", "savoir"), ("agents/", "savoir")):
        lu = shell.get(prefixe) or py.get(prefixe)
        ok = lu == attendu
        print("   %s %-9s -> %s" % ("✅" if ok else "❌ %r au lieu de" % lu, prefixe, attendu))
        if not ok:
            echecs.append("%s n'est pas en zone %s" % (prefixe, attendu))

    print("\nLe hook installé applique bien la règle versionnée")
    if not os.path.exists(HOOK_INSTALLE):
        print("   ⓘ hook non installé sur cette machine — contrôle sans objet")
    else:
        a = open(HOOK_VERSIONNE, "rb").read()
        b = open(HOOK_INSTALLE, "rb").read()
        print("   %s identiques octet pour octet" % ("✅" if a == b else "❌"))
        if a != b:
            echecs.append("le hook installé diverge du versionné")

    print("\nCe que ce banc NE dit PAS")
    print("   zone de commit ≠ objet de connaissance : `agents/` est en zone savoir et")
    print("   pourtant exclu de l'univers canonique. Les deux découpages restent distincts.")

    print()
    if echecs:
        print("❌ BANC ROUGE : " + " · ".join(echecs))
        return 1
    print("✅ BANC VERT — une seule table, skills en zone savoir, hook installé conforme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
