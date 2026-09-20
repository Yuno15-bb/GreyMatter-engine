#!/usr/bin/env python3
"""
extrait_obligatoire.py — E1 « pas d'extrait, pas de fait », rendu réfutable.

CE QU'IL PROUVE. `agents/narcissus.md`, section « MISSION — distillateur », demande depuis le 2026-09-18 que chaque fait
porte l'extrait exact de sa source. Une consigne est une prose, et **une prose ne rougit
jamais** : tant qu'aucun contrôle ne refuse une fiche sans extrait, la règle n'existe que
sur le papier. Ce banc monte un tronc jetable, y ajoute des fiches, et vérifie que le
garde-fou du commit (`tests/provenance_fiches.py --check --nouvelles`) dit NON quand il
doit dire non — et se tait quand il doit se taire.

POURQUOI UN DÉPÔT GIT JETABLE. La barrière lit `git diff --cached` : sans index, elle ne
voit aucune fiche « ajoutée » et passerait au vert quoi qu'on écrive. Un banc qui ne peut
pas rougir ne protège de rien (lessons/test-d-equivalence-vert-aussi-quand-le-code-est-
inerte.md). On fabrique donc un vrai dépôt, dans /tmp, jamais le tronc vivant.

LES DEUX MUETS COMPTENT AUTANT QUE LES ROUGES. Un contrôle qui rougit sur tout est aussi
inutile qu'un contrôle qui ne rougit sur rien : il se désactive au premier commit gênant.
Les cas « muet » vérifient les deux exemptions assumées — `kind: unknown` n'a rien à citer,
et les fiches déjà en place ne sont pas rattrapées.

VÉRIFIER LE MOTIF, PAS SEULEMENT LA COULEUR. Chaque rouge attendu doit mentionner « E1 » :
sans ça, un refus pour provenance absente passerait pour une preuve de ce banc.

Lancer :
  python3 tests/extrait_obligatoire.py
  python3 tests/extrait_obligatoire.py --check
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BARRIERE = os.path.join(ICI, "provenance_fiches.py")

AVEC_EXTRAIT = """---
title: Le cache du lecteur PDF garde l'ancienne version
description: "Réécrire un PDF au même chemin peut laisser Aperçu afficher la version d'avant."
topic: outillage-et-environnement
provenance:
  kind: internal_experience
  ref: "sessions/archive/2026-09-18-essai.md"
  captured_at: 2026-09-18
  extrait: "constaté le 31/08, reproduit à l'identique le 01/09"
authority:
  validated: false
  scope: repository
  confidence: medium
---

Réécrire un PDF au même chemin laisse parfois le lecteur afficher la version précédente.

## Correctif

Changer le nom du fichier à chaque rendu, ou vider le cache avant de regarder.
"""

SANS_ORIGINE = """---
title: Une note dont l'origine s'est perdue
description: "Un fait ancien, dont personne ne sait plus d'où il sort."
topic: outillage-et-environnement
provenance:
  kind: unknown
---

Le corps de la fiche, sans intérêt pour ce banc.
"""


def env_propre(**ajouts):
    """L'environnement DÉBARRASSÉ de tout ce que git y pose quand il appelle un hook.

    LE DÉFAUT QUE CETTE FONCTION FERME — mesuré le 2026-09-19, en production.
    Ce banc monte un dépôt jetable dans /tmp et y lance `git init`, `git add -A`,
    `git commit`. Lancé à la main, c'est hermétique. Lancé PAR LE PRE-COMMIT, ça ne
    l'est plus : git exporte `GIT_INDEX_FILE` et `GIT_DIR` vers ses hooks, et un
    `subprocess` en hérite. Le `git add -A` du dépôt jetable écrivait donc
    `lessons/fiche-ancienne.md` dans l'index DU VRAI DÉPÔT, avec une empreinte qui
    n'existe nulle part dans sa base d'objets.

    Conséquence observée : tout commit passant par le hook mourait sur
    « error: invalid object 100644 176d280d… for 'lessons/fiche-ancienne.md' /
    error: Error building trees » — un message qui ne nomme ni le banc, ni la cause,
    et qui survivait à `git reset` puisque la pollution était reposée à chaque essai.
    Les quatre zones étaient refusées d'affilée sans qu'aucun banc ne rougisse.

    `cwd=` ne protège de rien : `GIT_DIR` prime sur le répertoire courant. C'est
    l'environnement qu'il faut nettoyer, pas le chemin.
    """
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e.update(ajouts)
    return e


def tronc_jetable():
    """Un dépôt git neuf, avec UNE fiche déjà commitée : le passé, qu'on ne rattrape pas."""
    d = tempfile.mkdtemp(prefix="banc-extrait-")
    for sous in ("projects/socle", "lessons", "meta", "state"):
        os.makedirs(os.path.join(d, sous), exist_ok=True)
    ecrire(d, "lessons/fiche-ancienne.md", AVEC_EXTRAIT.replace(
        '  extrait: "constaté le 31/08, reproduit à l\'identique le 01/09"\n', ""))
    for cmd in (["git", "init", "-q"],
                ["git", "config", "user.email", "banc@local"],
                ["git", "config", "user.name", "Banc"],
                ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "le passé"]):
        subprocess.run(cmd, cwd=d, env=env_propre(), capture_output=True, text=True)
    return d


def ecrire(d, rel, txt):
    open(os.path.join(d, rel), "w", encoding="utf-8").write(txt)


def stager(d, rel, txt):
    """Écrit une fiche ET la met dans l'index : c'est l'index que la barrière regarde."""
    ecrire(d, rel, txt)
    subprocess.run(["git", "add", rel], cwd=d, env=env_propre(),
                   capture_output=True, text=True)


def verdict(d):
    """Ce que dirait le pre-commit sur ce tronc-là : (code de sortie, texte affiché)."""
    r = subprocess.run([sys.executable, BARRIERE, "--check", "--nouvelles"],
                       cwd=d, env=env_propre(BRAIN_HOME=d),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


CAS = []


def cas(nom, doit_rougir, motif=None):
    def deco(f):
        CAS.append((nom, doit_rougir, motif, f))
        return f
    return deco


@cas("fiche neuve AVEC son extrait", False)
def _c1(d):
    stager(d, "lessons/fiche-neuve.md", AVEC_EXTRAIT)


@cas("fiche neuve SANS ligne extrait", True, "E1")
def _c2(d):
    stager(d, "lessons/fiche-neuve.md", AVEC_EXTRAIT.replace(
        '  extrait: "constaté le 31/08, reproduit à l\'identique le 01/09"\n', ""))


@cas("extrait présent mais VIDE", True, "E1")
def _c3(d):
    stager(d, "lessons/fiche-neuve.md", AVEC_EXTRAIT.replace(
        '"constaté le 31/08, reproduit à l\'identique le 01/09"', '""'))


@cas("extrait fait de blancs", True, "E1")
def _c4(d):
    stager(d, "lessons/fiche-neuve.md", AVEC_EXTRAIT.replace(
        '"constaté le 31/08, reproduit à l\'identique le 01/09"', '"   "'))


@cas("origine déclarée inconnue, sans extrait — exemption assumée", False)
def _c5(d):
    stager(d, "lessons/fiche-neuve.md", SANS_ORIGINE)


@cas("fiche ancienne sans extrait, non ajoutée — pas de rattrapage", False)
def _c6(d):
    pass  # rien n'est ajouté : seule la fiche déjà commitée existe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    print(f"E1 — l'extrait obligatoire, {len(CAS)} cas\n")
    ennuis = []
    for nom, doit_rougir, motif, f in CAS:
        d = tronc_jetable()
        try:
            # Le tronc doit être VERT avant le sabotage, sinon le rouge ne prouve rien.
            code0, _ = verdict(d)
            if code0 != 0:
                ennuis.append(f"{nom} : le tronc d'essai rougit AVANT le sabotage")
                continue
            f(d)
            code, texte = verdict(d)
            rouge = code != 0
            if rouge != doit_rougir:
                attendu = "rouge" if doit_rougir else "vert"
                ennuis.append(f"{nom} : attendu {attendu}, obtenu "
                              f"{'rouge' if rouge else 'vert'}")
            elif doit_rougir and motif and motif not in texte:
                ennuis.append(f"{nom} : rouge, mais pour un autre motif que « {motif} »")
            etat = "ROUGE" if rouge else "vert "
            ok = "✅" if not [e for e in ennuis if e.startswith(nom)] else "❌"
            print(f"  {ok} {etat}  {nom}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print(f"\n  {len(CAS) - len(ennuis)}/{len(CAS)} cas conformes")
    for e in ennuis:
        print(f"     ↳ {e}")
    if a.check and ennuis:
        print("\n❌ E1 n'est pas tenu par un contrôle : la consigne reste une prose")
        return 1
    if a.check:
        print("\n✅ une fiche neuve sans extrait est refusée, et seulement celle-là")
    return 0


if __name__ == "__main__":
    sys.exit(main())
