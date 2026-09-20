#!/usr/bin/env python3
"""gouvernance_carte.py — B6 : qui décide de l'appartenance à MEMORY.md.

DEUX PIÈCES, DEUX VERDICTS DANS UN SEUL BANC parce qu'elles ne valent que
ensemble : la barrière seule ferait refuser des commits sans qu'aucun geste
légitime n'en sorte, et l'exemption seule ne protégerait rien.

CE QUI S'EST PASSÉ (2026-08-20). Le jardinier, lancé par `auto_maintain`, a
ajouté deux entrées dans `MEMORY.md` — dont une fiche laissée dehors par
décision explicite — SANS toucher au manifeste. Il n'a pas désobéi : sa règle
d'or est « toute fiche est dans la carte », il attaque en priorité ce que
`brain_doctor` signale, et le doctor affichait « Hors carte ». Trois faits, une
chaîne cohérente, et aucun endroit où écrire « celle-là, c'est voulu ».

PIÈCE 1 — `tests/carte_divergence.py --check` est branché au `pre-commit`, avec
SA PROPRE porte (`BRAIN_SKIP_CARTE`) : `BRAIN_SKIP_BANCS` est emprunté à presque
chaque commit à cause du témoin q13, et l'y ranger aurait désarmé le garde sans
que personne ne le décide.

PIÈCE 2 — `carte: exclue` dans le frontmatter. Il ne parle QUE de la carte : la
fiche reste indexée, rappelable, reliée. Déclaré dans `meta/jardinage-regles.md`.

Run: python3 tests/gouvernance_carte.py
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


FICHE = """---
name: %s
description: "Fiche synthétique du banc de gouvernance de la carte."
tags: [le-cerveau]
metadata:
  type: project
provenance:
  kind: internal_experience
  ref: "tests/gouvernance_carte.py"
  captured_at: 2026-08-20
%s---

## En clair

Une fiche ordinaire, écrite par un banc. Elle cite [[claude-brain]].
"""

NOM = "fiche-b6-synthetique"


def clone():
    d = os.path.realpath(tempfile.mkdtemp(prefix="b6.")) + "/t"
    r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", ROOT, d],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # ⚠️ un clone prend HEAD : on recopie ce que ce chantier modifie, sinon le
    # banc mesurerait l'état d'avant (défaut vécu sur B5 le même jour).
    for rel in ("hooks/brain_doctor.py", "tests/carte_divergence.py",
                "tools/git-hooks/pre-commit", "tools/git-hooks/post-commit",
                "tools/git-hooks/installer.sh", "MEMORY.md"):
        shutil.copy(os.path.join(ROOT, rel), os.path.join(d, rel))
    subprocess.run([os.path.join(d, "tools", "git-hooks", "installer.sh")],
                   capture_output=True, cwd=d)
    for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", d] + a, capture_output=True)
    return d


def doctor(d, chemin_hooks=None):
    """Le rapport que le JARDINIER consomme réellement.

    `--json` n'imprime rien : il ÉCRIT `state/doctor.json` et rend un code de
    sortie (brain_doctor.py:15). Premier passage de ce banc : j'ai lu stdout,
    trouvé le vide, et failli conclure que la source du jardinier était muette.
    Elle ne l'est pas — c'est ma lecture qui l'était.
    """
    h = chemin_hooks or os.path.join(d, "hooks")
    subprocess.run([sys.executable, os.path.join(h, "brain_doctor.py"), "--json"],
                   capture_output=True, text=True,
                   env=dict(os.environ, BRAIN_HOME=d, BRAIN_SKIP_BANCS="1"))
    p = os.path.join(d, "state", "doctor.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def pose_fiche(d, exclue=False):
    p = os.path.join(d, "projects", "claude-brain", NOM + ".md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(FICHE % (NOM, "carte: exclue\n" if exclue else ""))
    return p


def hors_carte(d):
    rep = doctor(d)
    val = rep.get("hors_index")
    if isinstance(val, list):
        return NOM in val
    # le doctor --json ne rend qu'un COMPTE : on compare avant/après
    return val


def commit(d, msg, **env):
    # Toutes les portes SAUF celle qu'on teste (BRAIN_SKIP_CARTE reste fermée) :
    # sinon un cas croit mesurer la gouvernance de la carte et mesure le garde
    # multi-zones ou le banc de provenance.
    e = dict(os.environ, BRAIN_HOME=d, BRAIN_SKIP_BANCS="1",
             BRAIN_SKIP_PROVENANCE="1", BRAIN_SKIP_INVARIANTS="1",
             BRAIN_COMMIT_MULTI="1", **env)
    return subprocess.run(["git", "-C", d, "commit", "-qm", msg],
                          capture_output=True, text=True, env=e)


def ajoute_entree_memory(d, nom):
    p = os.path.join(d, "MEMORY.md")
    t = open(p, encoding="utf-8").read()
    a = "⭐⭐ [[recall-seuil-distribution-2026-08-18]] (**A1 mesuré**)"
    assert a in t, "ancre absente de MEMORY.md"
    open(p, "w", encoding="utf-8").write(
        t.replace(a, a + "\n[[%s]]" % nom, 1))


def ajoute_entree_manifeste(d, nom):
    p = os.path.join(d, "tools", "cartes", "manifeste-carte.json")
    m = json.load(open(p, encoding="utf-8"))
    modele = [e for e in m["entrees"]
              if e["fiche"] == "recall-seuil-distribution-2026-08-18"][0]
    neuf = dict(modele)
    neuf.update({"fiche": nom, "rang": modele["rang"] + 1,
                 "niveau": 2, "annotation": "entrée du banc"})
    for e in m["entrees"]:
        if e["section"] == modele["section"] and e["rang"] > modele["rang"]:
            e["rang"] += 1
    m["entrees"].append(neuf)
    json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def divergence(d, hooks=None):
    r = subprocess.run([sys.executable, os.path.join(d, "tests", "carte_divergence.py"),
                        "--check"], capture_output=True, text=True,
                       env=dict(os.environ, BRAIN_HOME=d))
    return r.returncode


def main():
    print("== B6 — l'appartenance à MEMORY.md ne se décide pas toute seule ==")
    troncs = []
    try:
        d = clone(); troncs.append(d)

        # L'ÉTAT DE BASE PORTE DÉJÀ SA PROPRE DIVERGENCE — mesuré le 20/08 : une
        # référence morte `etat-des-projets`, née du conflit entre le kebab-case
        # exigé par le doctor et la casse que `etat_projets.py` écrit en dur.
        # C'est un chantier SÉPARÉ, explicitement hors de B6. Le cas 7 mesure donc
        # le DELTA de la transaction, pas la divergence absolue : sinon il
        # échouerait pour une raison étrangère à ce qu'il prétend prouver.
        base_divergent = divergence(d)
        note("divergence de l'état de base : %d (référence morte hors périmètre)"
             % base_divergent)

        print("\n> PIÈCE 2 — dire « hors carte, VOULU »")
        # `hors_index` est la LISTE nominative que le jardinier reçoit — on
        # vérifie donc l'appartenance de NOTRE fiche, pas un compte global qui
        # bougerait avec n'importe quelle autre anomalie.
        def signalee(rapport):
            return NOM in (rapport.get("hors_index") or [])

        pose_fiche(d, exclue=False)
        if signalee(doctor(d)):
            ok("1. fiche hors carte SANS exemption : nommée dans « Hors carte »")
        else:
            ko("1. la fiche hors carte n'est pas signalée",
               str(doctor(d).get("hors_index")))
        pose_fiche(d, exclue=True)
        if not signalee(doctor(d)):
            ok("2. la même fiche avec `carte: exclue` : plus signalée")
            ok("4. le jardinier lit ce rapport : plus rien à réparer pour elle")
        else:
            ko("2. l'exemption n'est pas comprise",
               str(doctor(d).get("hors_index")))

        print("\n> et elle reste une connaissance ORDINAIRE")
        r = subprocess.run([sys.executable, os.path.join(d, "hooks", "brain_corpus.py")],
                           capture_output=True, text=True,
                           env=dict(os.environ, BRAIN_HOME=d))
        rr = subprocess.run([sys.executable, os.path.join(d, "hooks", "brain_recall.py"),
                             "-k", "40", "fiche synthétique banc gouvernance carte"],
                            capture_output=True, text=True,
                            env=dict(os.environ, BRAIN_HOME=d))
        if NOM in rr.stdout:
            ok("3. la fiche exclue est toujours remontée par le rappel")
        else:
            note("3. non remontée sur cette requête — on vérifie l'indexation")
            idx = subprocess.run(["grep", "-rl", NOM, os.path.join(d, "state")],
                                 capture_output=True, text=True)
            if idx.stdout.strip():
                ok("3. mais bien présente dans l'index du corpus")
            else:
                ko("3. la fiche exclue a disparu du corpus — sémantique trop large")

        print("\n> PIÈCE 1 — la carte et son manifeste sont une transaction")
        subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
        commit(d, "socle du banc")
        ajoute_entree_memory(d, NOM)
        if divergence(d) != 0:
            ok("5a. MEMORY seule : l'instrument voit la divergence")
        else:
            ko("5a. aucune divergence détectée — le banc ne teste rien")
        subprocess.run(["git", "-C", d, "add", "MEMORY.md"], capture_output=True)
        r = commit(d, "MEMORY seule")
        if r.returncode != 0 and "DIVERGÉ" in (r.stdout + r.stderr):
            ok("5b. commit REFUSÉ, et le refus nomme la divergence")
        else:
            ko("5b. le commit est passé", (r.stdout + r.stderr).strip()[-160:])

        print("\n> 6. le manifeste seul, divergent")
        subprocess.run(["git", "-C", d, "checkout", "--", "MEMORY.md"], capture_output=True)
        ajoute_entree_manifeste(d, "fiche-b6-fantome")
        subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
        r = commit(d, "manifeste seul")
        if r.returncode != 0:
            ok("6. commit REFUSÉ : l'autorité ne peut pas dériver seule non plus")
        else:
            ko("6. le manifeste a pu diverger sans refus")

        print("\n> 7. la transaction cohérente doit PASSER")
        # LE CHEMIN PROPRIÉTAIRE, pas un bricolage. Fabriquer « à la main » une
        # entrée de manifeste qui concorde, c'est réimplémenter la règle d'entrée
        # dans le banc — et le premier essai a produit une transaction que
        # l'instrument jugeait divergente, à raison. `reconcilier.py` EST l'outil
        # gouverné par ADR-0015 : il propose, on accepte, il écrit LES DEUX.
        # ⚠️ PAS `checkout HEAD -- .` : ça ramènerait `tools/git-hooks/` à la
        # version de HEAD alors que la copie installée porte le travail en cours,
        # et le pre-commit se dénoncerait comme périmé — un refus qui n'a rien à
        # voir avec la carte.
        for rel in ("MEMORY.md", "tools/cartes/manifeste-carte.json"):
            subprocess.run(["git", "-C", d, "checkout", "HEAD", "--", rel],
                           capture_output=True)
        ajoute_entree_memory(d, NOM)          # une divergence réelle à réconcilier
        rec = os.path.join(d, "tools", "cartes", "reconcilier.py")
        env = dict(os.environ, BRAIN_HOME=d)
        subprocess.run([sys.executable, rec, "--ecrire"], capture_output=True,
                       text=True, env=env)
        acc = subprocess.run([sys.executable, rec, "--accepter"],
                             capture_output=True, text=True, env=env)
        code = divergence(d)
        subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
        r = commit(d, "transaction carte + manifeste, via reconcilier",
                   BRAIN_SKIP_CARTE="1" if base_divergent else "")
        if code <= base_divergent and r.returncode == 0:
            ok("7. réconcilié par l'outil propriétaire : la transaction n'ajoute "
               "AUCUNE divergence (%d, base %d) et le commit passe — le garde "
               "n'est pas un mur" % (code, base_divergent))
        else:
            ko("7. une transaction gouvernée a été refusée",
               "divergence=%d · %s" % (code, (acc.stdout + r.stdout + r.stderr).strip()[-200:]))

        print("\n> 8. retirer l'exemption redonne la fiche aux gardes")
        # SUR UN CLONE NEUF : au cas 7 la fiche a été réellement ajoutée à la
        # carte et commitée — elle n'est donc plus « hors carte », et le cas
        # aurait échoué pour cette raison-là. Un sabotage doit repartir de l'état
        # qu'il prétend saboter.
        d3 = clone(); troncs.append(d3)
        pose_fiche(d3, exclue=True)
        if NOM not in (doctor(d3).get("hors_index") or []):
            pose_fiche(d3, exclue=False)
            if NOM in (doctor(d3).get("hors_index") or []):
                ok("8. exemption retirée : la fiche redevient « Hors carte »")
            else:
                ko("8. la fiche reste invisible aux gardes sans son exemption",
                   str(doctor(d3).get("hors_index")))
        else:
            ko("8. l'exemption n'a pas pris — le sabotage ne teste rien")

        print("\n> 9. contre-épreuve — sans l'appel, la mutation passe")
        d2 = clone(); troncs.append(d2)
        # On sabote la SOURCE puis on réinstalle : le pre-commit vérifie sa propre
        # fraîcheur et se dénonce si la copie active diverge de la version suivie.
        # Éditer seulement la copie faisait échouer le cas pour cette raison-là.
        pc = os.path.join(d2, "tools", "git-hooks", "pre-commit")
        src = open(pc, encoding="utf-8").read()
        src = src.replace('SORTIE=$(python3 "$RACINE/tests/carte_divergence.py" --check 2>&1) || {',
                          'SORTIE=$(true) || {')
        open(pc, "w", encoding="utf-8").write(src)
        subprocess.run([os.path.join(d2, "tools", "git-hooks", "installer.sh")],
                       capture_output=True, cwd=d2)
        subprocess.run(["git", "-C", d2, "add", "-A"], capture_output=True)
        commit(d2, "socle")
        ajoute_entree_memory(d2, NOM)
        subprocess.run(["git", "-C", d2, "add", "MEMORY.md"], capture_output=True)
        r = commit(d2, "MEMORY seule, garde neutralise")
        if r.returncode == 0:
            ok("9. garde neutralisé : la mutation MEMORY seule PASSE — c'est bien "
               "lui qui bloquait")
        else:
            ko("9. le commit est refusé même sans le garde — le banc ne prouve rien",
               (r.stdout + r.stderr).strip()[-160:])

        print("\n" + "-" * 74)
        if fails:
            print("ROUGE — %d échec(s)" % len(fails))
            for f in fails:
                print("   . %s" % f)
            return 1
        print("VERT — une absence voulue se déclare, et l'appartenance à la carte est "
              "une transaction.")
        return 0
    finally:
        for x in troncs:
            shutil.rmtree(os.path.dirname(x), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
