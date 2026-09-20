#!/usr/bin/env python3
"""heldout_hors_git.py — un held-out armé ne doit jamais entrer dans l'historique.

L'INVARIANT GRAVÉ (2026-08-20) :

    Les données brutes d'un held-out ARMÉ sont des données expérimentales
    LOCALES et NON VERSIONNÉES jusqu'au scellement. Aucun mécanisme de commit
    automatique ne doit pouvoir les incorporer à l'historique.

POURQUOI IL A FALLU L'ÉCRIRE. `commit_par_zone` — lancé automatiquement en fin de
session par `auto_maintain.py` — sélectionne ce qu'il commite avec
`git status --porcelain`, fichiers NON SUIVIS compris. `capture-en-attente.json`
entrait donc dans la zone « moteur ». Il n'y est jamais entré en fait, mais pour
une raison qui n'en était pas une : l'invariant des reprises était rouge et
bloquait les commits automatiques. **Une protection accidentelle.** Elle a disparu
le jour où cet invariant a été réparé — le 2026-08-20, quelques minutes avant que
ce fichier soit écrit. Une protection qu'on n'a pas voulue ne protège que jusqu'au
jour où quelqu'un répare autre chose.

CE QUE CE BANC N'OUVRE JAMAIS. Le contenu du held-out. Aucune ligne ici ne lit
`capture-en-attente.json` : on interroge git SUR son chemin, et les cas
synthétiques écrivent leur propre fichier factice. Le protocole interdit de lire,
classer ou inspecter la capture avant scellement ; un test qui la lirait pour
prouver qu'elle est protégée serait la première fuite.

Run: python3 tests/heldout_hors_git.py
"""
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import commit_par_zone as cpz          # le SÉLECTIONNEUR réel, pas une imitation

CAPTURE = os.path.join("tests", "heldout", "capture-en-attente.json")
# `PROTOCOLE.json` a quitté cette liste le 2026-08-21 : il n'est plus suivi après le
# retrait gouverné du cycle L1. L'outil, lui, reste suivi en permanence.
SUIVIS = (os.path.join("tests", "heldout", "capture_heldout.py"),)
fails = []


# ── LE CYCLE DE VIE, ajouté le 2026-08-21 ────────────────────────────────────
# CE QUE CE BANC NE SAVAIT PAS. Il ne connaissait qu'UN état — « PROTOCOLE armé » —
# et lisait toute autre situation comme une panne. Le 21/08, le lot L1 a atteint
# 60/60, a été scellé, et le protocole a été retiré sur autorisation explicite. Le
# banc a rougi sur une TRANSITION RÉELLE ET VOULUE.
#
#     ARMÉ → COLLECTE → 60/60 → SCELLÉ → DÉSARMÉ
#
# ⚠️ ON N'ÉTEINT PAS UN ROUGE EN DÉPLAÇANT SON ATTENDU. Même principe que
# `ronde_annonce` : on apprend à l'instrument une transition prouvée AILLEURS —
# ici tools/heldout-L1-cycle-de-vie-2026-08-21.md, qui porte le sceau, la boîte
# noire intacte, le contenu byte-identique et l'autorisation nommée.
#
# CE QUE LA CLASSIFICATION LIT, ET CE QU'ELLE NE LIT PAS. Les métadonnées du
# protocole (fichier de configuration, versionné, public), les NOMS des lots et
# leur mtime. Jamais `capture-en-attente.json`, jamais le contenu d'un lot : ni
# requêtes, ni classements. La date de scellement se lit sur la mtime du lot,
# précisément pour ne pas avoir à l'ouvrir.

VALIDES = ("ARME", "COLLECTE", "SCELLE", "DESARME")


def cycle(racine):
    """{etat, rouges} — l'état du cycle de vie, et ce qui cloche, sans rien ouvrir."""
    hd = os.path.join(racine, "tests", "heldout")
    proto = os.path.join(hd, "PROTOCOLE.json")
    lots = sorted(glob.glob(os.path.join(hd, "heldout-*.json")))
    conserves = sorted(glob.glob(os.path.join(hd, "PROTOCOLE.json.desarme-*")))
    a_proto, a_lot = os.path.exists(proto), bool(lots)
    rouges = []

    if not a_proto and not a_lot:
        # 4 — un protocole disparu AVANT tout scellement : la collecte s'est
        #     interrompue sans rien produire, et personne ne l'a dit.
        return {"etat": "ABSENT_AVANT_SCELLEMENT", "lots": [],
                "rouges": ["protocole absent AVANT tout scellement"]}

    if a_proto and not a_lot:
        etat = "ARME"
    elif not a_proto and a_lot:
        # 3 — désarmé après scellement. Valide SI la copie du protocole est conservée :
        #     un retrait qui efface ce qui a armé le lot rend le lot inauditable.
        etat = "DESARME"
        if not conserves:
            rouges.append("protocole retire sans copie conservee — le lot devient inauditable")
    else:
        # Protocole présent ET lot scellé. Deux situations très différentes.
        etat = "SCELLE"
        try:
            arme = json.load(open(proto, encoding="utf-8")).get("arme_le", "")
        except Exception:
            arme = ""
            rouges.append("protocole illisible")
        scelle = datetime.datetime.fromtimestamp(
            os.path.getmtime(lots[-1])).isoformat(timespec="seconds")
        # 6 — le compteur repart sous le protocole QUI A DÉJÀ PRODUIT un lot.
        #     `sceller` vide la file d'attente : sans ce contrôle, un lot L2
        #     démarre tout seul et personne ne l'a décidé.
        if arme and arme < scelle:
            rouges.append(
                "collecte relancee sous le protocole d'origine (arme %s < scelle %s) :"
                " un lot suivant demande un protocole explicitement recree" % (arme, scelle))
    for l in lots:
        # 5 — un lot scellé qui n'est pas ignoré part au premier `git add -A`.
        if subprocess.run(["git", "-C", racine, "check-ignore", "-q",
                           os.path.relpath(l, racine)]).returncode != 0:
            rouges.append("lot scelle NON ignore par git : %s" % os.path.basename(l))
    return {"etat": etat, "lots": [os.path.basename(x) for x in lots], "rouges": rouges}


def ok(l):
    print("  OK   %s" % l)


def ko(l, d=""):
    print("  FAIL %s%s" % (l, ("  -- " + d) if d else ""))
    fails.append(l)


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd] + list(a), capture_output=True, text=True)


def faux_tronc(avec_regle=True):
    """Un dépôt jetable qui rejoue le cas, avec la VRAIE règle du .gitignore.

    La règle est copiée du dépôt réel : le banc vérifie la règle qui protège
    vraiment, pas une règle qu'il se serait écrite pour l'occasion.
    """
    d = os.path.realpath(tempfile.mkdtemp(prefix="heldout-garde."))
    os.makedirs(os.path.join(d, "tests", "heldout"))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        regles = f.read()
    if not avec_regle:
        regles = regles.replace(CAPTURE, "# SABOTAGE : regle retiree")
    open(os.path.join(d, ".gitignore"), "w", encoding="utf-8").write(regles)
    # contenu FACTICE : jamais celui du vrai held-out
    open(os.path.join(d, CAPTURE), "w").write('{"synthetique": true}\n')
    for rel in SUIVIS:
        open(os.path.join(d, rel), "w").write("factice\n")
    git(d, "init", "-q")
    # ⚠️ LE DÉPÔT DOIT ÊTRE RÉALISTE. `git status --porcelain` REPLIE un dossier
    # entièrement non suivi en une seule ligne (`tests/`) : sur un dépôt vierge,
    # aucun des trois fichiers n'apparaît nommément et le banc ne mesurait rien.
    # Dans le vrai tronc, `tests/` est suivi de longue date — on commite donc le
    # protocole et son outil, puis on les modifie, pour retrouver exactement la
    # forme que `modifies()` rencontre en production.
    git(d, "add", "--", ".gitignore", *SUIVIS)
    git(d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "socle")
    for rel in SUIVIS:
        open(os.path.join(d, rel), "a").write("modifie\n")
    return d


def _proto(d, arme_le="2026-01-01T00:00:00", n=60):
    json.dump({"n": n, "arme_le": arme_le},
              open(os.path.join(d, "tests", "heldout", "PROTOCOLE.json"), "w"))


def _lot(d, nom="heldout-L1.json"):
    """Enveloppe FACTICE : ce banc n'ecrit ni ne lit jamais de vraie requete."""
    open(os.path.join(d, "tests", "heldout", nom), "w").write('{"synthetique": true}')


def _conserve(d):
    json.dump({"n": 60, "arme_le": "2026-01-01T00:00:00"},
              open(os.path.join(d, "tests", "heldout",
                                "PROTOCOLE.json.desarme-20260101T0000"), "w"))


# Les sept situations exigees le 2026-08-21. Trois doivent etre VALIDES, quatre ROUGES :
# un banc qui ne verdit sur rien ne vaut pas mieux qu'un banc qui ne rougit sur rien.
SABOTAGES_CYCLE = [
    ("C1 ARME, aucun lot -> valide",
     lambda d: _proto(d), lambda c, p: c["etat"] == "ARME" and p),
    ("C2 SCELLE, protocole recree APRES le sceau -> valide",
     lambda d: (_lot(d), _proto(d, arme_le="2099-01-01T00:00:00")),
     lambda c, p: c["etat"] == "SCELLE" and p),
    ("C3 DESARME apres scellement, copie conservee -> valide",
     lambda d: (_lot(d), _conserve(d)), lambda c, p: c["etat"] == "DESARME" and p),
    ("C4 protocole absent AVANT tout scellement -> ROUGE",
     lambda d: None, lambda c, p: c["etat"] == "ABSENT_AVANT_SCELLEMENT" and not p),
    ("C5 lot scelle NON ignore par git -> ROUGE",
     lambda d: (_lot(d, "heldout-AUTRE.txt"), _conserve(d),
                open(os.path.join(d, "tests", "heldout", "heldout-L9.json"), "w").write("{}"),
                open(os.path.join(d, ".gitignore"), "w").write("# regle retiree\n")),
     lambda c, p: any("NON ignore" in m for m in c["rouges"])),
    ("C6 compteur reparti sous le protocole d'origine -> ROUGE",
     lambda d: (_lot(d), _proto(d, arme_le="2026-01-01T00:00:00")),
     lambda c, p: any("relancee" in m for m in c["rouges"])),
    ("C7 desarme SANS copie conservee -> ROUGE",
     lambda d: _lot(d), lambda c, p: any("sans copie" in m for m in c["rouges"])),
]


def main():
    print("== held-out : hors git avant scellement, cycle de vie apres ==")
    print("   Le contenu de la capture n'est jamais ouvert par ce banc.")

    print("\n> 1. dans le vrai tronc, le chemin est ignoré")
    r = git(ROOT, "check-ignore", "-v", CAPTURE)
    if r.returncode == 0:
        ok("git check-ignore : %s" % r.stdout.strip())
    else:
        ko("le chemin n'est PAS ignoré par git")
    if git(ROOT, "ls-files", "--error-unmatch", CAPTURE).returncode != 0:
        ok("il n'est pas suivi")
    else:
        ko("le held-out est SUIVI par git")
    r = git(ROOT, "log", "--oneline", "--", CAPTURE)
    if not r.stdout.strip():
        ok("et il n'apparaît dans AUCUN commit de l'historique")
    else:
        ko("le held-out est déjà entré dans l'historique",
           r.stdout.strip().splitlines()[0][:80])

    print("\n> 2. le sélectionneur de commit_par_zone ne le voit pas")
    d = faux_tronc(avec_regle=True)
    try:
        vus = cpz.modifies(d)
        if CAPTURE not in vus:
            ok("modifies() sélectionne %d fichier(s), pas la capture" % len(vus))
        else:
            ko("commit_par_zone embarquerait la capture", str(vus))
        if all(s in vus for s in SUIVIS):
            ok("  et il voit bien l'outil de capture : %s" % list(SUIVIS))
        else:
            ko("  la règle emporte trop : le protocole lui-même disparaît", str(vus))
        if cpz.zone(CAPTURE) == "moteur":
            ok("  (la capture appartient bien à la zone qui l'aurait commitée)")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("\n> 3. sabotage — sans la règle, le chemin de fuite se rouvre")
    d = faux_tronc(avec_regle=False)
    try:
        vus = cpz.modifies(d)
        if CAPTURE in vus:
            ok("règle retirée : la capture réapparaît dans la sélection — "
               "le banc reproduit bien le défaut")
        else:
            ko("le sabotage ne rouvre pas la fuite — ce banc ne prouve rien",
               str(vus))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("\n> 4. l'outil de capture reste suivi normalement")
    for rel in SUIVIS:
        if git(ROOT, "ls-files", "--error-unmatch", rel).returncode == 0:
            ok("%s suivi" % rel)
        else:
            ko("%s n'est plus suivi" % rel)

    print("\n> 5. l'ETAT reste lisible sans ouvrir la capture")
    # AVANT le 2026-08-21, ce point exigeait « /60 » dans la sortie : il confondait
    # « lisible » et « armé ». « NON ARMÉ » est un état parfaitement lisible — c'est
    # même la réponse la plus informative après un scellement.
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "heldout", "capture_heldout.py"),
                        "etat"], capture_output=True, text=True)
    ligne = (r.stdout or "").strip().splitlines()[0] if r.stdout.strip() else ""
    if "/60" in ligne or "NON ARM" in ligne.upper():
        ok("etat accessible : %s" % ligne[:70])
    else:
        ko("l'etat n'est plus lisible", ligne[:70])

    print("\n> 6. le CYCLE DE VIE du tronc reel")
    c = cycle(ROOT)
    if c["etat"] in VALIDES and not c["rouges"]:
        ok("etat %s · lot(s) %s · rien a signaler" % (c["etat"], c["lots"] or "aucun"))
    else:
        for m in c["rouges"] or ["etat non reconnu : %s" % c["etat"]]:
            ko(m)

    print("\n> 7. le protocole conserve n'a pas ete retouche")
    cons = sorted(glob.glob(os.path.join(ROOT, "tests", "heldout",
                                         "PROTOCOLE.json.desarme-*")))
    if not cons:
        ok("(aucun protocole conserve — sans objet dans cet etat)")
    for p in cons:
        rel = os.path.relpath(p, ROOT)
        suivi = git(ROOT, "ls-files", "--error-unmatch", rel).returncode == 0
        sale = git(ROOT, "status", "--porcelain", "--", rel).stdout.strip()
        if suivi and not sale:
            ok("%s suivi et identique a sa version enregistree" % os.path.basename(rel))
        elif not suivi:
            ko("%s n'est pas suivi : sa conservation n'est pas verifiable" % rel)
        else:
            ko("%s a ete MODIFIE apres conservation" % rel, sale[:60])

    print("\n> 8. sabotages du cycle de vie — sur des arbres factices")
    for titre, monter, attendu in SABOTAGES_CYCLE:
        d = os.path.realpath(tempfile.mkdtemp(prefix="heldout-cycle."))
        try:
            os.makedirs(os.path.join(d, "tests", "heldout"))
            git(d, "init", "-q")
            open(os.path.join(d, ".gitignore"), "w").write(
                "tests/heldout/capture-en-attente.json\ntests/heldout/heldout-*.json\n")
            monter(d)
            c = cycle(d)
            propre = c["etat"] in VALIDES and not c["rouges"]
            if attendu(c, propre):
                ok("%s" % titre)
            else:
                ko("%s" % titre, "etat=%s rouges=%s" % (c["etat"], c["rouges"]))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print("\n" + "-" * 74)
    if fails:
        print("ROUGE — %d échec(s)" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("VERT — la capture reste locale, hors sélection et hors historique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
