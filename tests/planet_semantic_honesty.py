#!/usr/bin/env python3
"""planet_semantic_honesty.py — la carte n'a pas le droit d'annoncer un sens qu'elle n'a pas.

POURQUOI CE BANC EXISTE. La Planète S'OUVRE sur la vue sémantique : c'est le choix de l'auteur,
et il est bon — le globe dit dans quel dossier une fiche est rangée, le nuage du sens dit ce qui
se ressemble. Mais les embeddings qui placent ce nuage sont OPTIONNELS PAR DESSEIN
(docs/design-doc.md : « ni le corpus froid ni le venv d'embeddings : optionnels, BM25 suffit par
défaut »), et l'installeur ne pose ni venv ni pip. L'état ordinaire d'une installation neuve est
donc : aucun vecteur.

Mesuré le 2026-08-19 et remesuré À L'ÉCRAN le 2026-09-19, sous Chrome headless, sur le paquet
livré : 0 fiche sur 10 portait un vecteur, 0 sur 36 dans un tronc installé — et l'écran d'accueil
affichait « ✦ SENS EN VOLUME — proximité = sens, toutes les fiches ». Chaque point était à sa
place STRUCTURELLE, par un repli écrit pour « une fiche qui n'a pas encore de vecteur » et
appliqué là à 100 % d'entre elles. Aucune erreur, aucune ligne de journal : le recalcul était
appelé avec `|| true`.

CE QUI EST MESURÉ. Pas un code de sortie. Deux choses qu'un lecteur peut voir :
  1. l'exporteur CONSIGNE ce qu'il a mesuré — `graph.json` porte `semantic.state` / `covered`
     / `total`, comptés sur les FICHES et non sur la taille du cache (un cache de clés périmées
     ne place personne et ne doit pas se lire comme une santé parfaite) ;
  2. la phrase que l'afficheur va montrer, produite par `planet/semantic-label.js` et comparée
     ici comme une CHAÎNE, sous node — les quatre états se vérifient donc partout, y compris là
     où aucun navigateur n'est installé.

L'INVARIANT, au-dessus de tous les autres : les mots « SENS EN VOLUME » et « toutes les fiches »
n'ont le droit d'apparaître que lorsque toutes les fiches sont réellement posées par le sens.

Lancer :  python3 tests/planet_semantic_honesty.py
          python3 tests/planet_semantic_honesty.py --sabotage label-frozen-on-meaning
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SABOTAGES = ("label-frozen-on-meaning", "coverage-counted-on-the-cache", "old-graph-assumed-ready")

NOTE = """---
name: {name}
description: une fiche pour le banc d'honnêteté sémantique
metadata:
  type: lesson
---

Corps de {name}.
"""

ok = True


def verdict(cond, label, seen=""):
    global ok
    print(f"  {'✅' if cond else '❌'} {label}" + (f"   → {seen}" if not cond and seen else ""))
    if not cond:
        ok = False


def build_trunk(trunk, n_notes, cache):
    """cache : None = pas de fichier · "corrupt" = présent et illisible · dict = rel_path -> [x,y,z]"""
    for d in ("lessons", "planet", "state", "meta"):
        os.makedirs(os.path.join(trunk, d), exist_ok=True)
    for i in range(n_notes):
        with open(os.path.join(trunk, "lessons", f"note-{i}.md"), "w", encoding="utf-8") as f:
            f.write(NOTE.format(name=f"note-{i}"))
    path = os.path.join(trunk, "state", "embed2.json")
    if cache is None:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json at all" if cache == "corrupt" else json.dumps({"pos": cache}))


def export(src, trunk):
    out = subprocess.run([sys.executable, os.path.join(src, "hooks", "graph_export.py")],
                         capture_output=True, text=True,
                         env=dict(os.environ, BRAIN_HOME=trunk), timeout=180)
    if out.returncode != 0:
        raise SystemExit(f"l'exporteur a échoué :\n{out.stderr}")
    with open(os.path.join(trunk, "planet", "graph.json"), encoding="utf-8") as f:
        return json.load(f)


def label(src, payload):
    """La phrase que l'afficheur va montrer, lue dans le VRAI module, sous node."""
    js = ("import { capaciteSemantique, etiquetteSens, etiquette3d } from %s;"
          "const d = %s; const c = capaciteSemantique(d);"
          "console.log(JSON.stringify({cap:c, ...etiquetteSens(c), trois_d: etiquette3d(c, null)}));"
          % (json.dumps(os.path.join(src, "planet", "semantic-label.js")), json.dumps(payload)))
    out = subprocess.run(["node", "--input-type=module", "-e", js],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SystemExit(f"semantic-label.js n'a pas pu être lu par node :\n{out.stderr}")
    return json.loads(out.stdout)


def sabotage(src, name):
    """Casse un mécanisme sur la COPIE, exprès. Une substitution qui ne trouve rien est un banc
    qui certifie son propre rougissement : un motif absent arrête donc tout, ici et maintenant."""
    def patch(rel, old, new):
        p = os.path.join(src, rel)
        s = open(p, encoding="utf-8").read()
        if s.count(old) != 1:
            raise SystemExit(f"SABOTAGE {name} : motif trouvé {s.count(old)}× dans {rel}, attendu 1")
        open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))

    if name == "label-frozen-on-meaning":
        # Le défaut lui-même : la formulation nominale, quel que soit l'état.
        patch("planet/semantic-label.js",
              "    default:   // 'absent' et tout état inconnu",
              "    default:\n      return { titre: '[ CARTE DU TRONC — LE SENS ]',\n"
              "               bandeau: '✦ SENS EN VOLUME — proximité = sens, toutes les fiches · S structure' };\n"
              "    case '_never':   // SABOTAGE")
    elif name == "coverage-counted-on-the-cache":
        # Un cache périmé se lit comme une santé parfaite : compter ses clés, pas les fiches posées.
        patch("hooks/graph_export.py",
              'sem_covered = sum(1 for n in nodes.values() if n.get("embed2"))',
              'sem_covered = len(embed2)  # SABOTAGE')
    elif name == "old-graph-assumed-ready":
        # Un graph.json d'avant la déclaration est pris pour sain.
        patch("planet/semantic-label.js",
              "    state: couverts === 0 ? 'absent' : couverts === noeuds.length ? 'ready' : 'partial',",
              "    state: 'ready',  // SABOTAGE")
    else:
        raise SystemExit(f"sabotage inconnu : {name}\nconnus : {', '.join(SABOTAGES)}")


def main():
    saboteur = None
    if "--sabotage" in sys.argv:
        saboteur = sys.argv[sys.argv.index("--sabotage") + 1]

    lab = tempfile.mkdtemp(prefix="planet-semantic.")
    src = os.path.join(lab, "src")
    try:
        # Le banc travaille TOUJOURS sur une copie : un sabotage ne doit jamais pouvoir toucher le dépôt.
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                               capture_output=True, timeout=60).stdout.split(b"\0")
        for rel in (f.decode() for f in files if f):
            s, d = os.path.join(ROOT, rel), os.path.join(src, rel)
            if os.path.exists(s):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
        if saboteur:
            sabotage(src, saboteur)
            print(f"⚠️  sabotage actif : {saboteur}\n")

        print("Planète — la carte n'annonce pas un sens qu'elle n'a pas\n")

        # ── 1. les quatre états, mesurés par le VRAI exporteur ────────────────────────
        vec = [0.1, 0.2, 0.3]
        cases = [
            # nom           fiches cache                                     état       couvert
            ("aucun module",  4,   None,                                     "absent",  0),
            ("illisible",     4,   "corrupt",                                "broken",  0),
            ("cache périmé",  4,   {"lessons/gone.md": vec},                 "broken",  0),
            ("indexation",    4,   {f"lessons/note-{i}.md": vec for i in (0, 1)}, "partial", 2),
            ("toutes",        4,   {f"lessons/note-{i}.md": vec for i in range(4)}, "ready", 4),
        ]
        recorded = {}
        for label_, n, cache, want_state, want_cov in cases:
            trunk = tempfile.mkdtemp(prefix="trunk.", dir=lab)
            build_trunk(trunk, n, cache)
            g = export(src, trunk)
            sem = g.get("semantic", {})
            recorded[want_state if want_state != "broken" else label_] = sem
            verdict(sem.get("state") == want_state,
                    f"{label_:14} → état = {want_state}", f"état = {sem.get('state')!r}")
            verdict(sem.get("covered") == want_cov and sem.get("total") == n,
                    f"{label_:14} → {want_cov} fiche(s) sur {n} posée(s) par le sens",
                    f"covered={sem.get('covered')} total={sem.get('total')}")
            if want_state != "ready":
                verdict(bool(sem.get("detail")), f"{label_:14} → dit POURQUOI, en une phrase")

        print()
        # ── 2. la phrase que le lecteur verra, pour chacun de ces états ───────────────
        CLAIM = ("SENS EN VOLUME", "toutes les fiches")
        for state, sem in recorded.items():
            r = label(src, {"semantic": sem, "nodes": []})
            claims = any(c in r["bandeau"] for c in CLAIM)
            shown = f"{r['titre']} / {r['bandeau']}"
            if sem.get("state") == "ready":
                verdict(claims, "toutes         → le bandeau DIT bien que le sens est là", shown)
                verdict("S pour le sens" in r["trois_d"],
                        "toutes         → et le globe y invite", r["trois_d"])
            elif sem.get("state") == "partial":
                # PARTIEL N'EST PAS « PAS DE SENS » : des fiches y sont vraiment posées. Le titre
                # a le droit de dire le mot — jamais nu, toujours avec le compte qui le borne.
                verdict(not claims, f"{state:14} → le bandeau ne prétend PAS toutes les fiches", shown)
                verdict("— LE SENS ]" not in r["titre"] and "/" in r["titre"],
                        f"{state:14} → le titre ne dit le sens QU'avec son compte", r["titre"])
                verdict("S pour le sens" in r["trois_d"],
                        f"{state:14} → le globe a encore le droit d'y inviter", r["trois_d"])
            else:
                verdict(not claims, f"{state:14} → le bandeau n'annonce PAS le sens", shown)
                # ⚠️ « le titre ne contient pas SENS » a rougi sur « PAS ENCORE DE SENS » —
                # une DÉNÉGATION contient le mot qu'elle nie. On vise l'AFFIRMATION nue.
                verdict("— LE SENS ]" not in r["titre"],
                        f"{state:14} → le titre non plus", r["titre"])
                verdict("S pour le sens" not in r["trois_d"],
                        f"{state:14} → et le globe ne le promet pas non plus", r["trois_d"])
        # les chiffres doivent atteindre le lecteur, pas seulement le JSON
        mid = label(src, {"semantic": recorded["partial"], "nodes": []})
        verdict("2 fiches sur 4" in mid["bandeau"], "indexation     → le bandeau donne le compte",
                mid["bandeau"])

        print()
        # ── 3. un graph.json d'AVANT cette déclaration ────────────────────────────────
        old = label(src, {"nodes": [{"id": "a"}, {"id": "b"}]})
        verdict(old["cap"]["state"] == "absent",
                "vieux graph.json → déduit des fiches, pas supposé sain",
                json.dumps(old["cap"]))
        verdict(not any(c in old["bandeau"] for c in CLAIM),
                "vieux graph.json → le bandeau n'annonce pas le sens", old["bandeau"])
        old_ok = label(src, {"nodes": [{"id": "a", "embed2": vec}, {"id": "b", "embed2": vec}]})
        verdict(old_ok["cap"]["state"] == "ready",
                "vieux graph.json AVEC vecteurs → se lit toujours comme du sens", old_ok["bandeau"])

        print("\n" + ("✅ la carte dit ce qu'elle montre, dans les cinq états."
                      if ok else "❌ la carte annonce ce qu'elle ne peut pas montrer."))
        return 0 if ok else 1
    finally:
        shutil.rmtree(lab, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
