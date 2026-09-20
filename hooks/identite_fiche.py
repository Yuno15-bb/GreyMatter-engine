#!/usr/bin/env python3
"""
identite_fiche — la SEULE définition de « quel est l'identifiant logique de ce fichier ».

POURQUOI CE FICHIER EXISTE. Le tronc dérive partout l'identité d'une fiche de son nom de
fichier : `basename[:-3]`. C'est vrai pour `projects/`, `lessons/`, `life/`, `meta/`. Ce
n'est PAS vrai pour `skills/`, et le 2026-08-25 cette différence a cassé les 24 skills de
l'auteur.

CE QUI S'EST PASSÉ, ET POURQUOI C'ÉTAIT INÉVITABLE. Un agent a voulu faire entrer les
skills dans le graphe du Brain. Il a ajouté `skills` à `LINKED_DIRS` de `brain_doctor`.
Le doctor a alors appliqué sa règle générale à `skills/design/SKILL.md` :
`base = "SKILL"`, comparé au `name: design` du frontmatter → violation ; et
`re.fullmatch(r"[a-z0-9-]+", "SKILL")` → violation aussi. **Renommer le fichier en
`design.md` était le SEUL moyen de satisfaire le doctor.** L'agent l'a fait, deux fois, et
les 24 skills sont devenus introuvables pour Claude Code, qui exige `SKILL.md`.

Ce n'était donc pas une maladresse : c'était une contrainte contradictoire non tranchée.

LA DÉCISION (l'auteur, 2026-08-27) : **la contrainte externe fait autorité sur la forme
physique.** Claude Code exige `skills/<slug>/SKILL.md` ; le Brain ne casse pas cette
convention pour satisfaire son propre indexeur. C'est l'indexeur qui apprend.

    physique   skills/design/SKILL.md
    identité   design                    ← le nom du DOSSIER, pas du fichier

UNE SEULE REPRÉSENTATION INDEXABLE. Si `SKILL.md` et `design.md` coexistent, ce n'est pas
« deux fiches » ni « une fiche indexée deux fois » : c'est un CONFLIT, et il se signale.
Indexer les deux en silence donnerait 48 identités pour 24 skills, et une résolution de
`[[design]]` qui dépend de l'ordre de parcours du disque.

POURQUOI ICI ET PAS DANS CHAQUE CONSOMMATEUR. Une douzaine d'endroits calculent
`basename[:-3]`. Recopier la règle dans chacun garantirait qu'ils divergent au premier
dossier nouveau — c'est déjà l'argument de `commit_par_zone` pour sa table de zones. Une
définition, plusieurs importateurs.
"""
import os

# Familles dont l'identité vient du DOSSIER et non du fichier, avec le nom canonique
# imposé par l'outil extérieur.
FAMILLES_A_DOSSIER = {"skills": "SKILL.md"}

# Sous-dossiers qui ne sont pas des fiches : des ressources internes d'une famille.
DOSSIERS_RESSOURCE = {"_refs", "references", "assets", "scripts"}

# Outillage : jamais du savoir. Trouvé par la mesure, pas prévu — un `.venv` dans
# `skills/video-merge/` faisait entrer `numpy/random/LICENSE.md` comme « représentation
# concurrente du skill video-merge ». Un scanner qui descend dans un virtualenv indexe
# les dépendances de quelqu'un d'autre.
DOSSIERS_OUTILLAGE = {".venv", "venv", "node_modules", "__pycache__", ".git",
                      "site-packages", ".tox", "dist", "build", ".pytest_cache"}


def identite(rel):
    """Chemin relatif au tronc → (slug, canonique, motif).

    slug      identité logique, ou None si ce fichier n'est pas une fiche du tout ;
    canonique True si c'est LA représentation à indexer ;
    motif     pourquoi il ne l'est pas, quand il ne l'est pas.
    """
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if not rel.endswith(".md"):
        return None, False, "pas un .md"
    zone = parts[0]
    fichier = parts[-1]

    if zone in FAMILLES_A_DOSSIER:
        if len(parts) < 3:
            # `skills/quelquechose.md` — hors du schéma dossier/SKILL.md
            return None, False, "hors du schéma %s/<slug>/%s" % (zone, FAMILLES_A_DOSSIER[zone])
        dossier = parts[1]
        intermediaires = set(parts[1:-1])
        if intermediaires & DOSSIERS_OUTILLAGE:
            return None, False, "outillage (%s)" % ", ".join(sorted(intermediaires & DOSSIERS_OUTILLAGE))
        if dossier in DOSSIERS_RESSOURCE or (intermediaires & DOSSIERS_RESSOURCE):
            return None, False, "ressource interne, pas une fiche"
        # PROFONDEUR. Le schéma imposé par l'outil extérieur est EXACTEMENT
        # `zone/<slug>/SKILL.md` — deux segments, pas trois. Un dossier qui en CONTIENT
        # d'autres n'est pas un skill, c'est un conteneur, et son nom n'est l'identité de
        # personne. Mesuré le 2026-09-20 : `skills/synced/<uuid>/<slug>/SKILL.md`, le
        # miroir des skills synchronisés, rabattait SES 57 SKILL.md sur l'unique identité
        # « synced ». Conséquence en chaîne — 57 orphelins et 57 hors-carte portant tous
        # le même nom, 86 « représentations concurrentes », 58 plaintes de frontmatter ;
        # et comme le doctor n'imprime que 12 entrées par rubrique, le sabotage de
        # `tests/identite_skills.py` (un skill au `name:` faux) tombait HORS DE L'ÉCRAN.
        # Le banc était rouge sur « SABOTAGE INVISIBLE » : du bruit qui cache un défaut.
        # La règle se dit en structure, pas en liste de noms — une liste aurait raté le
        # prochain conteneur, ce que ce fichier reproche déjà aux copies de `basename`.
        if len(parts) > 3:
            return None, False, ("hors du schéma %s/<slug>/%s — %d niveaux de dossier, "
                                 "donc un conteneur et non un skill"
                                 % (zone, FAMILLES_A_DOSSIER[zone], len(parts) - 1))
        if fichier == FAMILLES_A_DOSSIER[zone]:
            return dossier, True, None
        # même identité logique, autre fichier : représentation CONCURRENTE.
        return dossier, False, ("représentation concurrente de %s/%s/%s"
                                % (zone, dossier, FAMILLES_A_DOSSIER[zone]))

    return os.path.splitext(fichier)[0], True, None


def chemin_canonique(zone, slug):
    """L'inverse : où DOIT vivre la fiche `slug` de la zone `zone`."""
    if zone in FAMILLES_A_DOSSIER:
        return "%s/%s/%s" % (zone, slug, FAMILLES_A_DOSSIER[zone])
    return "%s/%s.md" % (zone, slug)


def scanner(racine, zones):
    """Parcourt `zones` sous `racine`. Rend (index, conflits, ignores).

    index     {slug: chemin relatif}  — une entrée par identité, jamais deux ;
    conflits  [(slug, canonique, concurrent, motif)] — à SIGNALER, pas à trancher seul ;
    ignores   [(rel, motif)] — ressources internes et fichiers hors schéma.

    Le scanner ne supprime ni ne renomme rien : détecter n'est pas décider.
    """
    index, conflits, ignores, vus = {}, [], [], {}
    for z in zones:
        d = os.path.join(racine, z)
        if not os.path.isdir(d):
            continue
        for r, sousdirs, fs in os.walk(d):
            # élaguer À LA SOURCE : descendre dans un .venv puis filtrer coûte des
            # milliers de fichiers pour rien.
            sousdirs[:] = [x for x in sousdirs if x not in DOSSIERS_OUTILLAGE]
            for f in sorted(fs):
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(r, f), racine).replace("\\", "/")
                slug, canonique, motif = identite(rel)
                if slug is None:
                    ignores.append((rel, motif))
                    continue
                vus.setdefault(slug, []).append((rel, canonique, motif))
    for slug, entrees in vus.items():
        canons = [e for e in entrees if e[1]]
        autres = [e for e in entrees if not e[1]]
        if canons:
            index[slug] = canons[0][0]
            for rel, _, motif in autres:
                conflits.append((slug, canons[0][0], rel, motif))
            for rel, _, _ in canons[1:]:
                conflits.append((slug, canons[0][0], rel, "deux fichiers canoniques"))
        elif autres:
            # pas de canonique : la fiche n'est PAS indexée, et on dit pourquoi.
            for rel, _, motif in autres:
                conflits.append((slug, None, rel, motif + " — aucun canonique présent"))
    return index, conflits, ignores
