#!/usr/bin/env python3
"""brain_racine — la définition unique de « quel Brain suis-je en train de mesurer ? ».

TROIS RACINES, TROIS NOTIONS. Les confondre est le défaut que ce module existe pour
fermer :

    CODE_ROOT   où vivent mes scripts, fixtures, ressources voisines.  → __file__
    BRAIN_ROOT  l'arbre de données que j'agis : corpus, state, cartes. → BRAIN_HOME
    HOME        le foyer de l'utilisateur : Bureau, coffres, sauvegardes. → ~

Sur le tronc de l'auteur, les trois coïncident — et c'est exactement ce qui a rendu le
défaut invisible pendant des mois. Ils divergent dès qu'on clone, qu'on ouvre un worktree,
ou qu'on installe le paquet ailleurs.

POURQUOI UNE PRIMITIVE, ET SEULEMENT MAINTENANT. Le bon patron existait depuis le
2026-08-03 dans `tests/invariants_brain.py:19-23`, avec la bonne raison écrite à côté, et
n'avait jamais été propagé. Au 2026-08-21 il en existe cinq copies inline. Cinq copies d'une
définition, c'est cinq occasions de diverger : `grep -l "def racine"` ne rendait rien.

RÈGLE (spec gelée du 2026-08-20, clauses 1 à 5) :
    1. `realpath` obligatoire — le symlink ~/.claude/projects/…/memory donne deux chemins
       pour un seul arbre, et deux chemins font deux racines.
    2. jamais `~/.c-brain/trunk` littéral — mesuré : 7 sites qu'aucune variable ne détournait.
    3. jamais le `cwd` — il n'a aucun effet aujourd'hui ; créer la dépendance serait un recul.
    4. `BRAIN_HOME` défini mais VIDE ≡ absent — mesuré le 2026-08-20.
    5. une seule implémentation — ce fichier.
"""
import os


def brain_root(depuis=None):
    """Racine canonique du Brain MESURÉ.

    `depuis` : un chemin du module appelant (typiquement `__file__`). Il ne sert QUE de
    repli, pour trouver le dépôt qui héberge le code quand personne n'a demandé de Brain
    explicite. Il ne prime jamais sur `BRAIN_HOME`."""
    demande = os.environ.get("BRAIN_HOME")
    if demande:                                   # "" est faux : clause 4
        return os.path.realpath(demande)
    ancre = depuis or __file__
    return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(ancre)), ".."))


def code_root(depuis):
    """Racine du CODE appelant. Légitime, et distincte du Brain : c'est là que vivent les
    fixtures, les scripts voisins, les ressources du programme. Ne jamais l'utiliser comme
    identité du Brain simplement parce que les deux coïncident sur le tronc auteur."""
    return os.path.dirname(os.path.abspath(depuis))
