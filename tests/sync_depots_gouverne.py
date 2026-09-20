#!/usr/bin/env python3
"""
sync_depots_gouverne.py — la publication gouvernée, éprouvée sur distants jetables.
ADR-0017 phase 4.

CE QUI EST TESTÉ : `tools/sync_depots.py` lui-même — sa fonction `publier()` et son mode
`--auto` — jamais une imitation.

L'OBSERVABLE EST TOUJOURS LA REF RÉELLEMENT SERVIE (`git ls-remote`). Jamais un code de
retour, jamais une ligne de log. C'est la leçon du 2026-08-25 : un push dont on lit le
code n'est pas un push dont on a vu le résultat.

  python3 tests/sync_depots_gouverne.py
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
sys.path.insert(0, os.path.join(BRAIN, "tools"))
import git_guard  # noqa: E402

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)


def g(args, cwd, **kw):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, **kw)


def servie(depot, branche="main"):
    """La ref RÉELLEMENT servie par le distant. La seule source de vérité de ce banc."""
    out = g(["ls-remote", "origin", branche], depot).stdout.split()
    return out[0] if out else None


def scene(n_commits=2):
    """Dépôt jetable + distant jetable, avec n commits locaux non poussés."""
    base = tempfile.mkdtemp(prefix="sdg-")
    if not os.path.realpath(base).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")
    g(["init", "-q", "--bare", os.path.join(base, "remote.git")], base)
    d = os.path.join(base, "brain")
    os.makedirs(os.path.join(d, "state"))
    for z in ("lessons", "hooks", "tools"):
        os.makedirs(os.path.join(d, z))
    # LA SCÈNE DOIT PORTER LE MOTEUR. Sans ces deux fichiers, sync_depots plante à
    # l'import et le banc affiche « ref distante inchangée » — un VERT obtenu parce que
    # le script est mort, pas parce que le confinement a tenu. C'est arrivé au premier
    # essai : trois cas verts, sortie vide. Un banc doit échouer bruyamment, pas
    # silencieusement réussir.
    for f in ("commit_par_zone.py", "git_guard.py"):
        shutil.copy(os.path.join(BRAIN, "hooks", f), os.path.join(d, "hooks", f))
    open(os.path.join(d, ".gitignore"), "w").write("state/\n")
    g(["init", "-q", "--initial-branch=main", "."], d)
    for c, v in (("user.name", "S"), ("user.email", "s@l"), ("commit.gpgsign", "false")):
        g(["config", c, v], d)
    open(os.path.join(d, "lessons", "base.md"), "w").write("base\n")
    g(["add", "-A"], d); g(["commit", "-q", "-m", "C0"], d)
    g(["remote", "add", "origin", os.path.join(base, "remote.git")], d)
    g(["push", "-q", "origin", "main"], d)
    for i in range(n_commits):
        open(os.path.join(d, "lessons", "c%d.md" % i), "w").write("x\n")
        g(["add", "-A"], d); g(["commit", "-q", "-m", "local %d" % i], d)
    return base, d


def lancer(d, *args):
    """Le VRAI sync_depots, dans un HOME jetable pour que ~/c-brain n'existe pas.

    Le garde ci-dessous existe parce qu'il a servi : une sortie vide signifie que le
    script est mort avant d'agir, et un banc qui lit « rien ne s'est passé » comme
    « le garde-fou a tenu » se ment."""
    r = subprocess.run([sys.executable, os.path.join(BRAIN, "tools", "sync_depots.py")] + list(args),
                       cwd=d, capture_output=True, text=True,
                       env=dict(os.environ, HOME=os.path.dirname(d), BRAIN_HOME=d))
    if not r.stdout.strip():
        ko("sync_depots n'a RIEN produit — il n'a pas tourné : %s"
           % (r.stderr.strip()[-160:] or "aucune erreur"))
    return r


def journal(d):
    try:
        return [json.loads(l) for l in
                open(os.path.join(d, "state", "git-journal.jsonl"), encoding="utf-8")]
    except Exception:
        return []


# ── 1. --auto ne publie pas ─────────────────────────────────────────────────
def cas_1():
    print("\n1. --auto AVEC des commits en attente → aucune publication")
    base, d = scene(2)
    try:
        avant, head = servie(d), g(["rev-parse", "HEAD"], d).stdout.strip()
        lancer(d, "--auto")
        apres = servie(d)
        ok("ref distante INCHANGÉE : %s" % avant[:7]) if apres == avant else \
            ko("origin/main a avancé %s → %s SANS humain" % (avant[:7], apres[:7]))
        ok("HEAD local intact, %d commit(s) d'avance"
           % int(g(["rev-list", "--count", "origin/main..HEAD"], d).stdout or 0)) \
            if g(["rev-parse", "HEAD"], d).stdout.strip() == head else ko("HEAD local a bougé")
        p = os.path.join(d, "state", "lot-a-publier.json")
        if os.path.exists(p):
            sig = json.load(open(p))
            if sig["head"] == head and sig["commits_en_attente"] == 2:
                ok("signal cohérent : head=%s, %d en attente" % (sig["head"][:7],
                                                                sig["commits_en_attente"]))
            else:
                ko("signal incohérent : %s" % sig)
        else:
            ko("aucun signal écrit")
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── 2. appel humain → publication sous verrou ───────────────────────────────
def cas_2():
    print("\n2. APPEL HUMAIN, fast-forward possible → publication sous git_guard")
    base, d = scene(2)
    try:
        avant, head = servie(d), g(["rev-parse", "HEAD"], d).stdout.strip()
        lancer(d)
        apres = servie(d)
        if apres == head:
            ok("ref distante RELUE = HEAD publié : %s → %s" % (avant[:7], apres[:7]))
        else:
            ko("ref servie %s ≠ HEAD %s" % (str(apres)[:7], head[:7]))
        ev = [e["evenement"] for e in journal(d)]
        ok("transaction tracée (%s)" % " → ".join(ev[-2:])) if "acquis" in ev and "libere" in ev \
            else ko("aucune transaction au journal : %s" % ev)
        ok("verrou libéré") if git_guard.diagnostic(d)["etat"] == "libre" \
            else ko("verrou resté pris")
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── 3. un autre acteur détient le verrou ────────────────────────────────────
def cas_3():
    print("\n3. VERROU TENU par un autre acteur → refus, aucun repli")
    base, d = scene(2)
    dormeur = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(45)"])
    try:
        import time; time.sleep(0.3)
        json.dump({"acteur": "autre-acteur", "pid": dormeur.pid,
                   "demarrage": git_guard._demarrage(dormeur.pid), "operation": "commit",
                   "perimetre": None, "ts": time.time(), "head_avant": "x"},
                  open(os.path.join(d, "state", "git.lock"), "w"))
        avant = servie(d)
        r = lancer(d)                       # appel HUMAIN, donc autorisé à publier
        if servie(d) == avant:
            ok("ref distante inchangée — rien n'a été poussé malgré l'autorisation")
        else:
            ko("PUBLIÉ malgré le verrou d'un tiers")
        if "verrou tenu par" in r.stdout:
            ok("refus explicite, nommant le détenteur")
        else:
            ko("aucun refus explicite : %s" % r.stdout.strip()[-140:])
    finally:
        dormeur.kill(); dormeur.wait()
        shutil.rmtree(base, ignore_errors=True)


# ── 4. le distant a bougé → refus, aucun écrasement ─────────────────────────
def cas_4():
    print("\n4. LE DISTANT A BOUGÉ entre-temps → refus, aucun écrasement")
    base, d = scene(2)
    try:
        # un tiers publie sa propre histoire sur le distant
        autre = os.path.join(base, "autre")
        g(["clone", "-q", os.path.join(base, "remote.git"), autre], base)
        for c, v in (("user.name", "T"), ("user.email", "t@l")):
            g(["config", c, v], autre)
        open(os.path.join(autre, "du-tiers.md"), "w").write("tiers\n")
        g(["add", "-A"], autre); g(["commit", "-q", "-m", "commit du tiers"], autre)
        g(["push", "-q", "origin", "main"], autre)
        divergent = servie(d)
        r = lancer(d)
        apres = servie(d)
        if apres == divergent:
            ok("ref distante INTACTE : %s — le commit du tiers survit" % apres[:7])
        else:
            ko("ÉCRASEMENT : %s → %s" % (divergent[:7], str(apres)[:7]))
        if "pas un ancêtre" in r.stdout or "REFUS" in r.stdout:
            ok("refus explicite, motif fast-forward nommé")
        else:
            ko("pas de refus lisible : %s" % r.stdout.strip()[-140:])
        if "--force" not in r.stdout:
            ok("aucun --force proposé ni employé")
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── 5. le push échoue → pas de faux succès ──────────────────────────────────
def cas_5():
    print("\n5. LE PUSH ÉCHOUE (distant qui refuse) → état inspectable, pas de faux succès")
    base, d = scene(2)
    try:
        h = os.path.join(base, "remote.git", "hooks", "pre-receive")
        open(h, "w").write("#!/bin/sh\necho 'refus du serveur' >&2\nexit 1\n")
        os.chmod(h, 0o755)
        avant, head = servie(d), g(["rev-parse", "HEAD"], d).stdout.strip()
        r = lancer(d)
        if servie(d) == avant:
            ok("ref distante inchangée : %s" % avant[:7])
        else:
            ko("la ref a bougé alors que le serveur refusait")
        if "✅" not in r.stdout.split("push :")[-1][:20]:
            ok("aucun faux succès annoncé")
        else:
            ko("FAUX SUCCÈS : « push : ✅ » alors que rien n'est publié")
        if "ÉCHEC" in r.stdout:
            ok("échec nommé, avec la ref attendue vs servie")
        else:
            ko("l'échec n'est pas explicite : %s" % r.stdout.strip()[-140:])
        if g(["rev-parse", "HEAD"], d).stdout.strip() == head:
            ok("état local inspectable et intact (HEAD %s)" % head[:7])
        else:
            ko("l'état local a été altéré par l'échec")
        if git_guard.diagnostic(d)["etat"] == "libre":
            ok("verrou libéré malgré l'échec")
        else:
            ko("verrou orphelin après échec")
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── 6. le journal ───────────────────────────────────────────────────────────
def cas_6():
    print("\n6. JOURNAL — acteur, refs avant/après, résultat réel")
    base, d = scene(1)
    try:
        head = g(["rev-parse", "HEAD"], d).stdout.strip()
        lancer(d)
        j = journal(d)
        a = next((e for e in j if e["evenement"] == "acquis" and "push" in str(e.get("operation"))), {})
        l = next((e for e in j if e["evenement"] == "libere" and "push" in str(e.get("operation"))), {})
        manque = [c for c in ("acteur", "pid", "operation", "head_avant", "branche") if c not in a]
        if manque:
            ko("champs absents : %s" % manque)
        else:
            ok("acteur=%s opération=%s branche=%s pid=%s"
               % (a["acteur"], a["operation"], a["branche"], a["pid"]))
        if l.get("head_apres") == head:
            ok("libération certifie HEAD après = %s (ref servie : %s)"
               % (l["head_apres"][:7], str(servie(d))[:7]))
        else:
            ko("la libération ne certifie pas le HEAD publié")
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── 7. git_guard absent → refus ─────────────────────────────────────────────
def cas_7():
    """⚠️ PREMIÈRE VERSION FAUSSE. Elle copiait sync_depots dans un dossier sans
    git_guard.py — mais la SCÈNE, elle, en contenait un dans `hooks/`, et le script le
    trouvait par `BRAIN_HOME/hooks`. Le banc affichait « REPLI : publié sans git_guard »
    alors que git_guard était bien là et faisait son travail. Pour mesurer une absence,
    il faut vraiment absenter la chose."""
    print("\n7. git_guard INDISPONIBLE → aucune publication, aucun repli")
    base, d = scene(2)
    try:
        os.remove(os.path.join(d, "hooks", "git_guard.py"))    # l'absence est RÉELLE
        avant = servie(d)
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "tools", "sync_depots.py")],
                           cwd=d, capture_output=True, text=True,
                           env=dict(os.environ, HOME=os.path.dirname(d), BRAIN_HOME=d,
                                    PYTHONPATH=os.path.join(d, "hooks")))
        sortie = r.stdout + r.stderr
        if servie(d) == avant:
            ok("aucune publication sans la primitive (ref %s inchangée)" % str(avant)[:7])
        else:
            ko("REPLI : publié sans git_guard")
        if "indisponible" in sortie:
            ok("refus explicite et nommé")
        else:
            ko("pas de refus nommé : %s" % sortie.strip()[-160:])
        if not os.path.exists(os.path.join(d, "state", "git.lock")):
            ok("aucun verrou laissé derrière")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print("=" * 78)
    print("sync_depots GOUVERNÉ — publication, dépôts ET distants jetables")
    print("=" * 78)
    for f in (cas_1, cas_2, cas_3, cas_4, cas_5, cas_6, cas_7):
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
    print("VERT — sync_depots est gouverné dans les conditions testées.")
    print("  brain push et les commandes git humaines restent HORS primitive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
