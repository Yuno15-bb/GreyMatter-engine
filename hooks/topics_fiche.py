#!/usr/bin/env python3
"""topics_fiche — LIRE et VALIDER le sujet d'une fiche. Une seule définition, un seul code.

POURQUOI CE MODULE EXISTE
    Le tronc compte déjà SIX lecteurs de frontmatter écrits chacun de leur côté
    (`brain_doctor`, `graph_export`, `index_lecons`, `fraicheur_fiches`,
    `provenance_fiches`, `archiver-journal`). Aucun n'est un vrai analyseur YAML : ce sont
    des expressions régulières ligne à ligne. Ajouter un septième dialecte pour les sujets
    reproduirait exactement le défaut mesuré le 20/08, où deux lecteurs de `MEMORY.md`
    fabriquaient la divergence qu'ils prétendaient mesurer. Tout ce qui lit ou écrit un
    sujet passe donc par ici — l'outil d'écriture comme le banc qui le met à l'épreuve.

LA SOURCE RESTE `meta/topics.json`
    Les identifiants valides sont LUS à chaque appel, jamais recopiés. Un sujet retiré de
    la source devient immédiatement invalide ici, sans qu'aucune liste ne soit à tenir à
    jour. C'est ce qui rend la contre-épreuve « le 13e sujet réapparaît » possible.

LE FORMAT, ET POURQUOI CELUI-LÀ (mesuré avant d'être choisi)
        topic: preuve-et-verification
        topics_secondaires: [le-brain, machine-et-processus]

    - Une clé par ligne, valeur simple : les six lecteurs à expression régulière la lisent
      sans broncher, et aucun ne valide la liste des clés — une clé neuve ne fait rougir
      personne (vérifié dans `brain_doctor.frontmatter`, qui ne contrôle que `name` et
      `description`).
    - La liste est EN LIGNE, entre crochets, parce que c'est déjà la convention du tronc
      pour `tags:`, lue par `re.search(r"^tags:\\s*\\[(.*?)\\]")`. Une liste YAML à tirets
      serait ignorée en silence par `brain_doctor`, qui ne garde que ce qui ressemble à
      `clé: valeur`.
    - `topics_secondaires` est ABSENTE quand il n'y en a pas : une clé vide se lirait comme
      une liste d'un élément vide chez au moins un des lecteurs.
    - Le frontmatter n'entre PAS dans le texte indexé par le rappel (`brain_recall` construit
      son document avec `strip_md()`, qui retire le frontmatter). Écrire un sujet ne peut donc
      pas déplacer un résultat de `golden_recall` — c'est vérifié par contre-épreuve, pas
      supposé.
"""
import json
import os
import re

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
SOURCE = os.path.join(BRAIN, "meta", "topics.json")

RE_TOPIC = re.compile(r"^topic:[ \t]*(.*?)[ \t]*$", re.M)
RE_SECONDAIRES = re.compile(r"^topics_secondaires:[ \t]*\[(.*?)\][ \t]*$", re.M)


class SujetInvalide(ValueError):
    """Levée quand un sujet ne peut pas être écrit. Le refus est le comportement voulu."""


def ids_canoniques():
    """Les identifiants de sujet valides, LUS dans la source à chaque appel."""
    canon = json.load(open(SOURCE, encoding="utf-8"))
    return [t["id"] for t in canon["topics"]]


def bloc_frontmatter(texte):
    """Le contenu entre les deux `---` de tête, ou None. Même découpe que les six lecteurs."""
    m = re.match(r"^---\n(.*?)\n---", texte, re.S)
    return m.group(1) if m else None


def lire(texte):
    """Rend (topic, [secondaires]) tels qu'ils sont ÉCRITS. Ne valide rien, ne devine rien.

    `topic` vaut None si la clé est absente. Une clé présente deux fois rend la liste de
    toutes ses valeurs, pour que le contrôle puisse REFUSER au lieu d'en choisir une.
    """
    fm = bloc_frontmatter(texte)
    if fm is None:
        return None, []
    principaux = [v.strip().strip('"').strip("'") for v in RE_TOPIC.findall(fm)]
    m = RE_SECONDAIRES.search(fm)
    secondaires = []
    if m:
        secondaires = [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]
    if len(principaux) > 1:
        return principaux, secondaires        # une LISTE signale la faute au contrôleur
    return (principaux[0] if principaux else None), secondaires


def valider(topic, secondaires, ids=None):
    """Lève SujetInvalide si quoi que ce soit cloche. Aucune correction silencieuse."""
    ids = ids if ids is not None else ids_canoniques()
    if isinstance(topic, list):
        raise SujetInvalide("deux sujets principaux : %s" % topic)
    if not topic:
        raise SujetInvalide("aucun sujet principal")
    if topic not in ids:
        raise SujetInvalide("sujet principal inconnu : %r" % topic)
    vus = set()
    for s in secondaires:
        if s not in ids:
            raise SujetInvalide("sujet secondaire inconnu : %r" % s)
        if s == topic:
            raise SujetInvalide("le secondaire %r répète le principal" % s)
        if s in vus:
            raise SujetInvalide("secondaire en double : %r" % s)
        vus.add(s)
    return True


def rendu(topic, secondaires):
    """Les lignes à insérer dans le frontmatter, dans l'ordre stable."""
    lignes = ["topic: %s" % topic]
    if secondaires:
        lignes.append("topics_secondaires: [%s]" % ", ".join(secondaires))
    return lignes


def ecrire(texte, topic, secondaires, ids=None):
    """Rend le texte avec le sujet posé. VALIDE d'abord ; ne touche à rien d'autre.

    L'insertion se fait juste après `tags:` quand il existe — les deux axes de classement
    se lisent alors côte à côte — sinon après `description:`. Une clé déjà présente est
    remplacée sur place, jamais dupliquée.
    """
    valider(topic, secondaires, ids)
    fm = bloc_frontmatter(texte)
    if fm is None:
        raise SujetInvalide("fiche sans frontmatter")
    lignes = fm.split("\n")
    # retirer les clés existantes (remplacement, pas empilement)
    lignes = [l for l in lignes
              if not re.match(r"^topic:", l) and not re.match(r"^topics_secondaires:", l)]
    nouvelles = rendu(topic, secondaires)
    pos = None
    for i, l in enumerate(lignes):
        if re.match(r"^tags:", l):
            pos = i + 1
    if pos is None:
        for i, l in enumerate(lignes):
            if re.match(r"^description:", l):
                pos = i + 1
        # une description sur plusieurs lignes (bloc `>-`) : descendre jusqu'à la clé suivante
        while pos is not None and pos < len(lignes) and re.match(r"^\s", lignes[pos]):
            pos += 1
    if pos is None:
        pos = len(lignes)
    lignes[pos:pos] = nouvelles
    return texte.replace(fm, "\n".join(lignes), 1)
