#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""C Brain — contrôle de fuite. Le garde-fou qui a le droit de bloquer le commit.

Adapté de claude-brain-v2/build/leakcheck.py (2026-07-25), qui tourne déjà vert
sur le pipeline d'anonymisation du portfolio.

Il ne relit PAS la source : il scanne ce qui va réellement sortir — le dépôt
lui-même, et son historique git avec --history. Un marqueur qui survit = rouge.

Usage :
  python3 leakcheck.py              scanne l'arbre de travail
  python3 leakcheck.py --history    scanne EN PLUS tout l'historique git

Sortie 0 = propre · Sortie 1 = fuite détectée.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Ce qui ne doit JAMAIS sortir. Deux familles : identités réelles de tiers,
# et secrets. Les deux bloquent de la même façon.
MARKERS = [
    ("nom du client",           r"DG\s*CHARPENTE|DG\s*Charpente"),
    ("sigle client",            r"\bDGC\b|\bdgc-"),
    ("produit client",          r"BIG\s*GABY|\bGaby\b|\bgaby\b"),
    ("personne — propriétaire", r"\bDylan\b|\bDylanp\b"),
    ("personne — gestionnaire", r"\bClarisse\b"),
    ("personne — technicien",   r"\bLaurent\b"),
    ("personne — dirigeant",    r"\bGabriel\b"),
    ("nom de famille client",   r"\bRoume\b"),
    ("ville du client",         r"\bToulouse\b|\btoulousain"),
    ("commune du client",       r"\bCastanet-Tolosan\b|\bColomiers\b|\bBlagnac\b"
                                r"|\bTournefeuille\b|\bMURET\b"),
    ("code postal local",       r"\b31\d{3}\b"),
    ("cadre personnel",         r"Mission Locale|\bCEJ\b"),
    ("tiers identifié",         r"\b(GAILLOUSTE|TREMBLET|GAUBE|DELEST|MARRE|CHOUIALI"
                                r"|NAJMEDDINE|WILLHEM|AGESTIS|ALTRAD|FONCIA|SERCOB"
                                r"|PERSONAZ|RENOVAZ|CHAMAYOU|Barhoumi|Faouz|Merwan"
                                r"|Alexis|Joris)\b"),
    ("adresse mail",            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("téléphone",               r"(?<![\d.])0[1-9](?:[ .-]?\d{2}){4}(?![\d.])"),
    ("adresse postale",         r"\b\d{1,3}\s+(?:rue|avenue|impasse|chemin|boulevard|route)\s+\w+"),
    ("chemin personnel",        r"/Users/[A-Za-z0-9_.-]+/"),
    ("clé Anthropic",           r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ("jeton GitHub",            r"gh[pousr]_[A-Za-z0-9]{16,}"),
    ("jeton JWT",               r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("secret assigné en clair", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"),
]

# Deux fichiers CONTIENNENT forcément les marqueurs, c'est leur métier :
# le contrôleur (la liste) et les règles de généralisation (les motifs à traiter).
# Les scanner reviendrait à se mordre la queue.
SKIP_NAMES = {"leakcheck.py", "rules.json"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}

# Exemptions NOMMÉES, marqueur par marqueur. Jamais un dossier entier :
# une exemption large finirait par couvrir une vraie fuite.
#
# `docs/` = prose rédigée et relue à la main. Le propriétaire y garde son nom,
# c'est SON design-doc (même décision que pour le portfolio Claude Brain V2).
# Tous les autres marqueurs — clients, tiers, secrets, chemins — s'y appliquent
# normalement : seul le nom du propriétaire est exempté.
# `LICENSE` et `NOTICE` : Apache 2.0 EXIGE le nom du titulaire du copyright.
# Le retirer rendrait la licence inopérante. C'est une mention volontaire et
# juridiquement nécessaire, pas une fuite. Exemption ciblée sur le seul marqueur
# « propriétaire » : une clé ou un nom de client dans ces fichiers reste rouge.
# `.claude-plugin/` les rejoint pour la même raison que LICENSE : les manifestes
# de plugin et de marketplace portent des champs `author` / `owner`, Claude Code
# les montre à qui installe, et une entrée de catalogue sans mainteneur n'a pas
# à être publiée. Même règle : seul le nom du PROPRIÉTAIRE y est exempté ; un
# nom de client ou une clé dans ces fichiers vire toujours au rouge.
EXEMPT = {"personne — propriétaire": ("docs/", "LICENSE", "NOTICE", ".claude-plugin/"),
          # `.sync-manifest` n'est pas de la prose : c'est une liste de sommes
          # SHA-256 suivies de chemins relatifs, RÉGÉNÉRÉE à chaque sync. Un
          # hexadécimal de 64 caractères finit statistiquement par contenir une
          # suite de chiffres qui ressemble à un numéro — c'est arrivé le
          # 2026-08-03 et ça a bloqué une publication propre. Le danger d'une
          # telle fausse alerte n'est pas la perte de temps : c'est qu'elle
          # apprend à passer outre un contrôle rouge. Exemption ciblée sur le
          # SEUL marqueur numérique ; un nom ou une clé dans ce fichier reste rouge.
          "téléphone": (".sync-manifest",)}

# Le nom de l'auteur dans l'en-tête de copyright de CE dépôt n'est pas une fuite :
# c'est une signature volontaire, et depuis le passage en Apache 2.0 il figure de
# toute façon dans LICENSE, où la licence l'exige. Le motif est ancré sur la forme
# EXACTE de l'en-tête — pas sur le nom seul, qui reste bloquant partout ailleurs
# (prose, chemins /Users/..., commentaires).
COPYRIGHT_HEADER = re.compile(r"Copyright \(c\) 20\d\d [A-Z][a-z]+ [A-Z][a-z]+")

# Adresses qui ressemblent à un mail sans en être un. Liste FERMÉE de littéraux
# exacts — jamais un assouplissement du motif, qui rouvrirait la porte à tout.
FAUX_POSITIFS = {
    "adresse mail": ("git@github.com",),   # syntaxe SSH, pas une personne
}

# ── LEURRES DE TEST ────────────────────────────────────────────────────────
# Un test qui prouve qu'un garde-fou ROUGIT doit contenir la chose interdite.
# `tests/fiche_write_contract.py` écrit une fausse clé Anthropic pour vérifier
# qu'elle est bien refusée ; `tests/a1_pixel_lib.py` compare des chemins
# `/Users/x/` pour vérifier qu'un chemin personnel est bien reconnu. Sans
# exception, le contrôle bloque les tests écrits POUR LUI — et le seul geste
# possible devient de l'assouplir. C'est précisément ce qu'on refuse.
#
# Trois verrous, cumulatifs, pour que l'exception ne puisse pas grossir :
#   1. VALEUR EXACTE. Liste fermée de littéraux, jamais un motif détendu.
#      Toute variation — une vraie clé, un vrai chemin — reste rouge.
#   2. EMPLACEMENT. Uniquement sous `tests/`. La même valeur ailleurs dans le
#      dépôt rougit toujours : un leurre n'a de sens que dans un test.
#   3. FORME MANIFESTEMENT FAUSSE. `AAAABBBBCCCCDDDDEEEE`, `/Users/x/` — aucune
#      ne peut être confondue avec une donnée réelle par un relecteur.
#
# Ajouter une entrée ici est une décision, pas une commodité : elle doit être
# accompagnée d'un test dans `tests/leakcheck_fixtures.py` qui prouve que la
# variante NON exemptée reste bloquante.
FIXTURES_DIRS = ("tests/",)
FIXTURES = {
    "chemin personnel": ("/Users/x/", "/Users/them/", "/Users/us/"),
    "clé Anthropic": ("sk-ant-AAAABBBBCCCCDDDDEEEE",),
    "secret assigné en clair": ('SECRET = "sk-ant-AAAABBBBCCCCDDDDEEEE',),
}


def est_un_leurre(label: str, source: str, valeur: str) -> bool:
    """Vrai seulement si les trois verrous sont satisfaits en même temps."""
    src = source[len("historique:"):] if source.startswith("historique:") else source
    if not src.startswith(FIXTURES_DIRS):
        return False
    return valeur in FIXTURES.get(label, ())


def exempted(label: str, source: str) -> bool:
    # « historique:docs/… » doit être exempté comme « docs/… » : c'est le même
    # fichier, vu à deux moments.
    src = source[len("historique:"):] if source.startswith("historique:") else source
    return any(src.startswith(p) for p in EXEMPT.get(label, ()))


# Les en-têtes de diff ne sont PAS du contenu publié : `index e855c2a..8ef0920
# 100644` a été lu comme un numéro de téléphone français. On les retire avant de
# scanner — un faux positif dans un garde-fou bloquant est aussi nuisible qu'un
# trou : il pousse à assouplir les marqueurs pour « débloquer ».
DIFF_META = re.compile(r"^(diff --git |index [0-9a-f]+\.\.|--- |\+\+\+ |@@ |old mode |new mode |"
                       r"similarity index |rename (from|to) |new file mode |deleted file mode )")


def strip_diff_metadata(patch: str) -> str:
    return "\n".join(l for l in patch.splitlines() if not DIFF_META.match(l))


def is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.read_bytes()[:2048]
    except OSError:
        return False


def iter_files():
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        if SKIP_DIRS & set(f.relative_to(ROOT).parts):
            continue
        if is_text(f):
            yield f


def context(text, start, end, width=45):
    left = text[max(0, start - width):start].replace("\n", " ")
    right = text[end:end + width].replace("\n", " ")
    return f"…{left}⟦{text[start:end]}⟧{right}…"


def _sur_une_ligne_de_copyright(text: str, pos: int) -> bool:
    """Ce résultat est-il posé sur une ligne de copyright / de licence ?

    Le nom du propriétaire dans un en-tête de copyright est VOLONTAIRE — c'est
    ce qui fait qu'un fichier copié porte son origine. Ce que le marqueur
    traque vraiment, c'est la mention accidentelle (« la machine de l'auteur »,
    « demandé par … »). Exempter la ligne de notice garde la chasse tranchante
    au lieu d'émousser le motif.
    """
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:end if end != -1 else len(text)]
    return "Copyright (c)" in line or "All rights reserved" in line


def scan(label_source, text, compiled, leaks):
    if label_source.startswith("historique:"):
        text = "\n".join(l for l in text.splitlines() if not COPYRIGHT_HEADER.search(l))
    for label, rx in compiled:
        if exempted(label, label_source):
            continue
        for m in rx.finditer(text):
            if m.group(0) in FAUX_POSITIFS.get(label, ()):
                continue
            if est_un_leurre(label, label_source, m.group(0)):
                continue
            if label == "personne — propriétaire" and _sur_une_ligne_de_copyright(text, m.start()):
                continue
            leaks.append((label_source, label, context(text, m.start(), m.end())))


def main():
    with_history = "--history" in sys.argv
    compiled = [(label, re.compile(pattern)) for label, pattern in MARKERS]
    leaks = []

    files = list(iter_files())
    for path in files:
        scan(path.relative_to(ROOT).as_posix(),
             path.read_text(encoding="utf-8", errors="replace"), compiled, leaks)

    scanned = f"{len(files)} fichier(s)"

    if with_history:
        try:
            paths = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                   capture_output=True, text=True, timeout=30).stdout.split()
        except (OSError, subprocess.SubprocessError):
            paths = []
            print("⚠️  Historique git illisible — scan limité à l'arbre de travail.")

        # CHEMIN PAR CHEMIN, pas en un seul bloc. Deux raisons :
        #  · les exemptions (docs/, contrôleur, règles) ne s'appliquent que si
        #    l'on sait de quel fichier vient chaque ligne ;
        #  · `--format=` retire les en-têtes de commit, sinon la ligne « Author:
        #    Prénom Nom <mail> » remonte comme fuite à chaque commit.
        n_hist = 0
        for rel in paths:
            if os.path.basename(rel) in SKIP_NAMES:
                continue
            try:
                d = subprocess.run(["git", "-C", str(ROOT), "log", "-p", "--all",
                                    "--format=", "--", rel],
                                   capture_output=True, text=True, timeout=60).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if d:
                n_hist += 1
                scan(f"historique:{rel}", strip_diff_metadata(d), compiled, leaks)
        if n_hist:
            scanned += f" + historique de {n_hist} fichier(s)"

    print(f"🔍 Contrôle de fuite — {scanned}, {len(MARKERS)} marqueurs")

    if not leaks:
        print("\n✅ PROPRE — aucun marqueur sensible. Commit autorisé.")
        return 0

    by_label = {}
    for _, label, _ in leaks:
        by_label[label] = by_label.get(label, 0) + 1

    print(f"\n⛔ ROUGE — {len(leaks)} fuite(s). Rien ne sort.\n")
    for label, count in sorted(by_label.items(), key=lambda kv: -kv[1]):
        print(f"   {count:>5}×  {label}")

    print("\n   Cas :")
    for path, label, ctx in leaks[:20]:
        print(f"     · [{label}] {path}\n       {ctx}")
    if len(leaks) > 20:
        print(f"     … et {len(leaks) - 20} autre(s).")

    print("\n   → Corrige à la source (généralise le fichier), pas en assouplissant les marqueurs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
