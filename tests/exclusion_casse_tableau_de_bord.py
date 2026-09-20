#!/usr/bin/env python3
"""exclusion_casse_tableau_de_bord.py — ETAT-DES-PROJETS ne se propose jamais.

VERDICT INDÉPENDANT de celui de la clé de classement : deux correctifs, deux
bancs, pour qu'un vert ne porte pas l'autre.

LE DÉFAUT. `ETAT-DES-PROJETS.md` est un tableau de bord GÉNÉRÉ qui contient « ce
qu'il faut reprendre » : s'il entre dans le scan, il se détecte lui-même et
squatte la première place. Il était donc exclu — par une comparaison LITTÉRALE.
Or macOS est insensible à la casse : `planet/graph.json` portait
`projects/etat-des-projets.md` là où le disque porte `ETAT-DES-PROJETS.md`.
La même fiche avait deux orthographes, et l'exclusion en ratait une.

CE QUE CE BANC EXIGE. Les trois orthographes conduisent à la même exclusion, et
une fiche ordinaire reste candidate — sans ce dernier point, une exclusion qui
exclurait TOUT passerait pour un succès.

Run: python3 tests/exclusion_casse_tableau_de_bord.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
fails = []


def ok(l):
    print("  OK   %s" % l)


def ko(l, d=""):
    print("  FAIL %s%s" % (l, ("  -- " + d) if d else ""))
    fails.append(l)


FICHE = "---\nname: %s\n---\n\n# Point de reprise : quelque chose à finir\n"


def tronc(nom_tableau, hooks=None):
    """Un tronc minimal, versionné, avec le tableau de bord sous UNE orthographe."""
    d = os.path.realpath(tempfile.mkdtemp(prefix="casse."))
    os.makedirs(os.path.join(d, "projects"))
    open(os.path.join(d, "projects", nom_tableau), "w").write(FICHE % nom_tableau[:-3])
    open(os.path.join(d, "projects", "une-fiche-ordinaire.md"), "w").write(
        FICHE % "une-fiche-ordinaire")
    open(os.path.join(d, "MEMORY.md"), "w").write(FICHE % "memory")
    for a in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", d] + a, capture_output=True)
    subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "tronc"], capture_output=True)
    return d


def collecte(racine, hooks=None):
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import brain_anticipate as ba
        print(json.dumps([i["path"] for i in ba.collect()]))
    """) % (hooks or HOOKS)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, BRAIN_HOME=racine))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def cas(nom_tableau, hooks=None):
    d = tronc(nom_tableau, hooks)
    try:
        return collecte(d, hooks), d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print("== exclusion du tableau de bord — insensible à la casse ==")

    print("\n> les trois orthographes mènent à la même exclusion")
    for nom in ("ETAT-DES-PROJETS.md", "etat-des-projets.md", "Etat-Des-Projets.md"):
        trouve, _ = cas(nom)
        if not any("etat-des-projets" in p.lower() for p in trouve):
            ok("%-22s exclu" % nom)
        else:
            ko("%-22s a été proposé comme reprise" % nom, str(trouve))

    print("\n> contrôle négatif — une fiche ordinaire reste candidate")
    trouve, _ = cas("ETAT-DES-PROJETS.md")
    if "projects/une-fiche-ordinaire.md" in trouve:
        ok("une-fiche-ordinaire.md est bien collectée (%d candidat(s))" % len(trouve))
    else:
        ko("l'exclusion emporte tout — un banc qui exclut tout n'exclut rien",
           str(trouve))

    print("\n> MEMORY.md est exclu par le même chemin")
    if not any(p.lower() == "memory.md" for p in trouve):
        ok("MEMORY.md n'entre pas dans les reprises")
    else:
        ko("MEMORY.md a été proposé comme reprise")

    print("\n> sabotage — la comparaison littérale laissait passer une orthographe")
    tmp = tempfile.mkdtemp(prefix="casse-sab.")
    try:
        casse = os.path.join(tmp, "hooks")
        shutil.copytree(HOOKS, casse)
        src = open(os.path.join(casse, "brain_anticipate.py"), encoding="utf-8").read()
        avant = 'if rel.lower() in EXCLUS_TOUJOURS \\'
        assert avant in src, "le sabotage ne trouve plus la ligne à saboter"
        src = src.replace(avant, 'if rel in ("MEMORY.md", "projects/ETAT-DES-PROJETS.md") \\')
        open(os.path.join(casse, "brain_anticipate.py"), "w", encoding="utf-8").write(src)
        trouve, _ = cas("etat-des-projets.md", hooks=casse)
        if any("etat-des-projets" in p.lower() for p in trouve):
            ok("avec la comparaison littérale, l'orthographe minuscule PASSE : "
               "le banc reproduit bien le défaut")
        else:
            ko("le sabotage ne reproduit pas le défaut — ce banc ne prouve rien")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "-" * 74)
    if fails:
        print("ROUGE — %d échec(s)" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("VERT — une seule fiche, quelle que soit son orthographe, une seule exclusion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
