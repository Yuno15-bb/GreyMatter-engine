#!/usr/bin/env python3
"""
sabotages_git_guard.py — éprouve la PRIMITIVE, pas la course git.

DEUX OBJETS, DEUX BANCS. `tests/banc_course_git.py` mesure si les incidents git observés
se reproduisent ; ce fichier-ci mesure si le verrou tient ses propres promesses. Les
confondre donnerait un banc qui passe au vert parce que l'autre moitié marche.

Les neuf sabotages d'ADR-0017 phase 2B. Les 1→4 (S4/S1/S5 sans puis avec protection) vivent
dans `banc_course_git.py --avec-git-guard`, où le scénario est déjà écrit. Les 5→9 portent
sur le mécanisme du verrou et vivent ici.

LA RÈGLE QUE CE FICHIER DÉFEND LE PLUS DUREMENT (sabotage 7) :
    un verrou VIVANT ne se vole pas parce qu'il est ANCIEN.
    Un `git push` porte `timeout=180` : un propriétaire lent est un propriétaire, pas un
    zombie. Voler son verrou remplacerait une course par une corruption silencieuse.

Tout se passe dans des dépôts jetables, jamais dans le tronc.

  python3 tests/sabotages_git_guard.py
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import git_guard  # noqa: E402

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)


def depot():
    d = tempfile.mkdtemp(prefix="sab-git-guard-")
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")            # même garde que l'autre banc
    os.makedirs(os.path.join(d, "state"))
    subprocess.run(["git", "init", "-q", "--initial-branch=main", "."], cwd=d)
    for c, v in (("user.name", "S"), ("user.email", "s@l"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "config", c, v], cwd=d)
    open(os.path.join(d, "f.md"), "w").write("base\n")
    subprocess.run(["git", "add", "f.md"], cwd=d)
    subprocess.run(["git", "commit", "-q", "-m", "C0"], cwd=d)
    return d


def journal(d):
    try:
        return [json.loads(l) for l in
                open(os.path.join(d, "state", "git-journal.jsonl"), encoding="utf-8")]
    except Exception:
        return []


def lock_path(d):
    return os.path.join(d, "state", "git.lock")


# ── 5. deux acquisitions simultanées → une seule gagne ───────────────────────
def sabotage_5():
    """⚠️ PREMIÈRE VERSION FAUSSE, GARDÉE EN MÉMOIRE ICI. Elle lançait 8 processus qui
    acquéraient puis mouraient AUSSITÔT. Résultat : 4 « gagnants » — et c'était le
    comportement CORRECT, puisqu'un propriétaire mort laisse un verrou légitimement
    récupérable. Le sabotage mesurait « 8 processus qui meurent », pas « 8 acquisitions
    simultanées ». Deux corrections : les gagnants TIENNENT le verrou pendant la course,
    et tous partent sur une barrière commune au lieu d'espérer que Popen les synchronise."""
    print("\n5. DEUX ACQUISITIONS SIMULTANÉES — une seule doit gagner")
    d = depot()
    try:
        top = os.path.join(d, "TOP")
        code = ("import sys,os,time;sys.path.insert(0,%r);import git_guard\n"
                "open(%r+'/PRET-%%s','w').write('1')\n"                # « je suis en place »
                "while not os.path.exists(%r): time.sleep(0.005)\n"   # barrière commune
                "j=git_guard.acquerir('acteur-%%s','commit',['f.md'],depot=%r)\n"
                "print('GAGNE' if j else 'REFUSE',flush=True)\n"
                "if j:\n"
                "    time.sleep(1.5)\n"                                # il TIENT le verrou
                "    git_guard.liberer(j,%r)\n"
                % (os.path.join(BRAIN, "hooks"), d, top, d, d))
        procs = [subprocess.Popen([sys.executable, "-c", code % (i, i)],
                                  stdout=subprocess.PIPE, text=True) for i in range(8)]
        # ATTENDRE LA PRÉSENCE RÉELLE DES 8, pas une durée fixe. Un `sleep(0.6)` a suffi
        # tant que le banc tournait seul ; lancé en même temps que les autres, la machine
        # chargée en laissait partir moins de huit et le banc rougissait sans qu'aucune
        # propriété du verrou ne soit en cause. Un banc qui dépend de la charge machine
        # mesure la machine.
        limite = time.time() + 30
        while len([f for f in os.listdir(d) if f.startswith("PRET-")]) < 8:
            if time.time() > limite:
                ko("seulement %d/8 processus en place — banc non concluant"
                   % len([f for f in os.listdir(d) if f.startswith("PRET-")]))
                return
            time.sleep(0.01)
        open(top, "w").write("go")
        sorties = [p.communicate()[0].strip() for p in procs]
        gagnants = sorties.count("GAGNE")
        if gagnants == 1:
            ok("8 processus lâchés ensemble → 1 gagnant, %d refusés" % sorties.count("REFUSE"))
        else:
            ko("%d gagnants au lieu de 1 — l'exclusion mutuelle ne tient pas" % gagnants)
        refus = [e for e in journal(d) if e["evenement"] == "refuse"]
        if refus and all(e.get("proprietaire_actuel") for e in refus):
            ok("les %d refus nomment le propriétaire qui détenait git à cet instant"
               % len(refus))
        else:
            ko("un refus ne dit pas qui possédait git — l'information manquante d'aujourd'hui")
        if not [e for e in journal(d) if e["evenement"] == "recuperation_zombie"]:
            ok("aucune récupération pendant la course : personne n'a volé un verrou vivant")
        else:
            ko("un verrou VIVANT a été récupéré pendant la course")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 6. verrou zombie → récupération GOUVERNÉE ────────────────────────────────
def sabotage_6():
    print("\n6. VERROU ZOMBIE — propriétaire mort, récupération gouvernée")
    d = depot()
    try:
        mort = subprocess.Popen([sys.executable, "-c", "pass"])
        mort.wait()
        json.dump({"acteur": "fantome", "pid": mort.pid, "demarrage": "jadis",
                   "operation": "commit", "perimetre": ["f.md"], "ts": time.time(),
                   "head_avant": "x"}, open(lock_path(d), "w"))
        diag = git_guard.diagnostic(d)
        if diag["etat"] == "recuperable":
            ok("diagnostic : récupérable (%s)" % diag.get("raison"))
        else:
            ko("un propriétaire mort est vu « %s » — le verrou resterait pris à jamais"
               % diag["etat"])
        j = git_guard.acquerir("repreneur", "commit", ["f.md"], depot=d)
        if j:
            ok("acquisition après récupération : obtenue")
        else:
            ko("impossible de reprendre un verrou zombie")
        ev = [e["evenement"] for e in journal(d)]
        if "recuperation_zombie" in ev:
            ok("la récupération est TRACÉE avant d'avoir lieu (%s)" %
               [e for e in journal(d) if e["evenement"] == "recuperation_zombie"][0]["raison"])
        else:
            ko("récupération silencieuse — aucune trace de qui a été retiré")
        git_guard.liberer(j, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 7. propriétaire VIVANT, TTL dépassé → NE PAS VOLER ───────────────────────
def sabotage_7():
    print("\n7. PROPRIÉTAIRE VIVANT MAIS TTL DÉPASSÉ — le verrou ne se vole pas")
    d = depot()
    dormeur = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
    try:
        time.sleep(0.3)
        json.dump({"acteur": "push-lent", "pid": dormeur.pid,
                   "demarrage": git_guard._demarrage(dormeur.pid),
                   "operation": "push", "perimetre": None,
                   "ts": time.time() - 10 * git_guard.TTL,     # 50 minutes d'âge
                   "head_avant": "x"}, open(lock_path(d), "w"))
        diag = git_guard.diagnostic(d)
        if diag["etat"] == "tenu" and diag.get("ttl_depasse"):
            ok("TTL dépassé (%.0f s > %.0f s) ET propriétaire vivant → état « tenu », "
               "raison « %s »" % (diag["age_s"], diag["ttl_s"], diag.get("raison")))
        else:
            ko("état « %s » — un propriétaire vivant a été déclaré récupérable sur son ÂGE"
               % diag["etat"])
        j = git_guard.acquerir("voleur", "commit", ["f.md"], depot=d)
        if j is None:
            ok("acquisition REFUSÉE — le verrou n'a pas été volé")
        else:
            ko("VOL : le verrou d'un processus vivant a été pris parce qu'il était ancien")
        if os.path.exists(lock_path(d)) and \
                json.load(open(lock_path(d)))["acteur"] == "push-lent":
            ok("le verrou appartient toujours à son propriétaire d'origine")
        else:
            ko("le fichier de verrou a été écrasé")
    finally:
        dormeur.kill(); dormeur.wait()
        shutil.rmtree(d, ignore_errors=True)


# ── 8. propriétaire TUÉ en pleine transaction ────────────────────────────────
def sabotage_8():
    print("\n8. PROPRIÉTAIRE TUÉ EN PLEINE TRANSACTION — inspectable puis déterministe")
    d = depot()
    try:
        code = ("import sys,time;sys.path.insert(0,%r);import git_guard;"
                "git_guard.acquerir('tue-en-vol','commit',['f.md'],depot=%r);"
                "print('PRIS',flush=True);time.sleep(60)"
                % (os.path.join(BRAIN, "hooks"), d))
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        p.stdout.readline()                       # attendre la prise réelle du verrou
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        if os.path.exists(lock_path(d)):
            v = json.load(open(lock_path(d)))
            ok("état INSPECTABLE après SIGKILL : verrou de « %s », pid %s, opération %s"
               % (v["acteur"], v["pid"], v["operation"]))
        else:
            ko("le verrou a disparu — plus rien à inspecter après le crash")
        etats = {git_guard.diagnostic(d)["etat"] for _ in range(5)}
        if etats == {"recuperable"}:
            ok("diagnostic DÉTERMINISTE sur 5 lectures : recuperable")
        else:
            ko("diagnostic instable : %s" % etats)
        j = git_guard.acquerir("suivant", "commit", ["f.md"], depot=d)
        ok("reprise obtenue après crash") if j else ko("reprise impossible après crash")
        # la récupération n'a rien publié : aucun commit n'est apparu
        n = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=d,
                           capture_output=True, text=True).stdout.strip()
        ok("aucune publication silencieuse pendant la récupération (%s commit)" % n) \
            if n == "1" else ko("un commit est apparu pendant la récupération")
        git_guard.liberer(j, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 9. identité absente → refus EXPLICITE ────────────────────────────────────
def sabotage_9():
    print("\n9. IDENTITÉ ABSENTE — refus explicite, jamais d'attribution silencieuse")
    d = depot()
    try:
        for mauvais in (None, "", "   ", 42):
            if git_guard.acquerir(mauvais, "commit", ["f.md"], depot=d) is not None:
                ko("acteur %r accepté — une mutation git serait devenue anonyme" % mauvais)
                break
        else:
            ok("None, chaîne vide, blancs et non-chaîne : tous REFUSÉS")
        refus = [e for e in journal(d) if e["evenement"] == "refus_identite_absente"]
        ok("les %d refus sont journalisés" % len(refus)) if len(refus) == 4 else \
            ko("%d refus journalisés sur 4" % len(refus))
        if not os.path.exists(lock_path(d)):
            ok("aucun verrou n'a été créé au nom de personne")
        else:
            ko("un verrou anonyme existe")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 10. PID réutilisé — le PID seul ne suffit pas à identifier ───────────────
def sabotage_10():
    print("\n10. PID RÉUTILISÉ — un pid vivant n'est pas forcément LE propriétaire")
    d = depot()
    dormeur = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
    try:
        time.sleep(0.3)
        # pid bien vivant, mais l'heure de démarrage enregistrée n'est pas la sienne :
        # c'est exactement la signature d'un PID recyclé par le système.
        json.dump({"acteur": "ancien", "pid": dormeur.pid,
                   "demarrage": "Mon Jan  1 00:00:00 1990", "operation": "commit",
                   "perimetre": None, "ts": time.time(), "head_avant": "x"},
                  open(lock_path(d), "w"))
        diag = git_guard.diagnostic(d)
        if diag["etat"] == "recuperable" and "réutilisé" in (diag.get("raison") or ""):
            ok("détecté : %s" % diag["raison"])
        else:
            ko("PID recyclé vu « %s » — le verrou serait gardé par un innocent"
               % diag["etat"])
    finally:
        dormeur.kill(); dormeur.wait()
        shutil.rmtree(d, ignore_errors=True)


# ── 11. libérer ne retire que SON verrou ─────────────────────────────────────
def sabotage_11():
    print("\n11. LIBÉRATION — on ne retire jamais le verrou d'un autre")
    d = depot()
    try:
        vrai = git_guard.acquerir("proprietaire", "commit", ["f.md"], depot=d)
        faux = dict(vrai, acteur="usurpateur", pid=vrai["pid"] + 1, ts=vrai["ts"] + 1)
        git_guard.liberer(faux, d)
        if os.path.exists(lock_path(d)):
            ok("un jeton étranger ne libère pas le verrou en place")
        else:
            ko("VOL PAR LIBÉRATION : un tiers a retiré le verrou du propriétaire")
        git_guard.liberer(vrai, d)
        ok("le vrai propriétaire libère") if not os.path.exists(lock_path(d)) else \
            ko("le propriétaire n'arrive pas à libérer son propre verrou")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 12. le journal répond-il à LA question ? ─────────────────────────────────
def sabotage_12():
    print("\n12. LE JOURNAL — « qui a tenté quoi, quand, pendant que qui possédait git ? »")
    d = depot()
    try:
        with git_guard.transaction("acteur-A", "commit", ["f.md"], depot=d):
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=d)
            refuse = git_guard.acquerir("acteur-B", "reset", ["f.md"], depot=d)
        j = journal(d)
        manque = []
        acquis = next((e for e in j if e["evenement"] == "acquis"), {})
        for champ in ("acteur", "pid", "operation", "perimetre", "head_avant", "quand"):
            if not acquis.get(champ) and acquis.get(champ) != []:
                manque.append("acquis." + champ)
        ref = next((e for e in j if e["evenement"] == "refuse"), {})
        if not ref.get("proprietaire_actuel"):
            manque.append("refuse.proprietaire_actuel")
        lib = next((e for e in j if e["evenement"] == "libere"), {})
        for champ in ("head_apres", "fichiers_commites", "duree_s"):
            if champ not in lib:
                manque.append("libere." + champ)
        if manque:
            ko("champs absents du journal : %s" % ", ".join(manque))
        else:
            ok("acquisition, refus nommant le propriétaire, et libération certifiant "
               "HEAD après + fichiers réels")
        if refuse is None and ref.get("acteur") == "acteur-B" \
                and ref["proprietaire_actuel"].get("acteur") == "acteur-A":
            ok("le refus de B nomme A comme détenteur — l'information qui manquait le 25/08")
        else:
            ko("le journal ne relie pas le refusé au détenteur")
        # le résultat réel est OBSERVÉ, pas recopié de l'intention
        if lib.get("head_a_bouge") is True and lib.get("head_apres") != lib.get("head_avant"):
            ok("la libération CERTIFIE le résultat réel (HEAD %s → %s)"
               % (lib["head_avant"][:7], lib["head_apres"][:7]))
        else:
            ko("la libération n'observe pas le résultat réel")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print("=" * 78)
    print("SABOTAGES DE git_guard — la primitive, pas la course git")
    print("  TTL = %.0f s · dépôts jetables · aucun accès au tronc" % git_guard.TTL)
    print("=" * 78)
    for f in (sabotage_5, sabotage_6, sabotage_7, sabotage_8, sabotage_9,
              sabotage_10, sabotage_11, sabotage_12):
        try:
            f()
        except Exception as e:
            ko("%s a levé : %s" % (f.__name__, e))
    print("\n" + "-" * 78)
    if fails:
        print("ROUGE — %d sabotage(s) en échec :" % len(fails))
        for f in fails:
            print("   · %s" % f)
        return 1
    print("VERT — les 8 sabotages du verrou passent.")
    print("  Portée : le MÉCANISME du verrou. Ne dit rien des producteurs, qui ne")
    print("  l'appellent pas encore.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
