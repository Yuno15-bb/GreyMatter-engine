#!/usr/bin/env python3
"""brain_corpus — LA définition du corpus indexable du tronc. Source UNIQUE.

POURQUOI CE FICHIER EXISTE (2026-08-16). Cette définition vivait en DEUX exemplaires :
une dans `brain_recall.py` (BM25), une dans `brain_embed.py` (embeddings), la seconde
portant le commentaire « MÊME corpus que brain_recall ». Elles ont divergé le 2026-08-15,
le jour où les 24 compétences sont entrées dans le tronc :

    brain_recall  393 documents      (skills/ exclu)
    brain_embed   458 documents      (skills/ indexé — 65 fiches d'outillage)

Personne ne l'a vu, parce que rien ne comparait les deux. Le commentaire affirmait la
parité au lieu de la garantir — et un commentaire ne rougit jamais.

CE QUE ÇA CASSAIT. Toute comparaison BM25 / embeddings mesurait deux CORPUS différents en
croyant comparer deux méthodes de récupération. Le duel en aveugle de l'ADR-0001 a été
tranché AVANT cette divergence ; le rejouer tel quel aujourd'hui rendrait un verdict faux.

LA RÈGLE. Aucun moteur ne redéfinit cette liste. On l'importe.
`tests/corpus_partage.py` refuse tout module qui s'en écrirait une copie locale.
cf. [[un-detecteur-partage-par-concept]]
"""
import glob
import os

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))

# On exclut du corpus les couches BRUTES/infra — le rappel doit remonter le savoir DISTILLÉ
# (projects/lessons/meta/life), pas les catalogues d'agents, l'état ni le corpus froid.
#   • sessions/ : TIMELINE.md = index de 80+ sessions, si long qu'il matche presque tout → bruit.
#   • corpus/   : couche froide (milliers de conversations importées) → noierait le top-k. cf. carte-vivante
# Matché par SEGMENTS de dossier (pas en substring : sinon une fiche « capsule-… » ou « …-sessions »
# serait exclue à tort, comme l'ancien bug). cf. [[bm25-recall-exclure-index-catalogues]]
#   • tools/    : outillage. Le banc de valeur y garde des COPIES du tronc pour ses
#     conditions ; sans cette exclusion chaque fiche était indexée 5 fois (1 573 docs
#     au lieu de 312), ce qui fausse l'IDF de tout le corpus et donc tous les scores.
SKIP_DIRS = {
    ".git", "node_modules", "capsule", "capsule-v2", "corpus", "audits",
    "agents", "state", "tools",
    #   • skills/ : entré dans le tronc le 2026-08-15 (les 24 compétences vivent
    #     désormais ici, `~/.claude/skills` est un symlink). Ce sont des MODES
    #     D'EMPLOI et leurs références — de l'outillage, comme `agents/` juste
    #     au-dessus, pas du savoir distillé. Mesuré à chaud : sans cette ligne,
    #     438 docs indexés dont **65 venant de skills/** (15 % du corpus), et le
    #     rappel proposait `skills/blender-motion/references/fcurve-modifiers.md`
    #     sur la requête « pousse les modifs ». Le déplacement dans le tronc et
    #     l'exclusion du rappel doivent aller ENSEMBLE : ranger une couche
    #     d'outillage dans le Brain sans l'exclure ici la fait concurrencer les
    #     fiches. Les skills restent trouvables par leur fiche,
    #     [[systeme-skills-standard]]. cf. [[ce-qui-vit-dans-la-config-ne-vit-pas-dans-le-brain]]
    #     ⚠️ C'est CETTE ligne que brain_embed.py n'avait pas — la divergence de 65 docs.
    "skills",
    # `archive/` = la couche FROIDE (journaux détachés des fiches, cf.
    # tools/archiver-journal.py). Mesuré le 2026-08-14 : sans cette ligne, un
    # journal archivé ressortait **en 1re position** devant la fiche courante —
    # ranger l'historique au froid n'a aucun sens s'il continue de concurrencer
    # le présent dans la recherche. Sur disque et dans git, hors du rappel.
    "archive",
}
SKIP_PREFIX = ("sessions",)
SKIP_FILES = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}


def skip(rel):
    """Ce chemin relatif est-il hors du corpus ?"""
    if rel in SKIP_FILES or any(rel.startswith(p) for p in SKIP_PREFIX):
        return True
    dirs = rel.split(os.sep)[:-1]               # segments de DOSSIER (hors nom de fichier)
    return any(d in SKIP_DIRS for d in dirs)


def indexable(brain=None):
    """Les .md du corpus, triés — (chemin relatif, chemin absolu).

    Le tri n'est pas cosmétique : c'est l'entrée de l'empreinte du cache d'index de
    brain_recall. Un ordre instable rejetterait le cache à chaque appel.
    """
    racine = brain or BRAIN
    out = []
    for p in glob.glob(os.path.join(racine, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, racine)
        if not skip(rel):
            out.append((rel, p))
    out.sort()
    return out


if __name__ == "__main__":
    docs = indexable()
    print(f"{len(docs)} documents dans le corpus indexable de {BRAIN}")
