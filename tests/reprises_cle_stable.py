#!/usr/bin/env python3
"""reprises_cle_stable.py — les reprises décrivent l'état VERSIONNÉ, pas le disque.

CE QUI EST EN JEU. `brain_anticipate.collect()` classait par `mtime`. C'est une
propriété du système de fichiers, pas de la connaissance : `git clone`,
`checkout`, `stash pop` et `rsync` la réécrivent en bloc. MESURÉ le 2026-08-20 :
sur un clone frais, les 60 candidats partagent UN SEUL mtime — le top-4 devenait
un départage arbitraire, et deux copies du même HEAD proposaient des reprises
différentes.

Conséquence en cascade : le badge ↻ de la planète est un INSTANTANÉ
(`planet/graph.json`), les reprises du démarrage sont un RECALCUL. Deux lectures
d'une grandeur instable à deux instants ne peuvent pas concorder, et l'invariant
qui les compare était rouge sans qu'aucune connaissance ait changé.

LA CLÉ EST DONC LA DATE DU DERNIER COMMIT, départagée par le chemin — départage
DÉCLARÉ AVANT LA MESURE, jamais choisi après avoir vu quel top-4 il arrangeait.

CE QUE CE BANC NE PROUVE PAS. Que `%ct` survit à une réécriture d'historique :
un rebase le réécrit et peut réordonner. `%at` y survivrait mais ne répond pas à
la même question. Limite déclarée, pas mesurée.

Run: python3 tests/reprises_cle_stable.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
TOP = 4
fails = []


def ok(l):
    print("  OK   %s" % l)


def ko(l, d=""):
    print("  FAIL %s%s" % (l, ("  -- " + d) if d else ""))
    fails.append(l)


def note(l):
    print("  ..   %s" % l)


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def clone(dest):
    r = sh("git", "clone", "-q", "--no-hardlinks", ROOT, dest)
    assert r.returncode == 0, r.stderr
    return dest


def top(racine):
    """Le top-4 tel que l'instrument RÉEL le calcule dans cette copie."""
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import brain_anticipate as ba
        print(json.dumps([i["path"] for i in ba.collect()[:%d]]))
    """) % (HOOKS, TOP)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, BRAIN_HOME=racine))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def top_mtime(racine):
    """Le classement de l'ANCIENNE clé, pour montrer ce qu'elle faisait."""
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import brain_anticipate as ba
        items = ba.collect()
        items.sort(key=lambda x: x["mtime"], reverse=True)
        print(json.dumps([i["path"] for i in items[:%d]]))
    """) % (HOOKS, TOP)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, BRAIN_HOME=racine))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def commit(racine, message="test"):
    sh("git", "-C", racine, "add", "-A")
    sh("git", "-C", racine, "-c", "user.email=t@t", "-c", "user.name=t",
       "commit", "-qm", message)
    return sh("git", "-C", racine, "rev-parse", "HEAD").stdout.strip()


def graphe(racine):
    with open(os.path.join(racine, "planet", "graph.json"), encoding="utf-8") as f:
        return json.load(f)


def regenerer(racine):
    return subprocess.run([sys.executable, os.path.join(HOOKS, "graph_export.py")],
                          capture_output=True, text=True,
                          env=dict(os.environ, BRAIN_HOME=racine))


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="reprises."))
    try:
        print("== reprises : classement par date de commit, pas par mtime ==")

        A, B = clone(os.path.join(tmp, "A")), clone(os.path.join(tmp, "B"))
        # planet/graph.json n'est pas versionné : un clone n'en a pas. On le génère
        # une fois, ce qui est exactement ce que fait une première installation.
        regenerer(A)

        print("\n> 1. deux copies du même HEAD, mtimes différents")
        t = time.time()
        cibles = [os.path.join(dp, f)
                  for dp, _, fs in os.walk(os.path.join(B, "projects"))
                  for f in fs if f.endswith(".md")][:25]
        for n, p in enumerate(cibles):
            os.utime(p, (t - n, t - n))
        if sh("git", "-C", B, "status", "--porcelain").stdout.strip():
            ko("le brouillage a modifié le contenu — la mesure ne vaudrait rien")
        elif top_mtime(A) == top_mtime(B):
            note("mtime rend le même top-4 ici : le brouillage n'a pas mordu")
        else:
            note("pour mémoire, l'ancienne clé divergeait : %s ≠ %s"
                 % (top_mtime(A)[0][:40], top_mtime(B)[0][:40]))
        if top(A) == top(B):
            ok("même top-4 dans les deux copies")
        else:
            ko("deux copies du même HEAD proposent des reprises différentes",
               "%s vs %s" % (top(A), top(B)))

        print("\n> 2. maintenance à contenu identique, sans commit")
        avant = top(A)
        for p in [os.path.join(dp, f)
                  for dp, _, fs in os.walk(os.path.join(A, "projects"))
                  for f in fs if f.endswith(".md")][:25]:
            data = open(p, "rb").read()
            open(p, "wb").write(data)          # réécriture à l'identique
            os.utime(p, (time.time(), time.time()))
        if sh("git", "-C", A, "status", "--porcelain").stdout.strip():
            ko("la maintenance a sali l'arbre git")
        elif top(A) == avant:
            ok("top-4 inchangé après une maintenance qui ne change rien")
        else:
            ko("une maintenance sans changement a bougé les reprises")
        regenerer(A)
        if sorted(n["file"] for n in graphe(A)["nodes"] if n.get("resume")) == sorted(top(A)):
            ok("  et le badge régénéré dit la même chose que collect()")
        else:
            ko("  badge et collect() divergent sur le même HEAD")

        print("\n> 3. un VRAI commit sur une candidate change le classement")
        hors = [p for p in top_mtime(A) if p not in top(A)]
        cible = hors[0] if hors else [p for p in top(A)][-1]
        with open(os.path.join(A, cible), "a") as f:
            f.write("\n<!-- vrai changement -->\n")
        nouveau_head = commit(A, "un vrai commit sur une candidate")
        if top(A) and top(A)[0] == cible:
            ok("la fiche commitée prend le rang 0 : la clé n'est pas inerte")
        else:
            ko("un vrai commit ne change rien au classement", "%s" % top(A)[:1])

        print("\n> 4. après ce commit, AVANT régénération, le graphe est périmé")
        g = graphe(A)
        if g.get("head") and g["head"] != nouveau_head:
            ok("graph.json déclare un autre HEAD (%s ≠ %s) : périmé, et il le dit"
               % (g["head"][:12], nouveau_head[:12]))
        else:
            ko("rien ne permet de voir que l'instantané est périmé",
               "head du graphe : %s" % g.get("head"))

        print("\n> 5. après régénération, badge == collect()")
        r = regenerer(A)
        g = graphe(A)
        badge = sorted(n["file"] for n in g["nodes"] if n.get("resume"))
        if g.get("head") == nouveau_head and badge == sorted(top(A)):
            ok("le graphe décrit le nouveau HEAD et le badge concorde")
        else:
            ko("après régénération, badge et reprises ne concordent toujours pas",
               "head=%s badge=%s top=%s" % (str(g.get('head'))[:12], badge, sorted(top(A))))

        print("\n> 6. deux exports successifs du même HEAD sont identiques")
        C, D = clone(os.path.join(tmp, "C")), clone(os.path.join(tmp, "D"))
        if top(C) == top(D):
            ok("deux clones frais : même top-4")
        else:
            ko("deux clones frais divergent", "%s vs %s" % (top(C), top(D)))

        # LES CAS 7 ET 8 ONT DÉMÉNAGÉ (2026-08-20, chantier B5) vers
        # tests/graphe_apres_commit.py : ils portaient sur QUI déclenche la
        # régénération, et ce déclencheur n'est plus `commit_par_zone` mais le
        # hook `post-commit` du dépôt. Ce banc-ci garde ce qui lui appartient :
        # la CLÉ de classement et la cohérence badge/collect() sur un même HEAD.

        print("\n" + "-" * 74)
        if fails:
            print("ROUGE — %d échec(s)" % len(fails))
            for f in fails:
                print("   . %s" % f)
            return 1
        print("VERT — les reprises suivent le HEAD, et le badge dit quel HEAD il décrit.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
