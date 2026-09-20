#!/usr/bin/env python3
"""i1_obeissance — la conformité I-1 se MESURE, elle ne se lit pas.

POURQUOI CE BANC EXISTE (2026-08-21)
    La classification I-1 était faite par motifs lexicaux. Elle a produit un faux
    positif coûteux : `hooks/resume_pending.py` a été déclaré non conforme parce qu'il
    contient `sys.path.insert(0, dirname(__file__))` — alors que cette ligne désigne une
    RACINE DE CODE parfaitement légitime, et que toutes ses opérations Brain passent par
    `am.BRAIN`, qui honore `BRAIN_HOME`. Sur la foi de ce faux positif, une pose launchd
    a été laissée volontairement non ancrée pendant une journée, avec une « dette I-1 »
    inscrite dans un registre. La dette n'existait pas.

L'INVARIANT MÉTHODOLOGIQUE QUI EN SORT
    RACINE DE CODE ≠ RACINE DE BRAIN.
    Un outil statique produit des CANDIDATS. Il n'attribue jamais seul la conformité.

CE QUE MESURE CE BANC
    Quatre lieux distinguables, dans un seul sous-processus par module :
        CODE = A   (le dépôt d'où le fichier est chargé)
        BRAIN_HOME = B
        HOME = C
        cwd = D
    Puis on lit TOUS les chemins absolus que le module expose, et on regarde où ils
    tombent. Le classement dépend de la ZONE visée, pas de la forme du code :
      · zones de DONNÉES (state, lessons, projects, sessions, meta, life, agents,
        MEMORY.md, config) → doivent tomber dans B ;
      · zones de CODE (hooks, tools, tests, companion, capsule, mcp) → peuvent
        légitimement rester dans A ;
      · le foyer (Bureau, coffres, sauvegardes) → peut légitimement rester dans C.

VERDICTS
    I1-OK      au moins une donnée Brain vue, et toutes dans B.
    I1-FAIL    au moins une donnée Brain reste dans A, C ou D.
    I1-N/A     le module n'expose aucune donnée Brain : il n'a pas de racine Brain.
    I1-INCONNU le module n'a pas pu être chargé proprement.

Usage :  i1_obeissance.py [--check] [module…]     (sans argument : tout l'inventaire)
"""
import json, os, subprocess, sys, tempfile

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME")
                         or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

ZONES_DONNEES = ("state", "lessons", "projects", "sessions", "meta", "life", "agents",
                 "audits", "vision", "config")
FICHIERS_DONNEES = ("MEMORY.md",)

SONDE = r'''
import sys, os, io, contextlib, importlib.util, json
chemin = sys.argv[1]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(chemin)), "hooks"))
sys.path.insert(0, os.path.dirname(chemin))
spec = importlib.util.spec_from_file_location("sonde_i1", chemin)
m = importlib.util.module_from_spec(spec); sys.modules["sonde_i1"] = m
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        spec.loader.exec_module(m)
except BaseException as e:
    print(json.dumps({"erreur": type(e).__name__})); raise SystemExit(0)
vus = []
for nom in dir(m):
    if nom.startswith("__"): continue
    try: v = getattr(m, nom)
    except Exception: continue
    if isinstance(v, (str, os.PathLike)):
        s = str(v)
        if s.startswith("/"): vus.append(s)
print(json.dumps({"chemins": vus}))
'''


def est_donnee(chemin):
    """Ce chemin désigne-t-il une DONNÉE du Brain, où qu'il pointe ?

    On regarde les SEGMENTS, pas le préfixe. Première version : on testait
    `chemin.startswith(racine)` puis la tête du reste — et la sonde de calibration
    « littéral non redirigeable » est passée pour I1-N/A, donc l'instrument ne voyait
    pas le défaut qu'il devait voir. La raison : sous `HOME=C`, `expanduser("~/.c-brain/trunk")`
    donne `C/claude-brain/state/…`, dont la tête après C est `claude-brain`, pas `state`.
    Un banc qui ne rougit pas sur son propre sabotage ne mesure rien."""
    # Le foyer de Claude Code n'est PAS le Brain. `~/.claude/projects/` héberge les
    # transcripts, `~/.claude/companion/` l'état du compagnon : leurs segments
    # `projects` et `sessions` sont homonymes de zones du Brain, et la première version
    # de ce test a classé 4 modules I1-FAIL pour cette seule raison — archive_session,
    # auto_maintain, brain_audit, companion_lib. Quatre fausses accusations sur dix :
    # exactement la faute que ce banc existe pour ne plus commettre.
    if "/.claude/" in chemin:
        return False
    segments = chemin.strip("/").split("/")
    return any(s in ZONES_DONNEES for s in segments) or os.path.basename(chemin) in FICHIERS_DONNEES


def sous(chemin, racine):
    return chemin.startswith(racine.rstrip("/") + "/")


def mesurer(module, A, B, C, D):
    """Un sous-processus, quatre lieux distincts. Rend (verdict, preuves)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(SONDE); sonde = f.name
    try:
        env = dict(os.environ, BRAIN_HOME=B, HOME=C)
        env.pop("CLAUDE_SETTINGS", None)
        r = subprocess.run([sys.executable, sonde, os.path.join(A, module)],
                           capture_output=True, text=True, cwd=D, env=env, timeout=60)
    except subprocess.TimeoutExpired:
        return "I1-INCONNU", ["expiration"]
    finally:
        os.unlink(sonde)
    ligne = (r.stdout or "").strip().splitlines()
    if not ligne:
        return "I1-INCONNU", [(r.stderr or "")[:60]]
    try:
        d = json.loads(ligne[-1])
    except json.JSONDecodeError:
        return "I1-INCONNU", [ligne[-1][:60]]
    if "erreur" in d:
        return "I1-INCONNU", [d["erreur"]]

    donnees = [c for c in d["chemins"] if est_donnee(c)]
    dans_B = [c for c in donnees if sous(c, B)]
    egares = [c for c in donnees if not sous(c, B)]
    if egares:
        return "I1-FAIL", egares[:3]
    if dans_B:
        return "I1-OK", dans_B[:2]
    return "I1-N/A", []


def inventaire():
    """Modules exécutables du Brain susceptibles de toucher aux données."""
    out = []
    for d in ("hooks", "tools", "companion/hooks", "tools/cartes"):
        rep = os.path.join(BRAIN, d)
        if not os.path.isdir(rep): continue
        for f in sorted(os.listdir(rep)):
            if f.endswith(".py") and not f.startswith("_"):
                out.append(os.path.join(d, f))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    modules = args or inventaire()
    A = BRAIN
    base = tempfile.mkdtemp(prefix="i1-")
    B = os.path.realpath(os.path.join(base, "brainB"))
    C = os.path.realpath(os.path.join(base, "foyerC"))
    D = os.path.realpath(os.path.join(base, "cwdD"))
    for p in (B, C, D):
        os.makedirs(p, exist_ok=True)
    for z in ZONES_DONNEES:
        os.makedirs(os.path.join(B, z), exist_ok=True)

    compte = {}
    fails = []
    for m in modules:
        v, preuves = mesurer(m, A, B, C, D)
        compte[v] = compte.get(v, 0) + 1
        if v == "I1-FAIL":
            fails.append((m, preuves))
        if "--check" not in sys.argv or v == "I1-FAIL":
            marque = {"I1-OK": "✅", "I1-FAIL": "🔴", "I1-N/A": "·", "I1-INCONNU": "⬛"}[v]
            detail = ""
            if v == "I1-FAIL":
                detail = "  ← " + ", ".join(p.replace(A, "<CODE>").replace(C, "<FOYER>")
                                            for p in preuves)
            print(f"  {marque} {v:11s} {m}{detail}")

    print("\n  " + " · ".join(f"{k} : {v}" for k, v in sorted(compte.items())))
    if fails:
        print(f"\n  {len(fails)} module(s) attachent une donnée Brain à autre chose que BRAIN_HOME.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
