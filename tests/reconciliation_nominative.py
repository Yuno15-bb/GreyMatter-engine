#!/usr/bin/env python3
"""
reconciliation_nominative.py — `--seulement` : appliquer un sous-ensemble NOMMÉ, et rien d'autre.

POURQUOI CE MODE EXISTE. `--accepter` appliquait le plan ENTIER. Le 2026-08-27, seules 24
opérations sur 28 étaient autorisées — les skills, pas deux fiches d'agents ni deux
annotations. Il ne restait que deux mauvaises portes : éditer à la main le fichier de
proposition, ou écrire dans le manifeste soi-même. Les deux contournent l'outil, donc ses
garde-fous. Ce banc éprouve la troisième porte, la propre.

CE QU'IL VÉRIFIE SURTOUT — que l'autorisation ne s'élargit JAMAIS toute seule :
  · une identité nommée dont l'ACTE a changé depuis la validation → refus ;
  · une liste vide n'est pas un raccourci pour « tout » ;
  · aucune entrée hors plan ne bouge, vérifié sur le fichier écrit, pas sur l'intention ;
  · et si quelque chose déborde quand même, le manifeste est RESTAURÉ.

Tout se passe dans des troncs jetables : le vrai manifeste n'est jamais ouvert en écriture.

  python3 tests/reconciliation_nominative.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)

CARTE = """# Carte

## 🧭 Section A

[[alpha]] · [[beta]] · [[gamma]] (annotation neuve)

## 🧭 Section B

[[delta]] · [[epsilon]]
"""

FICHE = "---\nname: %s\ndescription: d\n---\n\n## En clair\n\nx\n"


def tronc(entrees_manifeste, carte=CARTE, fiches=("alpha", "beta", "gamma", "delta", "epsilon")):
    """Tronc jetable complet : carte, manifeste, fiches, et l'outil lui-même."""
    d = tempfile.mkdtemp(prefix="reconc-nom-")
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")
    os.makedirs(os.path.join(d, "tools", "cartes"))
    os.makedirs(os.path.join(d, "hooks"))
    os.makedirs(os.path.join(d, "lessons"))
    for f in ("reconcilier.py", "regle_entree.py"):
        shutil.copy(os.path.join(BRAIN, "tools", "cartes", f), os.path.join(d, "tools", "cartes", f))
    shutil.copy(os.path.join(BRAIN, "hooks", "identite_fiche.py"), os.path.join(d, "hooks"))
    open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8").write(carte)
    for f in fiches:
        open(os.path.join(d, "lessons", f + ".md"), "w", encoding="utf-8").write(FICHE % f)
    json.dump({"entrees": entrees_manifeste},
              open(os.path.join(d, "tools", "cartes", "manifeste-carte.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)
    return d


def lancer(d, *args):
    return subprocess.run([sys.executable, os.path.join(d, "tools", "cartes", "reconcilier.py")]
                          + list(args), capture_output=True, text=True, cwd=d)


def manifeste(d):
    return json.load(open(os.path.join(d, "tools", "cartes", "manifeste-carte.json"),
                          encoding="utf-8"))["entrees"]


def entree(slug, **kw):
    e = {"fiche": slug, "section": "🧭 Section A", "rang": 0, "niveau": 0,
         "annotation": "", "statut_attendu": None, "date_statut": None}
    e.update(kw)
    return e


# ── 1. sous-ensemble appliqué, le reste intact ──────────────────────────────
def cas_1():
    print("\n1. PLAN PARTIEL — 3 identités nommées sur 5 opérations")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        avant = {e["fiche"]: json.dumps(e, sort_keys=True) for e in manifeste(d)}
        r = lancer(d, "--accepter", "--seulement", "beta,gamma,delta")
        ap = manifeste(d)
        noms = {e["fiche"] for e in ap}
        if noms == {"alpha", "beta", "gamma", "delta"}:
            ok("exactement les 3 nommés ajoutés — epsilon reste dehors")
        else:
            ko("entrées après : %s (sortie: %s)" % (sorted(noms), r.stdout.strip()[-120:]))
        inchange = all(json.dumps(e, sort_keys=True) == avant[e["fiche"]]
                       for e in ap if e["fiche"] in avant)
        ok("aucune entrée préexistante modifiée") if inchange else ko("alpha a été modifiée")
        sauv = [f for f in os.listdir(os.path.join(d, "tools", "cartes")) if ".avant-" in f]
        ok("sauvegarde écrite avant modification (%d)" % len(sauv)) if sauv \
            else ko("aucune sauvegarde")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 2. identité absente du plan ─────────────────────────────────────────────
def cas_2():
    print("\n2. IDENTITÉ ABSENTE de la proposition → refus, zéro écriture")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        avant = json.dumps(manifeste(d), sort_keys=True)
        r = lancer(d, "--accepter", "--seulement", "beta,inexistante")
        if r.returncode != 0 and "ne figurent PAS" in r.stdout:
            ok("refus explicite, l'identité fautive est nommée")
        else:
            ko("pas de refus : %s" % r.stdout.strip()[-140:])
        ok("manifeste inchangé") if json.dumps(manifeste(d), sort_keys=True) == avant \
            else ko("le manifeste a été écrit malgré le refus")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 3. proposition périmée ──────────────────────────────────────────────────
def cas_3():
    print("\n3. PROPOSITION PÉRIMÉE — la carte a bougé après le calcul")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        avant = json.dumps(manifeste(d), sort_keys=True)
        with open(os.path.join(d, "MEMORY.md"), "a", encoding="utf-8") as f:
            f.write("\n[[epsilon]]\n")          # la source bouge
        r = lancer(d, "--accepter", "--seulement", "beta")
        if r.returncode != 0 and "PÉRIMÉE" in r.stdout:
            ok("refus : la source a bougé depuis le calcul")
        else:
            ko("appliqué sur une proposition périmée : %s" % r.stdout.strip()[-140:])
        ok("manifeste inchangé") if json.dumps(manifeste(d), sort_keys=True) == avant \
            else ko("écriture malgré la péremption")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 4. l'identité est la même, l'ACTE a changé ──────────────────────────────
def cas_4():
    print("\n4. MÊME IDENTITÉ, ACTE DIFFÉRENT → refus (le cœur du mode nominatif)")
    # gamma est un AJOUT avec annotation. On le met dans le manifeste AVEC une autre
    # annotation : ce n'est plus un ajout, c'est un changement d'annotation.
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        prop = json.load(open(os.path.join(d, "tools", "cartes",
                                           "proposition-reconciliation.json"), encoding="utf-8"))
        # on falsifie le TYPE dans la proposition enregistrée : gamma passe d'AJOUT à
        # ANNOTATION. Le plan vivant, lui, dira toujours AJOUT → divergence détectée.
        aj = [a for a in prop["ajouts"] if a["fiche"] == "gamma"]
        prop["ajouts"] = [a for a in prop["ajouts"] if a["fiche"] != "gamma"]
        prop["annotations"].append({"fiche": "gamma", "avant": "", "apres": "x"})
        json.dump(prop, open(os.path.join(d, "tools", "cartes",
                                          "proposition-reconciliation.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=1)
        avant = json.dumps(manifeste(d), sort_keys=True)
        r = lancer(d, "--accepter", "--seulement", "gamma")
        if r.returncode != 0 and ("a CHANGÉ" in r.stdout or "PÉRIMÉE" in r.stdout):
            ok("refus : autorisé pour un acte, le plan réel en montre un autre")
        else:
            ko("l'acte a changé et c'est passé : %s" % r.stdout.strip()[-160:])
        ok("manifeste inchangé") if json.dumps(manifeste(d), sort_keys=True) == avant \
            else ko("écriture malgré le changement d'acte")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 5. sabotage : une opération non nommée tente de passer ──────────────────
def cas_5():
    print("\n5. SABOTAGE — une opération NON nommée tente d'entrer")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        r = lancer(d, "--accepter", "--seulement", "beta")
        noms = {e["fiche"] for e in manifeste(d)}
        if noms == {"alpha", "beta"}:
            ok("seul beta est entré — gamma, delta, epsilon sont restés dehors")
        else:
            ko("des opérations non nommées sont passées : %s" % sorted(noms))
        if "gamma" not in noms and "delta" not in noms:
            ok("le filtre porte sur les IDENTITÉS, pas sur un compte d'opérations")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 6. doublons dans la liste ───────────────────────────────────────────────
def cas_6():
    print("\n6. DOUBLON dans la liste → comportement déterministe et annoncé")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        r = lancer(d, "--accepter", "--seulement", "beta,beta,gamma")
        noms = {e["fiche"] for e in manifeste(d)}
        if noms == {"alpha", "beta", "gamma"} and "doublon" in r.stdout:
            ok("normalisé, et le dit : « %s »"
               % [l.strip() for l in r.stdout.splitlines() if "doublon" in l][0][:70])
        else:
            ko("comportement flou sur doublon : %s / %s" % (sorted(noms), r.stdout.strip()[-100:]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 7. liste vide ───────────────────────────────────────────────────────────
def cas_7():
    print("\n7. LISTE VIDE → refus, jamais un « tout » implicite")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        avant = json.dumps(manifeste(d), sort_keys=True)
        r = lancer(d, "--accepter", "--seulement", "")
        if r.returncode != 0 and "n'est PAS un raccourci" in r.stdout:
            ok("refus explicite : une liste vide n'autorise rien")
        else:
            ko("liste vide acceptée : %s" % r.stdout.strip()[-140:])
        ok("manifeste inchangé") if json.dumps(manifeste(d), sort_keys=True) == avant \
            else ko("TOUT a été appliqué sur une liste vide")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 8. le reste est reproposé après application ─────────────────────────────
def cas_8():
    print("\n8. APRÈS APPLICATION — seul le NON appliqué est reproposé")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        lancer(d, "--accepter", "--seulement", "beta,gamma")
        r = lancer(d)                       # lecture seule
        reste = r.stdout
        if "beta" not in reste and "gamma" not in reste:
            ok("beta et gamma ont disparu de la proposition")
        else:
            ko("des opérations appliquées sont encore proposées")
        if "delta" in reste and "epsilon" in reste:
            ok("delta et epsilon restent proposés — c'est normal, ils n'étaient pas nommés")
        else:
            ko("les opérations non nommées ont disparu aussi : %s" % reste.strip()[-160:])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 9. le mode global n'a pas changé ────────────────────────────────────────
def cas_9():
    print("\n9. NON-RÉGRESSION — sans --seulement, le plan entier s'applique encore")
    d = tronc([entree("alpha")])
    try:
        lancer(d, "--ecrire")
        lancer(d, "--accepter")
        noms = {e["fiche"] for e in manifeste(d)}
        if noms == {"alpha", "beta", "gamma", "delta", "epsilon"}:
            ok("les 5 entrées présentes — le comportement d'origine est intact")
        else:
            ko("le mode global a régressé : %s" % sorted(noms))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 10. le garde-fou anti-débordement, MIS EN JEU ───────────────────────────
def cas_10():
    """⚠️ CE CAS EXISTE PARCE QU'IL MANQUAIT. Sabotage du garde anti-débordement : le banc
    restait VERT. Cause : dans le chemin normal rien ne déborde jamais, donc retirer un
    contrôle qui ne se déclenche pas ne change rien. Un garde-fou qu'aucun cas ne met en
    jeu est une décoration, pas une barrière.

    Ici on force le débordement : la resynchronisation globale — celle qui réaligne rang,
    niveau et section de TOUTES les entrées — est rendue inconditionnelle dans une COPIE
    jetable de l'outil. `alpha`, hors du plan, a un rang faux : sans le garde, il serait
    corrigé au passage. Autoriser 1 ajout n'autorise pas à réécrire les autres."""
    print("\n10. DÉBORDEMENT PROVOQUÉ → détecté, écriture annulée, manifeste restauré")
    # alpha porte un rang et une section FAUX : la resync les corrigerait.
    d = tronc([entree("alpha", rang=99, section="🧭 Section INVENTÉE")])
    try:
        cible = os.path.join(d, "tools", "cartes", "reconcilier.py")
        src = open(cible, encoding="utf-8").read()
        assert src.count("    if seulement is None:\n        for e in man[\"entrees\"]:") == 1
        open(cible, "w", encoding="utf-8").write(
            src.replace("    if seulement is None:\n        for e in man[\"entrees\"]:",
                        "    if True:\n        for e in man[\"entrees\"]:"))
        lancer(d, "--ecrire")
        avant = json.dumps(manifeste(d), sort_keys=True)
        r = lancer(d, "--accepter", "--seulement", "beta")
        if r.returncode != 0 and "DÉBORDEMENT" in r.stdout:
            ok("débordement DÉTECTÉ : « %s »"
               % [l.strip() for l in r.stdout.splitlines() if "hors plan" in l][0][:66])
        else:
            ko("débordement non détecté : %s" % r.stdout.strip()[-160:])
        if json.dumps(manifeste(d), sort_keys=True) == avant:
            ok("manifeste RESTAURÉ à l'identique — alpha garde son rang 99")
        else:
            ko("le manifeste a été laissé dans un état modifié")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print("=" * 78)
    print("RÉCONCILIATION NOMINATIVE — appliquer ce qui est nommé, et rien d'autre")
    print("=" * 78)
    for f in (cas_1, cas_2, cas_3, cas_4, cas_5, cas_6, cas_7, cas_8, cas_9, cas_10):
        try:
            f()
        except Exception as e:
            ko("%s a levé : %s" % (f.__name__, e))
    print("\n" + "-" * 78)
    if fails:
        print("ROUGE — %d échec(s) :" % len(fails))
        for f in fails:
            print("   · %s" % f)
        return 1
    print("VERT — l'autorisation ne s'élargit jamais toute seule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
