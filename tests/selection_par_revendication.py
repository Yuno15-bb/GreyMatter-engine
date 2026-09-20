#!/usr/bin/env python3
"""selection_par_revendication.py — la chaîne de robots ne commite que ce qu'elle a écrit.

CE QUI EST ARRIVÉ. `hooks/commit_par_zone.py` sélectionne « tout ce qui est modifié dans la
zone ». Mesuré en production le 2026-09-15 : la passe automatique a commité 40 fichiers, dont
13 seulement avaient été écrits par un robot — 14 fichiers d'une session de refonte UI, des
fiches de deux autres sessions, des sauvegardes de manifeste. L'absorption vient de la
SÉLECTION, pas du pathspec (projects/claude-brain/gouvernance-git-multisession-2026-08-29.md).
`tools/revendication/` répare ça et est qualifié par sabotage depuis le 15/09 — 9/9 contre 2/9
pour l'ancienne sélection — mais il est resté QUATRE JOURS sans être branché nulle part.

CE QUE CE BANC VERROUILLE, ET POURQUOI CES POINTS-LÀ :
  1. la passe automatique commite par revendication (`revendiquer.py commite`) ;
  2. la photo se prend AVANT le premier robot — prise après, le veto n'a plus de point de
     comparaison et laisse passer le brouillon d'un voisin sans que rien ne rougisse ;
  3. dans `auto_maintain`, l'ancienne sélection ne subsiste que dans la branche de repli du
     paquet livré (`tools/` n'y est pas) — jamais comme chemin normal ;
  4. dans `sync_depots`, l'ancienne sélection n'est atteignable que hors passe automatique.
     C'est LE piège : `sync_depots --auto` tourne juste après la passe, et commitait « tout
     ce qui est modifié » — donc exactement ce que la revendication venait d'épargner.
     Brancher un seul des deux endroits ne réparait rien du tout.
  5. la photo porte sa propre borne de lecture et sa date de péremption.

CE QU'IL NE VÉRIFIE PAS. Que la sélection est JUSTE : ça, c'est `tools/revendication/banc.py`,
neuf sabotages sur une copie jetable du tronc réel, trop lourd pour un hook de commit (il
clone le tronc dix fois). Ici on vérifie seulement que le câblage n'a pas été défait. C'est
une lecture de la SOURCE, pas du script réellement engendré : un changement qui garderait ces
phrases tout en cassant l'ordre d'exécution passerait.

Sabotages vérifiés à l'écriture (2026-09-19), quatre, tous en code 1, retirés tous en
code 0 : remettre `commit_par_zone.py` comme chemin normal d'`auto_maintain` · transformer la
prise de photo en affectation morte · déplacer la photo juste avant le commit, donc après les
robots · rendre `commit_par_zone(BRAIN…)` atteignable en passe automatique dans `sync_depots`.
Le deuxième est celui qui a corrigé le banc : à sa première écriture il comparait des
positions de texte et restait VERT alors que la photo n'était plus prise du tout.

Run: python3 tests/selection_par_revendication.py --check
"""
import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(ROOT, "hooks", "auto_maintain.py")
SYNC = os.path.join(ROOT, "tools", "sync_depots.py")
REV = os.path.join(ROOT, "tools", "revendication", "revendiquer.py")


def lire(p):
    return io.open(p, encoding="utf-8").read()


def ou(texte, motif):
    """Le numéro de ligne de la première occurrence, ou None."""
    for n, l in enumerate(texte.split("\n"), 1):
        if motif in l:
            return n
    return None


def contributions_au_script(source, fonction):
    """Ce qui ALIMENTE la liste `lines` dans `fonction`, dans l'ordre du fichier.

    Lire des positions de texte ne suffisait pas : un sabotage qui remplace
    `lines.append(…)` par une affectation morte laisse la phrase en place à la même
    ligne, et le banc restait vert alors que la photo n'était plus prise du tout
    (constaté à l'écriture, le 2026-09-19). On regarde donc ce qui entre vraiment dans
    le script : un `lines.append`/`lines.extend`, ou un `lines += …`.
    """
    arbre = ast.parse(source)
    src = source.split("\n")
    dedans = []
    for f in ast.walk(arbre):
        if not (isinstance(f, ast.FunctionDef) and f.name == fonction):
            continue
        for n in ast.walk(f):
            nourrit = (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr in ("append", "extend")
                       and isinstance(n.func.value, ast.Name) and n.func.value.id == "lines")
            nourrit |= (isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
                        and n.target.id == "lines")
            if nourrit:
                fin = getattr(n, "end_lineno", n.lineno) or n.lineno
                dedans.append((n.lineno, "\n".join(src[n.lineno - 1:fin])))
    return sorted(dedans)


def fonctions_appelantes(source, nom, premier_argument):
    """Les fonctions qui appellent `nom(premier_argument, …)`.

    Le premier argument compte : `sync_depots` commite aussi le dépôt du PAQUET public
    (`commit_par_zone(cible, "sync: ")`), qui n'a ni robots ni transcripts et pour lequel
    la sélection large est la bonne. Sans ce filtre, le banc rougissait sur un appel
    parfaitement légitime — et un banc qui rougit à tort finit par être ignoré.
    """
    arbre = ast.parse(source)
    dedans = []
    for f in ast.walk(arbre):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(f):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == nom and n.args
                    and isinstance(n.args[0], ast.Name)
                    and n.args[0].id == premier_argument):
                dedans.append(f.name)
                break
    return sorted(set(dedans))


def defauts():
    d = []

    a = lire(AUTO)
    if '"{revendiquer}" commite --instantane' not in a:
        d.append("auto_maintain ne commite plus par revendication")
    script = contributions_au_script(a, "launch_agent")
    photo = next((i for i, (_, t) in enumerate(script) if '"{revendiquer}" instantane' in t), None)
    robot = next((i for i, (_, t) in enumerate(script) if "agent_call(" in t), None)
    if photo is None:
        d.append("auto_maintain ne met plus la photo d'avant-passe dans le script de la passe")
    elif robot is not None and photo > robot:
        d.append("la photo est prise APRÈS le premier robot — le veto n'a plus de repère")
    if a.count("hooks/commit_par_zone.py") != 1:
        d.append("auto_maintain nomme l'ancienne sélection %d fois (1 attendue : le repli)"
                 % a.count("hooks/commit_par_zone.py"))
    else:
        n = ou(a, "hooks/commit_par_zone.py")
        contexte = "\n".join(a.split("\n")[max(0, n - 4):n])
        if "else" not in contexte:
            d.append("l'ancienne sélection n'est plus dans la branche de repli d'auto_maintain")

    if os.path.exists(SYNC):                       # `tools/` n'est pas dans le paquet livré
        s = lire(SYNC)
        appelants = fonctions_appelantes(s, "commit_par_zone", "BRAIN")
        if appelants != ["commiter_le_tronc"]:
            d.append("sync_depots commite le TRONC par l'ancienne sélection depuis %s "
                     "(attendu : commiter_le_tronc seul)" % (appelants or "nulle part"))
        elif "REVENDIQUER" not in s.split("def commiter_le_tronc")[1].split("\ndef ")[0]:
            d.append("commiter_le_tronc ne passe plus par la revendication")

    if os.path.exists(REV):
        r = lire(REV)
        if '"depuis_ligne": lignes_cost(cwd)' not in r:
            d.append("la photo ne porte plus sa borne de lecture de cost.jsonl")
        if "FRAICHEUR_MAX" not in r:
            d.append("une photo périmée n'est plus refusée")
    return d


def main():
    d = defauts()
    for m in d:
        print(f"❌ {m}")
    if not d:
        print("✅ sélection par revendication branchée — passe automatique et sync_depots ; "
              "ancienne sélection seulement en repli du paquet livré")
    return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main())
