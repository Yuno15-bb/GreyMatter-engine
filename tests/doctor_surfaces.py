#!/usr/bin/env python3
"""
doctor_surfaces.py — ce que `brain doctor` a le droit de TAIRE, et ce qu'il doit voir.

POURQUOI CE BANC EXISTE (2026-09-20, friction #7 du chantier B, entrée B1 de C bis).
La friction demandait : « `brain doctor` doit-il distinguer l'état transitoire de
l'anomalie ? » La mesure a répondu autrement qu'attendu. Sur le vrai tronc, la rubrique
« Orphelins » comptait 57 entrées ; AUCUNE n'était une fiche neuve en attente de son
premier lien. Les 57 étaient un seul défaut d'identité (`skills/synced/<uuid>/<slug>/`
rabattu sur l'identité « synced »). La prémisse de l'arbitrage était fausse : il n'y avait
pas d'état transitoire à séparer, il y avait un instrument cassé.

Ce qui était VRAI dans la friction s'est montré ailleurs, et ce banc verrouille les trois
pièces de la réponse :

  1. UNE COUPE MUETTE LAISSE CROIRE QU'ON A TOUT VU. Les listes sont coupées à 12. Avec
     58 plaintes de frontmatter, le skill saboté exprès par `tests/identite_skills.py`
     tombait au 13ᵉ rang, donc hors écran, et ce banc-là rougissait sur « SABOTAGE
     INVISIBLE » sans que la sortie du doctor n'ait l'air fautive. Du bruit qui cache un
     défaut. La coupe doit se NOMMER là où elle coupe.

  2. LA VRAIE FRONTIÈRE EST UN SEUIL D'ÂGE, PAS UNE CATÉGORIE. `etat_projets.py` tourne à
     8 h et 19 h, sort en 0, affiche sa bannière — et depuis le 28/08 il ne mesure plus
     rien : le service launchd n'a pas le droit de lire le Bureau. Le programme refuse
     alors (correctement) d'écraser sa dernière mesure et annonce son âge. Un jour, c'est
     un état passager ; vingt-trois jours, c'est une panne. Rien ne faisait passer l'un
     dans l'autre.

  3. UN VERDICT GLOBAL N'EST PAS UN CONSTAT. Le doctor interroge
     `tools/settings_projection.py --verifie` et récolte ses ❌. Sa dernière ligne est son
     verdict — « ❌ écart(s) — `--diff` puis `--installe` » — et la compter ajoutait un
     défaut qui n'existe pas, à chaque run. Les constats sont indentés sous leur section ;
     le verdict est en colonne 0.

  python3 tests/doctor_surfaces.py
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
DOCTOR = os.path.join(BRAIN, "hooks", "brain_doctor.py")

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)


def tronc_jetable():
    """Le plus petit tronc que le doctor accepte de lire."""
    d = tempfile.mkdtemp(prefix="doctor-surfaces-")
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")
    os.makedirs(os.path.join(d, "lessons"))
    os.makedirs(os.path.join(d, "state"))
    open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8").write("# carte\n")
    open(os.path.join(d, "lessons", "INDEX.md"), "w", encoding="utf-8").write("# index\n")
    return d


def doctor(tronc):
    r = subprocess.run([sys.executable, DOCTOR], capture_output=True, text=True,
                       env={**os.environ, "BRAIN_HOME": tronc}, timeout=120)
    return r.stdout


def ligne(sortie, libelle):
    for l in sortie.splitlines():
        if libelle in l:
            return l
    return ""


# ── 1. la coupe à 12 se dit, et seulement quand elle coupe ───────────────────
def cas_1():
    print("\n1. UNE LISTE COUPÉE DIT QU'ELLE EST COUPÉE")
    for n, attendu in ((5, 0), (15, 3)):
        d = tronc_jetable()
        for i in range(n):
            open(os.path.join(d, "lessons", "f-%02d.md" % i), "w", encoding="utf-8").write(
                "---\nname: f-%02d\ndescription: \"x\"\ntags: [t]\n---\n\n# f\n" % i)
        l = ligne(doctor(d), "Hors carte")
        m = re.search(r"\+(\d+) non montré", l)
        vu = int(m.group(1)) if m else 0
        annonce = re.search(r"\((\d+)\)", l)
        if not annonce or int(annonce.group(1)) != n:
            ko("%d fiches hors carte : le doctor en annonce %s"
               % (n, annonce.group(1) if annonce else "aucune"))
        elif vu != attendu:
            ko("%d entrées, 12 montrées → le marqueur devrait dire +%d, il dit +%d"
               % (n, attendu, vu))
        elif attendu == 0:
            ok("%d entrées, rien n'est caché : aucun marqueur de coupe" % n)
        else:
            ok("%d entrées, 12 montrées : « … +%d non montré(s) » à l'endroit de la coupe"
               % (n, vu))


# ── 2. le seuil d'âge de la ronde d'état ─────────────────────────────────────
def cas_2():
    print("\n2. LA RONDE D'ÉTAT — UN JOUR EST UN ÉTAT, TROIS JOURS SONT UNE PANNE")
    for jours, doit_rougir in ((0, False), (2, False), (9, True)):
        d = tronc_jetable()
        quand = datetime.datetime.now() - datetime.timedelta(days=jours, minutes=1)
        json.dump({"mesure_le": quand.isoformat(), "depots": [], "depots_max": 0},
                  open(os.path.join(d, "state", "etat-projets.json"), "w", encoding="utf-8"))
        l = ligne(doctor(d), "Ronde d'état")
        if doit_rougir and not l:
            ko("mesure vieille de %d j : le doctor ne dit rien" % jours)
        elif not doit_rougir and l:
            ko("mesure vieille de %d j : le doctor crie alors que c'est normal" % jours)
        elif doit_rougir:
            age = re.search(r"il y a (\d+) j", l)
            if not age or int(age.group(1)) != jours:
                ko("le doctor rougit mais ne dit pas le bon âge : %s" % l.strip()[:90])
            else:
                ok("mesure vieille de %d j : signalée, avec son âge" % jours)
        else:
            ok("mesure vieille de %d j : rien à signaler, c'est le rythme normal" % jours)

    # CONTRE-ÉPREUVE : pas de cache du tout ≠ cache périmé. Un tronc qui n'a jamais
    # lancé la ronde ne doit pas être accusé de l'avoir laissée pourrir.
    d = tronc_jetable()
    if ligne(doctor(d), "Ronde d'état"):
        ko("aucun cache : le doctor accuse un tronc qui n'a jamais lancé la ronde")
    else:
        ok("aucun cache : le doctor se tait — jamais lancé n'est pas périmé")


# ── 3. le verdict du vérificateur n'est pas un de ses constats ───────────────
def cas_3():
    print("\n3. LES ÉCARTS DE HOOKS SONT COMPTÉS UN PAR UN, LE VERDICT NE COMPTE PAS")
    proj = os.path.join(BRAIN, "tools", "settings_projection.py")
    if not os.path.exists(proj):
        ok("pas de projecteur sur ce tronc — contrôle sans objet")
        return
    r = subprocess.run([sys.executable, proj, "--verifie"], capture_output=True,
                       text=True, timeout=60)
    # la vérité de référence : les ❌ INDENTÉS, ceux qui vivent sous une section.
    attendus = [l for l in r.stdout.splitlines()
                if l.startswith(" ") and l.strip().startswith("❌")]
    verdicts = [l for l in r.stdout.splitlines()
                if not l.startswith(" ") and l.strip().startswith("❌")]
    l = ligne(doctor(BRAIN), "Hooks Claude Code")
    m = re.search(r"\((\d+)\)", l)
    compte = int(m.group(1)) if m else 0
    if r.returncode == 0:
        if compte:
            ko("le projecteur est conforme et le doctor signale %d écart(s)" % compte)
        else:
            ok("projection conforme, doctor muet")
        return
    if compte != len(attendus):
        ko("%d écart(s) indenté(s) chez le projecteur, %d comptés par le doctor "
           "(%d ligne(s) de verdict en colonne 0)" % (len(attendus), compte, len(verdicts)))
    elif not verdicts:
        ko("le vérificateur sort en %d sans ligne de verdict — le contrôle ne prouve rien"
           % r.returncode)
    else:
        ok("%d écart(s) comptés, %d verdict(s) global(aux) écarté(s)"
           % (compte, len(verdicts)))


for c in (cas_1, cas_2, cas_3):
    c()

print("\n" + "-" * 74)
if fails:
    print("ROUGE — %d échec(s)" % len(fails))
    for f in fails:
        print("   . %s" % f)
    sys.exit(1)
print("VERT — le doctor nomme ce qu'il cache, date ce qui a vieilli, "
      "et ne compte pas un verdict pour un défaut.")
