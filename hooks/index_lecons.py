#!/usr/bin/env python3
"""Régénère lessons/INDEX.md depuis les `tags:` des fiches — l'INDEX devient un ARTEFACT.

Décision de l'utilisateur, 2026-08-14 (question Q3 du chantier « ossature thématique ») : la vérité
vit dans les fiches, l'INDEX est dérivé. Motif : un index tenu à la main sur 223 leçons a déjà
dérivé une fois — c'est de là que venaient ses 16 « Divers » et ses 21 étiquettes qui rangeaient
par technologie. Cf. [[reparer-l-artefact-derive-ne-tient-qu-un-cycle]] : la réparation va dans
la source, jamais dans le fichier régénéré.

Ce qui a été SAUVÉ avant de rendre ce fichier jetable (sinon on perdait le jugement de l'auteur) :
  · les 103 ⭐ → champ `star: true` dans la fiche ;
  · les 22 gloses que la description ne portait pas → repliées dans la description.

    python3 hooks/index_lecons.py            # écrit
    python3 hooks/index_lecons.py --verifie  # ne touche à rien, sort 1 si l'INDEX a dérivé
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, légitime
from brain_racine import brain_root

# I-1 (2026-08-21). Avant : la racine du DÉPÔT du script servait d'identité du Brain —
# racine de CODE prise pour racine de BRAIN. Ce module ÉCRIT `lessons/INDEX.md` : sur la
# mauvaise racine, il réécrit l'index d'un autre arbre. Migré SANS être exécuté sur le
# tronc : la preuve est faite sur clones jetables, la collecte held-out est en cours.
BRAIN = brain_root(__file__)
INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")


def frontmatter(p):
    raw = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def champ(fm, nom):
    m = re.search(rf'^{nom}:\s*"?(.*?)"?\s*$', fm, re.M)
    return m.group(1) if m else ""


def lire_lecons():
    out = []
    # Cherche les tags dans toute l'arborescence (sauf sessions/, audits/, .git/, vision/, etc.)
    # car une leçon peut être physiquement un projet mais aussi une leçon par ses tags.
    # vision/ est exclue : ce sont des documents sources de continuité, pas des leçons
    excludes = {".git", "audits", "sessions", "capsule", "companion", "tools", "archive", ".claude", "planet", "vision"}
    for p in sorted(glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True)):
        # Exclut les dossiers spécialisés et l'INDEX lui-même
        rel = os.path.relpath(p, BRAIN)
        if any(rel.startswith(ex) for ex in excludes) or os.path.basename(p) == "INDEX.md":
            continue
        fm = frontmatter(p)
        t = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
        if not t:  # Seules les fiches avec tags sont des leçons
            continue
        nom = os.path.basename(p)[:-3]
        out.append({
            "nom": nom,
            "desc": champ(fm, "description"),
            "tags": [x.strip() for x in t.group(1).split(",") if x.strip()],
            "star": champ(fm, "star").lower() == "true",
        })
    return out


def rendre():
    # Le registre est la PIÈCE MAÎTRESSE : sans lui il n'y a pas d'index à écrire.
    # On sort en nommant l'étape suivante plutôt qu'en déroulant une trace Python —
    # un `FileNotFoundError` nu dit ce qui manque, jamais quoi faire.
    reg = os.path.join(BRAIN, "meta", "familles.json")
    try:
        familles = json.load(open(reg, encoding="utf-8"))["familles"]
    except FileNotFoundError:
        sys.exit(f"❌ registre des familles absent : {reg}\n"
                 "   → `git checkout meta/familles.json` dans le tronc, ou relance "
                 "./install.sh (le paquet le livre dans skeleton/meta/).")
    except (ValueError, KeyError) as e:
        sys.exit(f"❌ registre des familles illisible : {reg} ({e})\n"
                 "   → répare le JSON ; l'INDEX n'est pas réécrit tant qu'il ne charge pas.")
    lecons = lire_lecons()
    sans = [l["nom"] for l in lecons if not l["tags"]]

    par_fam = {k: {"principal": [], "aussi": []} for k in familles}
    for l in lecons:
        for i, t in enumerate(l["tags"]):
            if t in par_fam:
                par_fam[t]["principal" if i == 0 else "aussi"].append(l)

    ordre = sorted(familles, key=lambda k: -len(par_fam[k]["principal"]))
    lignes = [
        "<!-- ⚠️ FICHIER GÉNÉRÉ — ne pas éditer à la main : `python3 hooks/index_lecons.py` l'écrase.",
        "     La vérité vit dans le champ `tags:` de chaque fiche. Pour déplacer une leçon,",
        "     on change SON tag, jamais cette carte. -->",
        "",
        "# Carte des leçons transverses",
        "",
        "Cet index secondaire conserve la navigation exhaustive sans charger tout le catalogue à "
        "chaque démarrage. Il est structurel : les moteurs de rappel et les métriques de savoir l'excluent.",
        "",
        f"**{len(lecons)} leçons · {len(familles)} familles.** Le rangement en dossiers dit la PORTÉE "
        "(d'où faut-il pouvoir relire la fiche) ; ces familles disent le SUJET. Les deux axes sont "
        "indépendants — une famille n'est pas un dossier.",
        "",
    ]
    for k in ordre:
        f, grp = familles[k], par_fam[k]
        if not grp["principal"] and not grp["aussi"]:
            continue
        lignes.append(f"### {f['titre']}  ·  {len(grp['principal'])}")
        lignes.append(f"*{f['quand']}* — on la trouve en cherchant : {' · '.join(f['lexique'])}")
        lignes.append("")
        # ⚠️ UNE FICHE PAR LIGNE, GLOSE COURTE. Première version : tout sur une seule ligne avec
        # la description entière — 400 caractères par fiche, 50 fiches à la suite, illisible.
        # Un catalogue se PARCOURT : le nom porte déjà le sens, la glose ne fait que confirmer.
        def glose(d, n=115):
            # ⚠️ UNE CARTE GÉNÉRÉE DOIT ÊTRE INERTE. Les descriptions contiennent des
            # apostrophes inverses (`git checkout`, `tags:`) : recopiées telles quelles, elles
            # ouvrent des spans de code non fermés, et l'extracteur de liens du docteur avalait
            # tout ce qui suit. Mesuré : 289 `[[` dans le fichier, 136 liens vus — 153 liens
            # perdus, donc des « orphelins » signalés à tort sur des fiches parfaitement liées.
            # On neutralise aussi les crochets, qui fabriqueraient de faux liens.
            d = re.sub(r"\s+", " ", d).replace("`", "").replace("[[", "").replace("]]", "").strip()
            if len(d) <= n:
                return d
            coupe = d[:n].rsplit(" ", 1)[0]
            return coupe + "…"
        for l in sorted(grp["principal"], key=lambda x: (not x["star"], x["nom"])):
            etoile = "⭐ " if l["star"] else ""
            lignes.append(f"- {etoile}[[{l['nom']}]] — {glose(l['desc'])}" if l["desc"]
                          else f"- {etoile}[[{l['nom']}]]")
        if grp["aussi"]:
            lignes.append("")
            lignes.append("*Touche aussi cette famille :* " +
                          " · ".join(f"[[{l['nom']}]]" for l in sorted(grp["aussi"], key=lambda x: x["nom"])))
        lignes.append("")
    if sans:
        lignes += ["### ⚠️ Sans famille — à taguer", "", " · ".join(f"[[{n}]]" for n in sans), ""]
    return "\n".join(lignes) + "\n"


if __name__ == "__main__":
    neuf = rendre()
    if "--verifie" in sys.argv:
        actuel = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
        if actuel == neuf:
            print("INDEX à jour."); sys.exit(0)
        print("INDEX DÉRIVÉ — relancer `python3 hooks/index_lecons.py`.", file=sys.stderr); sys.exit(1)
    open(INDEX, "w", encoding="utf-8").write(neuf)
    n = len(lire_lecons())
    print(f"lessons/INDEX.md régénéré : {n} leçons")
