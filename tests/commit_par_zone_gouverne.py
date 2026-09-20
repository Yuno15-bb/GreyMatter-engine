#!/usr/bin/env python3
"""
commit_par_zone_gouverne.py — le VRAI producteur migré, éprouvé sur dépôts jetables.
ADR-0017 phase 3.

CE QUI EST TESTÉ : `hooks/commit_par_zone.py` lui-même, importé, pas une imitation. Si la
migration régresse, ce banc rougit.

COMMENT LA CONCURRENCE EST INJECTÉE — le hook `pre-commit` du dépôt jetable.
    Pour perturber A *pendant* sa transaction, il faut un point d'entrée à l'intérieur de
    `git commit`. Le hook `pre-commit` en est un, et un vrai : git l'exécute alors que la
    transaction est ouverte et que le verrou est tenu. Aucune ligne de `commit_par_zone`
    n'a été modifiée pour rendre ce banc possible — instrumenter le sujet pour pouvoir le
    mesurer aurait mesuré autre chose que lui.

LES DEUX PROTECTIONS NE SE REMPLACENT PAS, ET CE BANC LES SÉPARE :
    · le PATHSPEC (`git commit -- <zone>`) borne ce que le commit embarque. Il tient même
      face à un acteur qui ignore le verrou — cas 2.
    · le VERROU borne qui peut muter l'état partagé. Il ne tient que face à un acteur qui
      le demande — cas 3 et 4.
    Un acteur non coopératif reste donc capable de salir l'INDEX ; il ne peut plus salir
    le COMMIT. C'est exactement pourquoi ADR-0017 exige les deux.

  python3 tests/commit_par_zone_gouverne.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import commit_par_zone as CPZ  # noqa: E402
import git_guard  # noqa: E402

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)


def depot(hook=None):
    d = tempfile.mkdtemp(prefix="cpz-gouverne-")
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")
    os.makedirs(os.path.join(d, "state"))
    for z in ("lessons", "hooks", "sessions"):
        os.makedirs(os.path.join(d, z), exist_ok=True)
    subprocess.run(["git", "init", "-q", "--initial-branch=main", "."], cwd=d)
    for c, v in (("user.name", "S"), ("user.email", "s@l"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "config", c, v], cwd=d)
    # LA FIXTURE DOIT RESSEMBLER À LA PRODUCTION. Sans cette ligne, les dépôts jetables
    # n'ignoraient pas `state/` — et le banc a alors montré commit_par_zone en train de
    # commiter `state/git.lock` PENDANT qu'il le tenait. Le tronc, lui, ignore `state/`
    # (`.gitignore:7`, 0 fichier suivi) : la fixture mentait, pas le producteur. Le
    # défaut restait réel pour tout dépôt sans cette règle, d'où l'exclusion défensive
    # ajoutée en même temps dans commit_par_zone.
    open(os.path.join(d, ".gitignore"), "w").write("state/\n")
    open(os.path.join(d, "lessons", "base.md"), "w").write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "commit", "-q", "-m", "C0"], cwd=d)
    if hook:
        h = os.path.join(d, ".git", "hooks", "pre-commit")
        open(h, "w").write("#!/bin/sh\n" + hook + "\nexit 0\n")
        os.chmod(h, 0o755)
    return d


def fichiers_du_commit(d, ref="HEAD"):
    r = subprocess.run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", ref],
                       cwd=d, capture_output=True, text=True)
    return sorted(x for x in r.stdout.splitlines() if x)


def index(d):
    r = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=d,
                       capture_output=True, text=True)
    return sorted(x for x in r.stdout.splitlines() if x)


def head(d):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d,
                          capture_output=True, text=True).stdout.strip()


def journal(d):
    try:
        return [json.loads(l) for l in
                open(os.path.join(d, "state", "git-journal.jsonl"), encoding="utf-8")]
    except Exception:
        return []


# ── 1. chemin normal ────────────────────────────────────────────────────────
def cas_1():
    print("\n1. CHEMIN NORMAL — une zone seule")
    d = depot()
    try:
        open(os.path.join(d, "lessons", "neuve.md"), "w").write("x\n")
        n = CPZ.commit_par_zone(d, "test: ")
        f = fichiers_du_commit(d)
        ok("1 commit posé, contenu %s" % f) if (n == 1 and f == ["lessons/neuve.md"]) \
            else ko("attendu 1 commit de lessons/neuve.md, obtenu %d commit(s) %s" % (n, f))
        # un fichier NEUF passe : c'est le rôle du `git add`, que le pathspec ne couvre PAS
        ok("un fichier NEUF (non suivi) est bien commité — le `git add` reste nécessaire") \
            if f == ["lessons/neuve.md"] else ko("le fichier neuf n'est pas dans le commit")
        ok("verrou libéré") if git_guard.diagnostic(d)["etat"] == "libre" \
            else ko("verrou resté pris après une transaction réussie")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 2. S4 — deux intrus de POUVOIRS DIFFÉRENTS, et la distinction compte ────
def cas_2():
    """POURQUOI DEUX CAS, ET CE QUE LE PREMIER ESSAI M'A APPRIS.

    La première version injectait `git add` depuis le hook pre-commit — et le pathspec
    semblait percé. Cause : avec `--only`, git EXPORTE `GIT_INDEX_FILE` vers son index
    TEMPORAIRE pour la durée du hook. L'intrus écrivait donc dans l'index du commit en
    cours, pouvoir qu'aucun processus concurrent ne possède. L'injection était trop
    puissante : elle ne modélisait pas la menace observée le 25/08, elle modélisait un
    hook malveillant.

    2a modélise la vraie menace : un acteur EXTERNE, `GIT_INDEX_FILE` désarmé, qui écrit
    dans l'index réel. 2b garde l'autre cas parce qu'il est vrai aussi, et le nomme pour
    ce qu'il est : une LIMITE connue du pathspec, pas une protection en défaut."""
    print("\n2a. S4 — acteur EXTERNE qui stage pendant la transaction (la vraie menace)")
    injection = ('cd "$(git rev-parse --show-toplevel)" && '
                 'unset GIT_INDEX_FILE && '        # ← sinon on écrit dans l'index du commit
                 'echo etranger > lessons/etranger.md && git add -- lessons/etranger.md')
    d = depot(hook=injection)
    try:
        open(os.path.join(d, "lessons", "mienne.md"), "w").write("x\n")
        CPZ.commit_par_zone(d, "test: ")
        f = fichiers_du_commit(d)
        if f == ["lessons/mienne.md"]:
            ok("commit borné au plan : %s — alors que l'intrus avait bien stagé" % f)
        else:
            ko("CONTAMINÉ : le commit embarque %s" % f)
        if os.path.exists(os.path.join(d, "lessons", "etranger.md")):
            ok("l'intrus a réellement agi pendant la transaction")
        else:
            ko("l'injection n'a pas eu lieu — ce test ne prouve rien")
        # MESURÉ, et la nuance compte : le FICHIER n'est pas perdu — contenu intact sur
        # disque, redevenu « non suivi ». Seule l'entrée d'index saute, parce que git
        # réécrit l'index réel en fin de commit `--only`. À comparer à l'ancien
        # `git reset`, qui désindexait TOUT, de TOUT LE MONDE, à CHAQUE passage, même
        # sans concurrence. Le cas 2c mesure la situation réellement observée.
        chemin = os.path.join(d, "lessons", "etranger.md")
        if os.path.exists(chemin) and open(chemin).read().strip() == "etranger":
            ok("le fichier de l'intrus est INTACT sur disque (son entrée d'index saute : "
               "git réécrit l'index réel en fin de commit --only) — aucune perte de contenu")
        else:
            ko("le fichier de l'intrus a été perdu — perte de contenu")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("\n2c. LE CAS RÉELLEMENT OBSERVÉ — un tiers a stagé AVANT que le producteur tourne")
    # Le 2026-08-26 à 01:41, le tronc portait deux fichiers stagés par un agent inactif.
    # ⚠️ MA PREMIÈRE ASSERTION ICI ÉTAIT FAUSSE : j'attendais que leur STAGING survive.
    # Il ne survit pas, et c'est correct — `commit_par_zone` commite tout ce qui a changé,
    # c'est son métier ; le fichier du tiers est donc COMMITÉ, pas détruit. Retirer les
    # `reset` n'a jamais eu pour but de préserver un staging que le producteur va de toute
    # façon consommer. La propriété qui compte, et qui est mesurée ici, est celle que S4
    # menaçait : CHAQUE fichier atterrit dans le commit de SA zone, aucun n'est avalé
    # dans celui d'une autre. C'est ce que « une histoire par commit » veut dire.
    d = depot()
    try:
        open(os.path.join(d, "lessons", "du-tiers.md"), "w").write("travail d un agent\n")
        subprocess.run(["git", "add", "--", "lessons/du-tiers.md"], cwd=d)
        open(os.path.join(d, "hooks", "mienne.py"), "w").write("x\n")
        CPZ.commit_par_zone(d, "test: ")
        savoir, moteur = fichiers_du_commit(d, "HEAD~1"), fichiers_du_commit(d, "HEAD")
        if savoir == ["lessons/du-tiers.md"] and moteur == ["hooks/mienne.py"]:
            ok("chaque fichier dans le commit de SA zone : savoir=%s moteur=%s"
               % (savoir, moteur))
        else:
            ko("zones mélangées : savoir=%s moteur=%s" % (savoir, moteur))
        perdus = [f for f in ("lessons/du-tiers.md", "hooks/mienne.py")
                  if f not in savoir + moteur]
        ok("aucun travail perdu : les 2 fichiers sont dans l'historique") if not perdus             else ko("travail perdu : %s" % perdus)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("\n2b. LIMITE CONNUE — un hook pre-commit qui stage n'est PAS borné par le pathspec")
    injection2 = ('cd "$(git rev-parse --show-toplevel)" && '
                  'echo interne > lessons/interne.md && git add -- lessons/interne.md')
    d = depot(hook=injection2)
    try:
        open(os.path.join(d, "lessons", "mienne.md"), "w").write("x\n")
        CPZ.commit_par_zone(d, "test: ")
        f = fichiers_du_commit(d)
        if "lessons/interne.md" in f:
            ok("limite CONFIRMÉE et documentée : le hook écrit dans l'index temporaire "
               "(GIT_INDEX_FILE) et son fichier entre dans le commit : %s" % f)
            ok("→ le pathspec borne les acteurs EXTERNES, pas le code que git exécute "
               "lui-même. Le pre-commit du tronc ne stage rien (vérifié par grep) ; si un "
               "jour il le faisait, cette protection ne s'appliquerait pas à lui.")
        else:
            ko("la limite ne se reproduit plus — ce test ne décrit plus la réalité, "
               "il faut réinstruire pourquoi")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 3 et 4. acteur COOPÉRATIF : reset puis commit concurrents ───────────────
def cas_3_4():
    for nom, op, geste in (("3. RESET CONCURRENT", "reset", "git reset -q"),
                           ("4. COMMIT CONCURRENT", "commit", "git commit -q --allow-empty -m intrus")):
        print("\n%s — l'acteur demande le verrou pendant la transaction de A" % nom)
        injection = (
            'cd "$(git rev-parse --show-toplevel)" && '
            '%s -c "import sys;sys.path.insert(0,\'%s\');import git_guard,os,json;'
            'j=git_guard.acquerir(\'intrus\',\'%s\',None,depot=os.getcwd());'
            'open(\'state/INTRUS\',\'w\').write(\'GAGNE\' if j else \'REFUSE\');'
            '(%s) if j else None"'
            % (sys.executable, os.path.join(BRAIN, "hooks"), op, "None"))
        d = depot(hook=injection)
        try:
            open(os.path.join(d, "lessons", "mienne.md"), "w").write("x\n")
            avant = head(d)
            n = CPZ.commit_par_zone(d, "test: ")
            verdict = open(os.path.join(d, "state", "INTRUS")).read() \
                if os.path.exists(os.path.join(d, "state", "INTRUS")) else "ABSENT"
            ok("l'intrus a été REFUSÉ pendant la transaction") if verdict == "REFUSE" \
                else ko("l'intrus a obtenu le verrou (%s) — exclusion mutuelle percée" % verdict)
            f = fichiers_du_commit(d)
            if n == 1 and f == ["lessons/mienne.md"] and head(d) != avant:
                ok("aucune perte d'opération : A a commité son plan, %s" % f)
            else:
                ko("A a perdu son opération : %d commit(s), contenu %s" % (n, f))
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ── 5. deux zones séquentielles légitimes ───────────────────────────────────
def cas_5():
    print("\n5. DEUX ZONES SÉQUENTIELLES — comportement nominal conservé")
    d = depot()
    try:
        open(os.path.join(d, "lessons", "savoir.md"), "w").write("x\n")
        open(os.path.join(d, "hooks", "moteur.py"), "w").write("y\n")
        n = CPZ.commit_par_zone(d, "test: ")
        c1 = fichiers_du_commit(d, "HEAD")
        c2 = fichiers_du_commit(d, "HEAD~1")
        if n == 2 and {tuple(c1), tuple(c2)} == {("hooks/moteur.py",), ("lessons/savoir.md",)}:
            ok("2 commits, une zone chacun : %s puis %s" % (c2, c1))
        else:
            ko("attendu 2 commits séparés par zone, obtenu %d : %s / %s" % (n, c2, c1))
        pris = [e for e in journal(d) if e["evenement"] == "acquis"]
        if len(pris) == 2 and {e.get("zone") for e in pris} == {"savoir", "moteur"}:
            ok("une transaction PAR ZONE dans le journal : %s"
               % sorted(e["zone"] for e in pris))
        else:
            ko("le journal ne montre pas une transaction par zone : %s"
               % [e.get("zone") for e in pris])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 6. git_guard indisponible → REFUS, jamais de repli ──────────────────────
def cas_6():
    print("\n6. git_guard INDISPONIBLE — refus propre, aucun repli vers git direct")
    d = depot()
    faux = tempfile.mkdtemp(prefix="sans-guard-")
    try:
        # un dossier qui contient commit_par_zone.py mais PAS git_guard.py
        shutil.copy(os.path.join(BRAIN, "hooks", "commit_par_zone.py"), faux)
        open(os.path.join(d, "lessons", "neuve.md"), "w").write("x\n")
        avant = head(d)
        r = subprocess.run([sys.executable, os.path.join(faux, "commit_par_zone.py")],
                           cwd=d, capture_output=True, text=True,
                           env=dict(os.environ, BRAIN_HOME=d, PYTHONPATH=faux))
        sortie = r.stdout + r.stderr
        if "git_guard indisponible" in sortie:
            ok("refus EXPLICITE et nommé")
        else:
            ko("aucun refus explicite — sortie : %s" % sortie.strip()[:150])
        if head(d) == avant:
            ok("AUCUN commit posé — pas de repli vers git direct")
        else:
            ko("REPLI : un commit a été posé sans la primitive (%s)" % fichiers_du_commit(d))
        if index(d) == []:
            ok("l'index n'a pas été touché non plus")
        else:
            ko("l'index a été muté malgré l'absence de garde : %s" % index(d))
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(faux, ignore_errors=True)


# ── 7. le journal attribue ──────────────────────────────────────────────────
def cas_7():
    print("\n7. JOURNAL — la transaction est attribuable et certifie son résultat")
    d = depot()
    try:
        open(os.path.join(d, "lessons", "neuve.md"), "w").write("x\n")
        CPZ.commit_par_zone(d, "test: ")
        j = journal(d)
        a = next((e for e in j if e["evenement"] == "acquis"), {})
        l = next((e for e in j if e["evenement"] == "libere"), {})
        manque = [c for c in ("acteur", "pid", "operation", "perimetre", "head_avant",
                              "zone", "origine") if c not in a]
        if manque:
            ko("champs absents de l'acquisition : %s" % manque)
        else:
            ok("acquisition attribuée : acteur=%s zone=%s pid=%s origine=%s"
               % (a["acteur"], a["zone"], a["pid"], str(a["origine"])[:28]))
        if l.get("fichiers_commites") == ["lessons/neuve.md"] and l.get("head_a_bouge"):
            ok("libération CERTIFIE le résultat réel : %s, HEAD %s → %s"
               % (l["fichiers_commites"], l["head_avant"][:7], l["head_apres"][:7]))
        else:
            ko("la libération ne certifie pas le résultat : %s" % l.get("fichiers_commites"))
        if l.get("hors_perimetre") == []:
            ok("aucun fichier hors du périmètre demandé")
        else:
            ko("fichiers hors périmètre : %s" % l.get("hors_perimetre"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print("=" * 78)
    print("commit_par_zone SOUS GARDE — le producteur réel, dépôts jetables")
    print("=" * 78)
    for f in (cas_1, cas_2, cas_3_4, cas_5, cas_6, cas_7):
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
    print("VERT — commit_par_zone est gouverné par git_guard dans les conditions testées.")
    print("  Portée : dépôts jetables, un hôte. Les autres producteurs — sync_depots,")
    print("  brain push, auto_maintain — restent HORS primitive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
