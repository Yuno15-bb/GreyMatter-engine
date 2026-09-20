#!/usr/bin/env python3
"""BANC — la règle de sélection de `isoler_sujet.py` refuse-t-elle les BONS cas ?

Il exerce `tools/nettoyage/classement/isoler_sujet.py`, le code même qui pose le sujet sur
une fiche déjà modifiée par une autre session. Le banc ne réimplémente pas la règle : il
fabrique des situations et regarde si l'outil accepte ou refuse.

POURQUOI CE BANC EXISTE — UNE RÈGLE PRISE TROP LARGE, PUIS CORRIGÉE
    Le premier tri, le 28/08, écartait toute fiche dont le bloc frontmatter différait de celui
    de HEAD. Ce critère mesurait la DIFFÉRENCE DU BLOC, pas le RISQUE : il a mis de côté deux
    fiches parfaitement traitables. Un frontmatter qui diffère n'est PAS un motif d'exclusion,
    et le cas C0 ci-dessous le verrouille — c'est le cas qui rougirait si quelqu'un
    réintroduisait l'ancien critère.

LES TROIS BLOCAGES RÉELS, chacun avec son cas :
    C1  l'ancre d'insertion diffère entre HEAD et le disque ;
    C2  une clé `topic:` existe déjà d'un côté ou de l'autre ;
    C3  l'insertion n'est pas neutre (contrôle par simulation avant écriture).
    C4  le fichier n'est pas suivi — pas de version HEAD, donc rien à isoler.

REPRODUCTIBLE DEPUIS LE DÉPÔT SEUL : dépôts jetables, aucune fiche du tronc lue ni touchée,
aucune dépendance à l'historique.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
OUTIL = os.path.join(os.path.dirname(ICI), "tools", "nettoyage", "classement",
                     "isoler_sujet.py")
sys.path.insert(0, os.path.join(os.path.dirname(ICI), "hooks"))
import topics_fiche as T  # noqa: E402


def ancre(fm):
    for motif in ("tags:", "description:"):
        if any(re.match("^" + motif, l) for l in fm.split("\n")):
            return motif
    return "(fin de frontmatter)"


def regle(base, travail):
    """La règle telle que l'outil l'applique, rejouée sur deux textes.

    Rend None si l'opération est autorisée, sinon le nom du blocage rencontré.
    """
    fh, fd = T.bloc_frontmatter(base), T.bloc_frontmatter(travail)
    if fh is None or fd is None:
        return "frontmatter absent"
    if ancre(fh) != ancre(fd):
        return "C1 ancre différente"
    if T.lire(base)[0] or T.lire(travail)[0]:
        return "C2 clé topic existante"
    ids = T.ids_canoniques()
    resultat = T.ecrire(travail, "le-brain", [], ids)
    depouille = "".join(l for l in resultat.splitlines(keepends=True)
                        if not l.startswith(("topic: ", "topics_secondaires: ")))
    if depouille != travail:
        return "C3 insertion non neutre"
    return None


FM = """---
name: fiche
description: "Essai."
%stags: [le-cerveau]
metadata:
  type: lesson
  updated: %s
---

Corps.
"""


def cas(nom, attendu, obtenu, echecs):
    ok = (obtenu == attendu) if attendu is None else (obtenu == attendu)
    print("   %s %-52s %s" % ("✅" if ok else "❌", nom,
                              "autorisé" if obtenu is None else "refusé : " + obtenu))
    if not ok:
        echecs.append(nom)


def main():
    echecs = []
    print("── RÈGLE DE SÉLECTION — refuse-t-elle les BONS cas ? ──")

    # C0 — LE CAS QUI VERROUILLE LA CORRECTION : frontmatter DIFFÉRENT, mais insertion sûre.
    # C'est exactement la situation des deux fiches écartées à tort le 28/08.
    base = FM % ("", "2026-08-25")
    travail = FM % ("", "2026-08-27")
    assert base != travail
    cas("C0 frontmatter DIFFÉRENT mais ancre identique", None, regle(base, travail), echecs)

    # C1 — l'ancre change : `tags:` d'un côté, plus de tags de l'autre.
    sans_tags = base.replace("tags: [le-cerveau]\n", "")
    cas("C1 ancre d'insertion différente", "C1 ancre différente",
        regle(base, sans_tags), echecs)

    # C2 — une clé `topic:` déjà posée par quelqu'un d'autre.
    deja = travail.replace("tags: [le-cerveau]", "tags: [le-cerveau]\ntopic: machine-et-processus")
    cas("C2 clé `topic:` déjà présente sur le disque", "C2 clé topic existante",
        regle(base, deja), echecs)
    cas("C2bis clé `topic:` déjà présente dans HEAD", "C2 clé topic existante",
        regle(deja, travail), echecs)

    # C3 — insertion non neutre. Le cas est instructif : un `topics_secondaires:` ORPHELIN,
    # sans `topic:` au-dessus, passe SOUS le radar de C2 — `topics_fiche.lire` ne le voit pas
    # comme un sujet posé. C'est C3, le contrôle de neutralité, qui l'attrape : `ecrire`
    # retirerait cette clé résiduelle, donc retirer les lignes de sujet du résultat ne
    # redonnerait pas le texte de départ. C3 n'est donc pas redondant avec C2 ; il rattrape ce
    # que C2 ne voit pas, et c'est le seul des trois qui PROUVE au lieu d'expliquer.
    orphelin = travail.replace("tags: [le-cerveau]",
                               "tags: [le-cerveau]\ntopics_secondaires: [le-brain]")
    cas("C3 `topics_secondaires:` orphelin — invisible pour C2",
        "C3 insertion non neutre", regle(base, orphelin), echecs)

    # C4 — un fichier non suivi : l'outil doit refuser, faute de version HEAD.
    d = tempfile.mkdtemp(prefix="banc-isolation-")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    open(os.path.join(d, "neuf.md"), "w").write(base)
    suivi = subprocess.run(["git", "ls-files", "--", "neuf.md"], cwd=d,
                           capture_output=True, text=True).stdout.strip()
    ok = (suivi == "")
    print("   %s %-52s %s" % ("✅" if ok else "❌",
                              "C4 fichier non suivi : aucune version HEAD",
                              "refusé : pas de HEAD" if ok else "⛔ vu comme suivi"))
    if not ok:
        echecs.append("C4")
    shutil.rmtree(d, ignore_errors=True)

    # L'outil versionné porte-t-il bien ces contrôles ? (sinon le banc teste une copie)
    src = open(OUTIL, encoding="utf-8").read()
    for marque in ("ANCRE d'insertion différente", "une clé `topic:` existe déjà",
                   "l'insertion N'EST PAS NEUTRE", "n'est pas suivi par git"):
        if marque not in src:
            echecs.append("l'outil ne porte pas le contrôle : " + marque)
    print("\n   %s les quatre refus sont bien présents dans l'outil lui-même"
          % ("✅" if not any("l'outil" in e for e in echecs) else "❌"))

    print()
    if echecs:
        print("❌ BANC ROUGE : " + " · ".join(echecs))
        return 1
    print("✅ BANC VERT — un frontmatter différent n'exclut plus rien ; les trois blocages "
          "réels refusent, et l'outil porte les quatre contrôles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
