#!/usr/bin/env python3
"""BANC — les deux bouts de l'ADR-0019 : le bilan (brain_doctor) et l'écriture (on_fiche_write).

Il exerce `hooks/brain_doctor.py`, c'est-à-dire EXACTEMENT le code qui rend le rapport
d'intégrité du tronc. Le banc ne réimplémente aucun contrôle : il fabrique des arbres et
lit le verdict rendu dans `state/doctor.json`.

REPRODUCTIBLE DEPUIS LE DÉPÔT SEUL. Chaque cas se joue dans un TRONC JETABLE (dossier
temporaire désigné par BRAIN_HOME), avec ses propres `meta/topics.json` et `meta/familles.json`.
Aucune fiche du tronc n'est lue ni touchée : le banc ne peut donc pas virer au rouge parce
qu'une autre session a écrit dans le Brain — défaut mesuré le 17/09, où le témoin du chantier
rappel a bougé de 25/40 à 24/40 pour cette seule raison.

POURQUOI CE BANC EXISTE (récolte J, 16/09)
    Deux vérificateurs réels du tronc étaient incapables de rougir : ils rendaient un verdict
    sans qu'aucune situation connue ne les fasse jamais dire non. Un contrôle qu'on n'a pas vu
    rougir ne protège de rien. Les sept sabotages ci-dessous sont chacun une faute RÉELLE,
    mesurée dans le tronc le 17/09 : 133 relations d'un type que la carte jette en silence,
    4 relations vers une fiche inexistante, 23 sujets étrangers aux 12 validés, 51 fiches sans
    sujet, une dérive `based_on` / `base_sur`.

S6 EST LA CONTRE-ÉPREUVE DE L'INSTRUMENT LUI-MÊME : on retire la source des sujets et on
vérifie que le docteur DIT que le contrôle n'a pas tourné, au lieu de rendre un arbre sain.

LES QUATRE CAS MUETS (M1-M4) SONT L'AUTRE MOITIÉ DE LA PREUVE. Un contrôle qui rougit sur
tout ne vaut pas mieux qu'un contrôle qui ne rougit sur rien : ils écrivent ce que
l'ADR-0019 AUTORISE — le type `precise`, le fourre-tout `lie_a` accompagné de sa raison, la
forme à tirets, une relation vers un document de `vision/` — et vérifient que le docteur se
tait. M4 est né d'une accusation fausse mesurée le 17/09 : `gmatter-vision-continuite` était
dite pointer dans le vide vers un document qui est sur le disque.

LE TROISIÈME VOLET (E1-E4) ÉPROUVE L'AUTRE BOUT — `hooks/on_fiche_write.py`. Le docteur voit
l'arbre entier et ne sait pas quand une fiche a été écrite ; il ne peut donc PAS tenir « le
sujet est obligatoire sur les fiches neuves », sauf à accuser les 51 anciennes. Le hook, lui,
ne voit que la fiche qu'on vient de déposer : E1-E3 vérifient qu'il consigne un sujet absent,
un type inventé et un `lie_a` sans raison ; E4 vérifie qu'une fiche conforme ne laisse RIEN
dans le journal — un journal qui note tout ne distingue plus rien.

Lancer : python3 tests/relations_et_sujets.py   (rc != 0 si un contrôle ne rougit pas)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
DOCTEUR = os.path.join(RACINE, "hooks", "brain_doctor.py")

# Les sujets du tronc jetable ne sont PAS ceux du vrai tronc : le docteur doit juger sur la
# source qu'il trouve, pas sur une liste recopiée dans son code. Si un jour il recopiait les
# 12 sujets réels, le cas S4 passerait au vert et ce banc le dirait.
TOPICS = {"_lisez_moi": "source jetable du banc", "topics": [
    {"id": "preuve-et-verification", "nom": "Preuve"}, {"id": "le-brain", "nom": "Le Brain"}]}
FAMILLES = {"_lisez_moi": "registre jetable du banc", "familles": {"le-cerveau": {
    "titre": "Le Brain lui-même", "quand": "le tronc, ses contrôles, sa carte",
    "lexique": ["brain", "fiche", "carte"]}}}

MERE = """---
name: fiche-mere
description: "Fiche d'essai : la source citée par sa voisine."
topic: preuve-et-verification
metadata:
  type: project
---

## En clair

Le corps cite [[fiche-fille]] pour que le lien existe des deux côtés.
"""

FILLE = """---
name: fiche-fille
description: "Fiche d'essai : elle déclare une relation typée vers sa source."
tags: [le-cerveau]
topic: le-brain
relations:
  base_sur: [fiche-mere]
metadata:
  type: lesson
---

## En clair

Le corps cite [[fiche-mere]], comme la convention l'exige.
"""

CARTE = "# Carte\n\n- [[fiche-mere]] — la source.\n- [[fiche-fille]] — ce qui s'appuie dessus.\n"


def tronc_jetable():
    """Un tronc neuf et SAIN : deux fiches, une relation typée valide, deux sujets valides."""
    d = tempfile.mkdtemp(prefix="banc-relations-")
    for sous in ("projects/socle", "lessons", "meta", "state"):
        os.makedirs(os.path.join(d, sous), exist_ok=True)
    ecrire(d, "MEMORY.md", CARTE)
    ecrire(d, "projects/socle/fiche-mere.md", MERE)
    ecrire(d, "lessons/fiche-fille.md", FILLE)
    json.dump(TOPICS, open(os.path.join(d, "meta", "topics.json"), "w"), ensure_ascii=False)
    json.dump(FAMILLES, open(os.path.join(d, "meta", "familles.json"), "w"), ensure_ascii=False)
    # lessons/INDEX.md est un ARTEFACT (décision du 14/08) : on le fait ÉCRIRE par son
    # générateur, sinon le tronc d'essai naîtrait déjà « dérivé » et aucun sabotage ne
    # prouverait plus rien — le rapport serait rouge avant qu'on y touche.
    subprocess.run([sys.executable, os.path.join(RACINE, "hooks", "index_lecons.py")],
                   env=dict(os.environ, BRAIN_HOME=d), capture_output=True, text=True)
    return d


def ecrire(d, rel, txt):
    open(os.path.join(d, rel), "w", encoding="utf-8").write(txt)


def rapport(d):
    """Le verdict du VRAI docteur sur ce tronc-là. `--json` écrit state/doctor.json."""
    env = dict(os.environ, BRAIN_HOME=d)
    subprocess.run([sys.executable, DOCTEUR, "--json"], env=env, capture_output=True, text=True)
    return json.load(open(os.path.join(d, "state", "doctor.json"), encoding="utf-8"))


CAS = []


def cas(nom, cle, attendu_dans=None):
    """Enregistre un sabotage : il doit remplir `cle`, et laisser les autres contrôles muets."""
    def deco(f):
        CAS.append((nom, cle, attendu_dans, f))
        return f
    return deco


@cas("type de relation hors vocabulaire", "relations_type_inconnu", "voisin_de")
def _s1(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("base_sur:", "voisin_de:"))


@cas("orthographe dérivée du même type", "relations_type_inconnu", "base_sur")
def _s2(d):
    # `based_on` n'est pas un type de plus : c'est `base_sur` mal écrit. Le message doit le
    # nommer, sinon on « tranche » un vocabulaire qui n'a jamais divergé.
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("base_sur:", "based_on:"))


@cas("relation vers une fiche qui n'existe pas", "relations_cible_morte", "fiche-disparue")
def _s3(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("[fiche-mere]", "[fiche-disparue]"))


@cas("sujet étranger à la source", "sujet_invalide", "architecture-et-conception")
def _s4(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("topic: le-brain",
                                                      "topic: architecture-et-conception"))


@cas("sujet absent", "sujet_absent", "aucun sujet")
def _s5(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("topic: le-brain\n", ""))


@cas("fourre-tout `lie_a` sans sa raison", "lie_a_sans_raison", "fiche-mere")
def _s7(d):
    # Faute LÉGÈRE par construction : la raison est exigée à l'écriture, pas rattrapée après
    # coup. Le docteur doit la DIRE sans faire rougir le tronc — inventer 239 raisons pour
    # les fiches d'avant l'ADR-0019 serait fabriquer de la provenance.
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("base_sur: [fiche-mere]",
                                                      "lie_a: [fiche-mere]"))


@cas("type inconnu écrit en forme à tirets", "relations_type_inconnu", "voisin_de")
def _s8(d):
    # La forme à tirets était JETÉE EN SILENCE avant le 17/09 : l'analyseur n'acceptait que
    # les crochets, et 5 fiches du tronc l'utilisaient déjà. Ce cas prouve qu'elle est lue.
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("  base_sur: [fiche-mere]",
                                                      "  voisin_de:\n    - fiche-mere"))


@cas("la source des sujets a disparu", "vocabulaire_injoignable", "NON JOUÉ")
def _s6(d):
    # La faute de S4 EST là, mais l'instrument qui la voit ne l'est plus.
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("topic: le-brain",
                                                      "topic: architecture-et-conception"))
    os.remove(os.path.join(d, "meta", "topics.json"))


MUETS = []


def muet(nom):
    """Enregistre une écriture AUTORISÉE par l'ADR-0019 : le docteur doit rester muet."""
    def deco(f):
        MUETS.append((nom, f))
        return f
    return deco


@muet("le type `precise`, ouvert le 17/09")
def _m1(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("base_sur:", "precise:"))


@muet("`lie_a` avec sa raison, en forme à tirets")
def _m2(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace(
        "  base_sur: [fiche-mere]",
        "  lie_a:\n    - fiche-mere: les deux décrivent le même piège de cache"))


@muet("un type valide en forme à tirets, sans raison")
def _m3(d):
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace("  base_sur: [fiche-mere]",
                                                      "  base_sur:\n    - fiche-mere"))


@muet("relation vers un document de vision, hors corpus")
def _m4(d):
    os.makedirs(os.path.join(d, "vision"), exist_ok=True)
    ecrire(d, "vision/recit-source-2026-09-17.md",
           "# Récit source\n\nUn document de vision, hors du corpus de rappel.\n")
    ecrire(d, "lessons/fiche-fille.md", FILLE.replace(
        "  base_sur: [fiche-mere]",
        "  base_sur: [fiche-mere]\n  lie_a:\n    - recit-source-2026-09-17: d'où vient la fiche"))


ECRITURES = []


def ecriture(nom, attendu):
    """Enregistre un cas joué À L'ÉCRITURE. `attendu` = l'écart que le hook doit consigner,
    ou None quand la fiche est conforme et que le hook doit rester silencieux."""
    def deco(f):
        ECRITURES.append((nom, attendu, f))
        return f
    return deco


def journal_ecriture(d, rel, txt):
    """Écrit une fiche, fait tourner le VRAI hook PostToolUse dessus, rend ce qu'il a consigné.

    C'est l'autre bout de la règle : le docteur regarde l'arbre entier et ne sait pas quand une
    fiche a été écrite ; seul ce hook-ci voit passer les fiches NEUVES, et c'est donc lui, et
    lui seul, qui peut tenir « le sujet est obligatoire sur les fiches neuves » (ADR-0019)."""
    ecrire(d, rel, txt)
    charge = json.dumps({"tool_input": {"file_path": os.path.join(d, rel)}})
    subprocess.run([sys.executable, os.path.join(RACINE, "hooks", "on_fiche_write.py")],
                   env=dict(os.environ, BRAIN_HOME=d), input=charge,
                   capture_output=True, text=True)
    chemin = os.path.join(d, "state", "vocabulaire-a-l-ecriture.jsonl")
    if not os.path.exists(chemin):
        return []
    return [json.loads(l) for l in open(chemin, encoding="utf-8") if l.strip()]


@ecriture("fiche neuve sans sujet", "absent")
def _e1(d):
    return journal_ecriture(d, "lessons/fiche-neuve.md",
                            FILLE.replace("name: fiche-fille", "name: fiche-neuve")
                                 .replace("topic: le-brain\n", ""))


@ecriture("fiche neuve au type de relation inventé", "type-hors-vocabulaire")
def _e2(d):
    return journal_ecriture(d, "lessons/fiche-neuve.md",
                            FILLE.replace("name: fiche-fille", "name: fiche-neuve")
                                 .replace("base_sur: [fiche-mere]", "voisin_de: [fiche-mere]"))


@ecriture("fiche neuve au fourre-tout `lie_a` sans raison", "lie_a-sans-raison")
def _e3(d):
    return journal_ecriture(d, "lessons/fiche-neuve.md",
                            FILLE.replace("name: fiche-fille", "name: fiche-neuve")
                                 .replace("base_sur: [fiche-mere]", "lie_a: [fiche-mere]"))


@ecriture("fiche neuve conforme — le hook doit se taire", None)
def _e4(d):
    return journal_ecriture(d, "lessons/fiche-neuve.md",
                            FILLE.replace("name: fiche-fille", "name: fiche-neuve").replace(
                                "  base_sur: [fiche-mere]",
                                "  base_sur: [fiche-mere]\n  lie_a:\n"
                                "    - fiche-mere: les deux décrivent le même piège"))


def main():
    ennuis = []
    d = tronc_jetable()
    try:
        sain = rapport(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    surveillees = ("relations_type_inconnu", "relations_cible_morte", "sujet_invalide",
                   "sujet_absent", "lie_a_sans_raison", "vocabulaire_injoignable")
    # Ce que l'ADR-0019 fait MESURER sans faire rougir : la règle ne vaut que pour les fiches
    # neuves, et le docteur n'a aucun moyen de savoir quand une fiche a été écrite.
    informatifs = ("sujet_absent", "lie_a_sans_raison")
    print("TRONC SAIN — total %d, ok=%s" % (sain["total"], sain["ok"]))
    for k in surveillees:
        print("   %-26s %d" % (k, len(sain[k])))
        if sain[k]:
            ennuis.append("sur un tronc sain, « %s » signale %s — le contrôle accuse une "
                          "fiche correcte" % (k, sain[k][:2]))
    if not sain["ok"]:
        ennuis.append("le tronc d'essai n'est pas vert (total %d) : un sabotage ne prouverait "
                      "rien, puisque le rapport est déjà rouge sans lui — %s"
                      % (sain["total"], {k: v for k, v in sain.items()
                                         if isinstance(v, list) and v}))

    print("\nSABOTAGES")
    for nom, cle, attendu, f in CAS:
        d = tronc_jetable()
        try:
            f(d)
            r = rapport(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        touche = r[cle]
        rougit = "ROUGE" if not r["ok"] else "vert"
        print("   %-42s %-5s %s" % (nom, rougit, touche[:1] or "— RIEN"))
        if not touche:
            ennuis.append("« %s » : le contrôle « %s » n'a rien vu — il est incapable de "
                          "rougir sur la faute qu'il prétend couvrir" % (nom, cle))
        elif attendu and not any(attendu in x for x in touche):
            ennuis.append("« %s » : le contrôle rougit mais son message ne nomme pas « %s » "
                          "(%s) — il signale sans dire quoi réparer" % (nom, attendu, touche[:1]))
        # Les autres contrôles surveillés doivent rester muets : un sabotage qui allume tout
        # ne prouve pas que le bon contrôle a vu quelque chose.
        for autre in surveillees:
            if autre != cle and r[autre]:
                ennuis.append("« %s » : le contrôle « %s » s'est allumé alors qu'il n'est "
                              "pas concerné (%s)" % (nom, autre, r[autre][:1]))
        # S5 et S7 : ces deux mesures ne doivent PAS changer le verdict. L'ADR-0019 rend le
        # sujet et la raison obligatoires sur les fiches NEUVES ; faire rougir le tronc
        # accuserait des fiches écrites avant que la règle existe.
        if cle in informatifs and not r["ok"]:
            ennuis.append("« %s » : le docteur sort en ROUGE sur une mesure qui n'est pas une "
                          "faute — c'est appliquer l'ADR-0019 aux fiches d'avant" % nom)
        if cle not in informatifs and r["ok"]:
            ennuis.append("« %s » : le docteur reste VERT malgré la faute" % nom)

    print("\nÉCRITURES AUTORISÉES — le docteur doit se taire")
    for nom, f in MUETS:
        d = tronc_jetable()
        try:
            f(d)
            r = rapport(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        bavards = {k: r[k][:1] for k in surveillees if r[k]}
        print("   %-42s %-5s %s" % (nom, "vert" if r["ok"] and not bavards else "ROUGE",
                                    bavards or "— muet"))
        if bavards:
            ennuis.append("« %s » : écriture autorisée par l'ADR-0019, et le docteur la "
                          "signale quand même (%s) — un contrôle qui accuse le permis vaut "
                          "aussi peu qu'un contrôle aveugle" % (nom, bavards))
        elif not r["ok"]:
            ennuis.append("« %s » : écriture autorisée, et le docteur sort en rouge (%s)"
                          % (nom, {k: v for k, v in r.items() if isinstance(v, list) and v}))

    print("\nÀ L'ÉCRITURE — ce que le hook consigne au moment où la fiche est déposée")
    for nom, attendu, f in ECRITURES:
        d = tronc_jetable()
        try:
            consigne = f(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        vus = [x.get("ecart") for x in consigne]
        print("   %-42s %-5s %s" % (nom, "VU" if vus else "muet", vus or "— rien"))
        if attendu is None and vus:
            ennuis.append("« %s » : fiche conforme, et le hook la consigne quand même (%s) — "
                          "un journal qui note tout ne distingue plus rien" % (nom, vus))
        elif attendu is not None and attendu not in vus:
            ennuis.append("« %s » : le hook n'a pas consigné « %s » (%s) — la règle de "
                          "l'ADR-0019 ne tient donc sur aucune fiche neuve" % (nom, attendu, vus))

    if ennuis:
        print("\n❌ %d défaut(s) — un contrôle qui ne rougit pas ne protège de rien :" % len(ennuis))
        for e in ennuis:
            print("     %s" % e)
        return 1
    print("\n✅ les %d fautes font parler le docteur, les %d écritures permises le laissent "
          "muet, et le hook d'écriture voit les %d cas neufs"
          % (len(CAS), len(MUETS), len(ECRITURES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
