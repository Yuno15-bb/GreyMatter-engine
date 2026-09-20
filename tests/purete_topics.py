#!/usr/bin/env python3
"""BANC — le contrôle de pureté des topics sait-il ROUGIR, et sur quoi exactement ?

Il exerce `tools/nettoyage/classement/verifier_purete.py`, c'est-à-dire EXACTEMENT le code
qui sert à valider un lot avant commit. Le banc ne réimplémente rien : il fabrique des
situations et regarde le verdict rendu.

REPRODUCTIBLE DEPUIS LE DÉPÔT SEUL. Chaque cas se joue dans un dépôt git JETABLE, créé dans
un dossier temporaire et détruit à la fin. Aucune fiche du tronc n'est lue ni touchée, et le
banc ne dépend d'aucun commit de l'historique : il ne peut donc pas virer au rouge parce que
l'histoire du Brain a bougé.

LES DEUX FAUTES REJOUÉES SONT DES FAUTES RÉELLES, PAS DES HYPOTHÈSES
  · S1 — la liste de chemins rendue en UN seul argument géant. C'est le faux vert du lot C
    (28/08) : sous zsh une variable non quotée n'est pas découpée, git recevait un argument
    de 6 Ko, ne voyait aucun fichier, et le contrôle affichait « 0 anomalie ».
  · S4 — un fichier ENTIER embarqué dans le lot. C'est le défaut du lot A (`e376edf`), qui a
    avalé une fiche non suivie écrite par une autre session.

S7 EST LA CONTRE-ÉPREUVE DU GARDE-FOU LUI-MÊME : elle vérifie que sans lui, S1 repasserait
au VERT. Un garde-fou dont on ne prouve pas qu'il porte quelque chose ne prouve rien.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(ICI), "tools", "nettoyage", "classement"))
import verifier_purete as V  # noqa: E402

FICHE = """---
name: %s
description: "Fiche d'essai du banc."
tags: [le-cerveau]
metadata:
  type: lesson
---

Corps inchangé.
"""


def git(d, *a):
    subprocess.run(["git", *a], cwd=d, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def depot_jetable():
    """Un dépôt neuf, trois fiches commitées, aucune ligne de sujet encore posée."""
    d = tempfile.mkdtemp(prefix="banc-purete-")
    git(d, "init", "-q")
    git(d, "config", "user.email", "banc@local")
    git(d, "config", "user.name", "banc")
    for n in ("alpha", "beta", "gamma"):
        open(os.path.join(d, n + ".md"), "w").write(FICHE % n)
    git(d, "add", "-A")
    git(d, "commit", "-qm", "socle")
    return d


def poser_sujet(d, nom, ligne="topic: le-brain"):
    p = os.path.join(d, nom + ".md")
    t = open(p).read().replace("tags: [le-cerveau]", "tags: [le-cerveau]\n" + ligne)
    open(p, "w").write(t)


def cas(nom, attendu, obtenu, echecs, detail=""):
    ok = obtenu == attendu
    print("   %s %-58s %s attendu, %s observé%s"
          % ("✅" if ok else "❌", nom, attendu, obtenu, detail))
    if not ok:
        echecs.append(nom)


def main():
    echecs = []
    print("── SABOTAGES DU CONTRÔLE DE PURETÉ (dépôts jetables) ──")

    # S0 — le cas propre doit passer au VERT, sinon le banc ne prouve rien.
    d = depot_jetable()
    poser_sujet(d, "alpha")
    poser_sujet(d, "beta")
    r = V.verifier(d, ["alpha.md", "beta.md"])
    cas("S0 deux sujets posés, rien d'autre", V.PUR, r["verdict"], echecs)
    if r["verdict"] == V.PUR and (r["ajoutees"], r["retirees"]) != (2, 0):
        echecs.append("S0 compte mal (%d/%d)" % (r["ajoutees"], r["retirees"]))

    # S1 — LE BUG DU LOT C : toute la liste rendue en un seul argument.
    r = V.verifier(d, [" ".join(["alpha.md", "beta.md"])])
    cas("S1 liste rendue en UN argument géant (bug du lot C)", V.ANOMALIE, r["verdict"], echecs)

    # S2 — un chemin qui n'a aucune modification : git en voit moins que demandé.
    r = V.verifier(d, ["alpha.md", "beta.md", "gamma.md"])
    cas("S2 un chemin sans modification dans la liste", V.ANOMALIE, r["verdict"], echecs)

    # S3 — une suppression glissée à côté du sujet.
    d3 = depot_jetable()
    poser_sujet(d3, "alpha")
    p = os.path.join(d3, "alpha.md")
    open(p, "w").write(open(p).read().replace("Corps inchangé.\n", ""))
    r = V.verifier(d3, ["alpha.md"])
    cas("S3 une ligne SUPPRIMÉE à côté du sujet", V.IMPUR, r["verdict"], echecs)

    # S4 — LE DÉFAUT DU LOT A : un fichier non suivi, qui serait ajouté ENTIER.
    d4 = depot_jetable()
    poser_sujet(d4, "alpha")
    open(os.path.join(d4, "intrus.md"), "w").write(FICHE % "intrus")
    r = V.verifier(d4, ["alpha.md", "intrus.md"])
    cas("S4 un fichier NON SUIVI dans le lot (défaut du lot A)", V.ANOMALIE, r["verdict"], echecs)

    # S4bis — le même intrus, mais déjà commité : le patch montre le fichier entier.
    git(d4, "add", "-A")
    git(d4, "commit", "-qm", "lot avec intrus")
    r = V.verifier(d4, ["alpha.md", "intrus.md"], source="HEAD")
    nomme = any("name: intrus" in l for l in r["hors_sujet"])
    cas("S4bis le même intrus relu DANS le commit", V.IMPUR, r["verdict"], echecs,
        " · lignes fautives nommées" if nomme else " · ⚠️ sans nommer les lignes")
    if r["verdict"] == V.IMPUR and not nomme:
        echecs.append("S4bis ne nomme pas les lignes fautives")

    # S8 — LE CAS DES FICHES SALES : copie de travail impure, index pur.
    # Ici la copie de travail porte LÉGITIMEMENT du travail étranger. Regarder la copie de
    # travail donnerait un rouge trompeur ; seul l'index doit être pur, car seul l'index part
    # au commit. Le banc vérifie que le contrôle sait faire la différence.
    d8 = depot_jetable()
    p8 = os.path.join(d8, "alpha.md")
    open(p8, "w").write(open(p8).read().replace("Corps inchangé.", "Corps inchangé.\n\nAjout d'une autre session."))
    base = subprocess.run(["git", "show", "HEAD:alpha.md"], cwd=d8,
                          capture_output=True, text=True).stdout
    avec = base.replace("tags: [le-cerveau]", "tags: [le-cerveau]\ntopic: le-brain")
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=d8, input=avec,
                          capture_output=True, text=True).stdout.strip()
    git(d8, "update-index", "--cacheinfo", "100644,%s,alpha.md" % blob)
    open(p8, "w").write(avec.replace("Corps inchangé.", "Corps inchangé.\n\nAjout d'une autre session."))
    r = V.verifier(d8, ["alpha.md"], source="--cached")
    cas("S8 fiche sale : l'INDEX est pur", V.PUR, r["verdict"], echecs)
    r = V.verifier(d8, ["alpha.md"])
    cas("S8bis la même fiche : la COPIE DE TRAVAIL est impure", V.IMPUR, r["verdict"], echecs)

    # S5 — une ligne étrangère ajoutée juste à côté du sujet.
    d5 = depot_jetable()
    poser_sujet(d5, "alpha", "topic: le-brain\nauteur: quelqu-un-d-autre")
    r = V.verifier(d5, ["alpha.md"])
    cas("S5 une ligne ÉTRANGÈRE ajoutée à côté du sujet", V.IMPUR, r["verdict"], echecs)

    # S6 — un sujet hors des deux préfixes autorisés.
    d6 = depot_jetable()
    poser_sujet(d6, "alpha", "topics: le-brain")
    r = V.verifier(d6, ["alpha.md"])
    cas("S6 un préfixe voisin mais non autorisé (`topics:`)", V.IMPUR, r["verdict"], echecs)

    # S7 — CONTRE-ÉPREUVE DU GARDE-FOU : sans lui, S1 repasse-t-il au vert ?
    print("\n── CONTRE-ÉPREUVE : le garde-fou porte-t-il quelque chose ? ──")
    sortie = V._git(d, ["diff", "--numstat", "--", " ".join(["alpha.md", "beta.md"])])
    aveugle = [l for l in sortie.splitlines() if l.strip()]
    faux_vert = (len(aveugle) == 0)
    print("   %s sans le garde-fou, S1 rendrait « 0 fichier, 0 anomalie » — un VERT AVEUGLE"
          % ("✅" if faux_vert else "❌"))
    if not faux_vert:
        echecs.append("le garde-fou ne porte rien : S1 ne produit pas de faux vert")

    for d_ in (d, d3, d4, d5, d6, d8):
        shutil.rmtree(d_, ignore_errors=True)

    print()
    if echecs:
        print("❌ BANC ROUGE : " + " · ".join(echecs))
        return 1
    print("✅ BANC VERT — le contrôle rougit sur les huit fautes, sait distinguer index et copie de travail, verdit sur le cas propre, "
          "et son garde-fou est prouvé porteur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
