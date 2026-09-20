#!/usr/bin/env python3
"""casse_disque_git.py — le disque et git doivent orthographier pareil.

CE QUI EST ARRIVÉ (2026-08-20). `projects/ETAT-DES-PROJETS.md` a été renommé en
minuscules sur le disque. macOS étant insensible à la casse, git a continué de
suivre l'ancienne orthographe et **rien n'a rien dit** : le doctor lisait le nom
du disque et le trouvait conforme, donc vert.

POURQUOI CE N'EST PAS COSMÉTIQUE. Sur un système de fichiers SENSIBLE à la casse
— Linux, une CI, un autre poste — `git checkout` matérialise l'orthographe qu'il
suit. Le tronc se retrouve alors avec `ETAT-DES-PROJETS.md` **à côté** de
`etat-des-projets.md` : deux fichiers, deux fiches, un doublon. Une divergence
invisible ici devient une duplication ailleurs. Le Brain se clone ; ce qui ne
survit pas au clone n'est pas une propriété du dépôt.

CE QUE LE BANC SÉPARE. Une divergence de CASSE (même chemin logique, deux
orthographes) n'est pas la même chose que deux fichiers RÉELLEMENT distincts,
qui peuvent coexister sur un système sensible à la casse et sont parfaitement
légitimes. La logique de comparaison est donc pure et testable sur des données
synthétiques, sans dépendre du système de fichiers qui exécute le banc.

Run: python3 tests/casse_disque_git.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── I-2 · PROFIL D'ÉTAT (lot 1) — TÉMOIN REPRODUCTIBLE ───────────────────────
# Branché ici précisément parce que ce banc ne lit AUCUN état local : il sert de
# contrôle négatif au profil. Si un banc sans dépendance externe ressortait
# « non reproductible », l'instrument produirait un faux rouge, et un faux rouge
# répété finit ignoré.
try:
    sys.path.insert(0, os.path.join(ROOT, "hooks"))
    import i2_profil
    i2_profil.demarrer("casse_disque_git")
except Exception:
    pass

fails = []


def ok(l):
    print("  OK   %s" % l)


def ko(l, d=""):
    print("  FAIL %s%s" % (l, ("  -- " + d) if d else ""))
    fails.append(l)


def divergences(suivis, entrees_par_dossier):
    """LOGIQUE PURE — aucune lecture de disque, donc testable partout.

    `suivis` : chemins tels que git les enregistre.
    `entrees_par_dossier` : {dossier: [noms réels du disque]}.

    Une divergence, c'est : git suit un nom que le disque n'a PAS, alors qu'il a
    le même à la casse près. Si le disque porte exactement le nom suivi, il n'y
    a rien à signaler — même si une autre orthographe existe à côté, car ce sont
    alors deux fichiers distincts, pas une divergence.
    """
    out = []
    for rel in suivis:
        dossier, nom = os.path.split(rel)
        entrees = entrees_par_dossier.get(dossier, [])
        if nom in entrees:
            continue
        jumeaux = [e for e in entrees if e.lower() == nom.lower()]
        if jumeaux:
            out.append((rel, os.path.join(dossier, jumeaux[0])))
    return out


def lire_depot(racine):
    suivis = subprocess.run(["git", "-C", racine, "ls-files"],
                            capture_output=True, text=True).stdout.split()
    dossiers = {}
    for rel in suivis:
        d = os.path.dirname(rel)
        if d not in dossiers:
            try:
                dossiers[d] = os.listdir(os.path.join(racine, d) if d else racine)
            except OSError:
                dossiers[d] = []
    return suivis, dossiers


def main():
    print("== casse : le disque et git orthographient-ils pareil ? ==")

    print("\n> calibration — la logique, sur des données synthétiques")
    cas = [
        ("casse identique", ["a/f.md"], {"a": ["f.md"]}, 0),
        ("même chemin, casse différente", ["a/F.md"], {"a": ["f.md"]}, 1),
        ("deux fichiers RÉELLEMENT distincts (FS sensible à la casse)",
         ["a/f.md", "a/F.md"], {"a": ["f.md", "F.md"]}, 0),
        ("git suit un fichier absent (pas une affaire de casse)",
         ["a/parti.md"], {"a": ["f.md"]}, 0),
        ("plusieurs divergences", ["a/F.md", "a/G.md"], {"a": ["f.md", "g.md"]}, 2),
    ]
    for nom, suivis, dossiers, attendu in cas:
        n = len(divergences(suivis, dossiers))
        if n == attendu:
            ok("%s : %d" % (nom, n))
        else:
            ko("%s : %d, attendu %d" % (nom, n, attendu))

    print("\n> le tronc réel")
    suivis, dossiers = lire_depot(ROOT)
    div = divergences(suivis, dossiers)
    if not div:
        ok("%d fichiers suivis, aucune divergence de casse" % len(suivis))
    else:
        for g, d in div:
            ko("git suit « %s », le disque porte « %s »" % (g, d))

    if "--check" in sys.argv:
        # Chemin du pre-commit : la logique est calibrée et le tronc mesuré, mais
        # PAS le sabotage par clone — il coûte une copie complète du dépôt, ce qui
        # n'a pas sa place sur le chemin d'un commit.
        print("\n" + "-" * 74)
        print(("ROUGE — %d" % len(fails)) if fails else "VERT — une seule orthographe par chemin.")
        return 1 if fails else 0

    print("\n> sabotage — sur une COPIE, on renomme et le banc doit rougir")
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="casse."))
    try:
        cible = os.path.join(tmp, "t")
        r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", ROOT, cible],
                           capture_output=True, text=True)
        if r.returncode != 0:
            ko("le clone a échoué", r.stderr[:120])
        else:
            s, dd = lire_depot(cible)
            if not divergences(s, dd):
                ok("clone propre : concordance")
            else:
                ko("un clone frais diverge déjà")
            victime = os.path.join(cible, "meta", "claude-brain.md")
            if os.path.exists(victime):
                os.rename(victime, os.path.join(cible, "meta", "CLAUDE-BRAIN.md"))
                s, dd = lire_depot(cible)
                d2 = divergences(s, dd)
                if any(g.endswith("meta/claude-brain.md") for g, _ in d2):
                    ok("renommage en majuscules : détecté (%d divergence)" % len(d2))
                else:
                    ko("le renommage n'est pas détecté — le banc ne prouve rien")
            else:
                ko("fichier témoin absent du clone")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "-" * 74)
    if fails:
        print("ROUGE — %d échec(s)" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("VERT — une seule orthographe par chemin, du disque jusqu'à git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
