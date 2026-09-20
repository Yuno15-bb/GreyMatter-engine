#!/usr/bin/env python3
"""graphe_apres_commit.py — B5 : le badge suit le HEAD sans geste manuel.

CE QUI EST EN JEU. `planet/graph.json` déclare le HEAD qu'il décrit et
`invariants_brain` refuse un instantané périmé. Ce garde est juste et on ne le
desserre pas : autoriser le commit suivant reviendrait à accepter un instantané
faux. Ce qui se répare, c'est le CHEMIN qui maintient l'invariant.

Le déclenchement vit donc dans `tools/git-hooks/post-commit`, installé aussi
sous `post-merge` depuis UNE SEULE SOURCE, et il a été RETIRÉ de
`commit_par_zone` : deux producteurs pour la même opération auraient régénéré
deux fois par commit. `hooks/graph_export.py` reste la seule définition.

MESURÉ AVANT D'ÉCRIRE LA MOINDRE LIGNE (2026-08-20) : commit ordinaire,
`--amend` et chaque commit rejoué par un rebase déclenchent `post-commit` ; un
merge ne le déclenche pas — c'est `post-merge`. Aucun `--no-verify` dans le
dépôt, donc tous les écrivains passent par là. `planet/graph.json` est gitignoré,
donc régénérer ne peut jamais provoquer un commit : pas de récursion.

CE QUE CE BANC N'ÉTABLIT PAS : le comportement sur un `git checkout` d'une autre
branche, qui change le contenu sans passer par ces hooks. Limite déclarée.

Run: python3 tests/graphe_apres_commit.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def ok(l):
    print("  OK   %s" % l)


def ko(l, d=""):
    print("  FAIL %s%s" % (l, ("  -- " + d) if d else ""))
    fails.append(l)


def note(l):
    print("  ..   %s" % l)


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd] + list(a), capture_output=True, text=True)


def head(cwd):
    return git(cwd, "rev-parse", "HEAD").stdout.strip()


COMPTEUR = "COMPTEUR-EXPORT"
FAUX_EXPORT = '''#!/usr/bin/env python3
"""Faux graph_export : compte ses invocations ET écrit un graphe minimal juste.

Compter est le seul moyen de prouver « une seule régénération par commit » :
le vrai export ne laisse aucune trace du nombre de fois qu'il a tourné.
"""
import json, os, subprocess, sys
R = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
if os.environ.get("EXPORT_CASSE") == "1":
    sys.stderr.write("export casse volontairement\\n")
    sys.exit(1)
with open(os.path.join(R, "%s"), "a") as f:
    f.write("x\\n")
h = subprocess.run(["git", "-C", R, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
os.makedirs(os.path.join(R, "planet"), exist_ok=True)
json.dump({"head": h, "nodes": []}, open(os.path.join(R, "planet", "graph.json"), "w"))
''' % COMPTEUR


# TOUTES LES PORTES DE SORTIE DU PRE-COMMIT, sauf celle qu'un cas teste.
# Sans elles, un commit de fixture est refusé pour une raison qui n'a rien à voir
# avec B5 — et le cas croit mesurer le hook alors qu'il mesure un banc de
# provenance. Le premier passage de ce fichier est tombé exactement là.
PORTES = {"BRAIN_SKIP_BANCS": "1", "BRAIN_SKIP_INVARIANTS": "1",
          "BRAIN_SKIP_PROVENANCE": "1"}


def tronc(avec_hooks=True):
    """Un clone jetable, hooks posés par l'installateur RÉEL du dépôt.

    ⚠️ UN CLONE PREND HEAD, PAS LE TRAVAIL EN COURS. Le premier passage de ce
    banc a installé l'ANCIEN installateur — celui qui ne connaît qu'un hook — et
    a conclu que rien ne se régénérait. On recopie donc par-dessus le clone les
    fichiers que ce chantier modifie : un banc qui ne teste pas le code présent
    ne teste rien.
    """
    d = os.path.realpath(tempfile.mkdtemp(prefix="b5.")) + "/t"
    r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", ROOT, d],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for rel in ("tools/git-hooks/pre-commit", "tools/git-hooks/post-commit",
                "tools/git-hooks/installer.sh", "hooks/commit_par_zone.py"):
        shutil.copy(os.path.join(ROOT, rel), os.path.join(d, rel))
        os.chmod(os.path.join(d, rel), 0o755)
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    with open(os.path.join(d, "hooks", "graph_export.py"), "w") as f:
        f.write(FAUX_EXPORT)
    if avec_hooks:
        r = subprocess.run([os.path.join(d, "tools", "git-hooks", "installer.sh")],
                           capture_output=True, text=True, cwd=d)
        assert r.returncode == 0, r.stdout + r.stderr
        for nom in ("pre-commit", "post-commit", "post-merge"):
            assert os.path.exists(os.path.join(d, ".git", "hooks", nom)), \
                "hook %s non installé — la fixture ne teste rien" % nom
    git(d, "add", "-A")
    git(d, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "socle", "--no-verify")
    return d


def compteur(d):
    p = os.path.join(d, COMPTEUR)
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


def graphe(d):
    p = os.path.join(d, "planet", "graph.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def touche(d, nom, texte="x\n"):
    p = os.path.join(d, "projects", nom)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(texte)
    git(d, "add", "--", os.path.join("projects", nom))


def commit(d, msg, **env):
    e = dict(os.environ, BRAIN_HOME=d, **PORTES, **env)
    return subprocess.run(["git", "-C", d, "commit", "-qm", msg],
                          capture_output=True, text=True, env=e)


def main():
    print("== B5 — le graphe suit le HEAD, sans geste manuel ==")
    troncs = []
    try:
        print("\n> 1. un commit réussi met le graphe sur le NOUVEAU HEAD")
        d = tronc(); troncs.append(d)
        avant = compteur(d)
        touche(d, "b5-un.md")
        commit(d, "premier")
        if graphe(d).get("head") == head(d):
            ok("graph['head'] == HEAD (%s)" % head(d)[:12])
        else:
            ko("le graphe ne décrit pas le nouveau HEAD",
               "%s vs %s" % (str(graphe(d).get("head"))[:12], head(d)[:12]))
        if compteur(d) - avant == 1:
            ok("  et une seule régénération pour ce commit")
        else:
            ko("  %d régénération(s) pour un commit" % (compteur(d) - avant))

        print("\n> 2. un commit REFUSÉ ne régénère rien")
        avant, h_avant = compteur(d), head(d)
        touche(d, "b5-deux.md")
        # le pre-commit du dépôt refuse un commit qui mélange deux zones
        with open(os.path.join(d, "hooks", "zz-moteur.py"), "w") as f:
            f.write("# moteur\n")
        git(d, "add", "--", "hooks/zz-moteur.py")
        r = commit(d, "deux zones melangees")
        motif = "mélange" in (r.stdout + r.stderr) or "zones" in (r.stdout + r.stderr)
        if r.returncode != 0 and head(d) == h_avant and motif:
            ok("commit refusé POUR LE MÉLANGE DE ZONES, HEAD inchangé")
        else:
            ko("le refus n'est pas celui qu'on croit tester",
               (r.stdout + r.stderr).strip()[-160:])
        if compteur(d) == avant:
            ok("  aucune régénération")
        else:
            ko("  une régénération a eu lieu sans commit")
        git(d, "reset", "-q")

        print("\n> 3. deux commits manuels successifs : aucun périmé intermédiaire")
        touche(d, "b5-trois.md")
        git(d, "add", "--", "projects/b5-trois.md")
        r1 = commit(d, "manuel un")
        etat_apres_1 = graphe(d).get("head") == head(d)
        touche(d, "b5-quatre.md")
        git(d, "add", "--", "projects/b5-quatre.md")
        r2 = commit(d, "manuel deux")
        if r1.returncode == 0 and r2.returncode == 0:
            ok("les deux commits passent, sans geste entre les deux")
        else:
            ko("un commit enchaîné a été refusé",
               (r2.stdout + r2.stderr).strip()[-160:])
        if etat_apres_1:
            ok("  le graphe était déjà à jour au moment du second")
        else:
            ko("  un état périmé subsistait entre les deux commits")

        print("\n> 4. régénération en échec : périmé EXPLICITE, jamais faux vert")
        h_avant = head(d)
        touche(d, "b5-cinq.md")
        git(d, "add", "--", "projects/b5-cinq.md")
        r = commit(d, "export casse", EXPORT_CASSE="1")
        sortie = r.stdout + r.stderr
        if head(d) != h_avant:
            ok("le commit est bien posé (un hook post-* ne casse rien)")
        else:
            ko("le commit a été bloqué par un hook post-commit")
        if "PÉRIMÉ" in sortie or "périmé" in sortie:
            ok("  l'échec est ANNONCÉ, avec le mot périmé")
        else:
            ko("  une régénération ratée n'a rien dit", sortie.strip()[-200:])
        if graphe(d).get("head") == h_avant:
            ok("  et le graphe porte toujours l'ancien HEAD : identifiable comme périmé")
        else:
            ko("  le graphe prétend décrire le nouveau HEAD")

        print("\n> 5. `git commit --amend` : le HEAD change, le graphe suit")
        avant = compteur(d)
        subprocess.run(["git", "-C", d, "commit", "-q", "--amend", "-m", "amende"],
                       capture_output=True, text=True,
                       env=dict(os.environ, BRAIN_HOME=d, **PORTES))
        if graphe(d).get("head") == head(d):
            ok("après --amend, graph['head'] == HEAD")
        else:
            ko("le graphe reste sur le HEAD d'avant l'amend")
        if compteur(d) - avant == 1:
            ok("  une seule régénération")
        else:
            ko("  %d régénération(s) pour un amend" % (compteur(d) - avant))

        print("\n> 6. commit_par_zone : UNE régénération par commit, jamais deux")
        d2 = tronc(); troncs.append(d2)
        touche(d2, "b5-zone.md")
        git(d2, "reset", "-q")
        avant, h_avant = compteur(d2), head(d2)
        r = subprocess.run([sys.executable, os.path.join(d2, "hooks", "commit_par_zone.py")],
                           capture_output=True, text=True,
                           env=dict(os.environ, BRAIN_HOME=d2, **PORTES))
        poses = 0 if head(d2) == h_avant else len(
            git(d2, "log", "--oneline", "%s..HEAD" % h_avant).stdout.strip().splitlines())
        note("commit_par_zone a posé %d commit(s)" % poses)
        if poses and compteur(d2) - avant == poses:
            ok("%d régénération(s) pour %d commit(s) — une par commit, pas deux"
               % (compteur(d2) - avant, poses))
        elif not poses:
            ko("commit_par_zone n'a rien commité — le cas ne teste rien",
               (r.stdout + r.stderr).strip()[-160:])
        else:
            ko("%d régénération(s) pour %d commit(s)" % (compteur(d2) - avant, poses))
        if graphe(d2).get("head") == head(d2):
            ok("  et le graphe final décrit le HEAD final")
        else:
            ko("  le graphe ne décrit pas le HEAD final")

        print("\n> 7. hooks non installés : l'état est VISIBLE, pas silencieux")
        d3 = tronc(avec_hooks=False); troncs.append(d3)
        r = subprocess.run([os.path.join(d3, "tools", "git-hooks", "installer.sh"),
                            "--verifie"], capture_output=True, text=True, cwd=d3)
        if r.returncode != 0 and "post-commit" in r.stdout:
            ok("installer.sh --verifie nomme les hooks manquants (code %d)" % r.returncode)
        else:
            ko("un dépôt sans hooks passe pour nominal", r.stdout.strip()[:160])
        touche(d3, "b5-sans-hook.md")
        git(d3, "add", "--", "projects/b5-sans-hook.md")
        commit(d3, "sans hooks")
        if compteur(d3) == 0:
            ok("  sans hook, rien ne régénère — c'est bien le hook qui agit")
        else:
            ko("  quelque chose régénère en dehors du hook")

        print("\n> 8. contre-épreuve — une source de hook non installée n'agit pas")
        d4 = tronc(); troncs.append(d4)
        os.remove(os.path.join(d4, ".git", "hooks", "post-commit"))
        avant = compteur(d4)
        touche(d4, "b5-sabotage.md")
        git(d4, "add", "--", "projects/b5-sabotage.md")
        commit(d4, "post-commit retire")
        if compteur(d4) == avant:
            ok("post-commit retiré : plus aucune régénération — le banc mesure "
               "bien le hook, pas autre chose")
        else:
            ko("la régénération a lieu sans post-commit : ce banc ne prouve rien")

        print("\n" + "-" * 74)
        if fails:
            print("ROUGE — %d échec(s)" % len(fails))
            for f in fails:
                print("   . %s" % f)
            return 1
        print("VERT — un commit, une régénération, sur le HEAD qu'il vient de poser.")
        return 0
    finally:
        for d in troncs:
            shutil.rmtree(os.path.dirname(d), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
