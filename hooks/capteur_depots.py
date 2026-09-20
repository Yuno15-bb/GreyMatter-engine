#!/usr/bin/env python3
"""Capteur de dépôts non sauvegardés — le travail qui n'existe QUE sur ce Mac.

Pourquoi il existe (2026-08-22). `codex M.confidential` : dernier commit le 13/08,
puis 70 fichiers modifiés et 6 306 insertions restés en working tree pendant NEUF JOURS,
dont ~20 fichiers jamais suivis — donc sans aucune version antérieure à récupérer.
Découvert par hasard en lisant le dépôt pour un cadrage. Le même jour : 8 commits jamais
poussés sur `mconfidential-edl`, une branche sans destination sur `mconfidential-edl-simple`,
et `cahier` sans aucun dépôt distant.

Le dispositif `sauvegarde-totale-github` couvrait déjà le Bureau NON-git, et sa fiche
signalait l'angle mort « un .git sans remote ». Il manquait le cas d'à côté, plus courant :
un dépôt QUI A un remote mais dont le travail n'y est jamais parti. Le dispositif reposait
sur une règle (« commit + push comme d'habitude ») — une règle n'est pas un capteur.

L'OBSERVABLE EST L'ÉTAT GIT RÉEL DU DISQUE : `git status --porcelain`, `rev-list @{u}..HEAD`,
`git remote`. Jamais une intention, jamais un journal de script. Mesure 100 % locale : aucun
`fetch`, donc pas de réseau et pas d'attente au démarrage de session.

  python3 capteur_depots.py            # rapport lisible
  python3 capteur_depots.py --hook     # bloc au démarrage de session (silencieux si tout est vert)
  python3 capteur_depots.py --json     # état brut
  python3 capteur_depots.py --notifier # + notification macOS si rouge (pour launchd)

  DEPOTS_RACINES=/chemin/a:/chemin/b   # surcharge du périmètre — pour SABOTER sur des
                                       # fixtures sans toucher aux vrais dépôts.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()

# Surchargeable : un capteur qu'on ne peut pas casser exprès n'a jamais prouvé qu'il rougit.
RACINES = [Path(p) for p in os.environ.get("DEPOTS_RACINES", str(HOME / "Desktop")).split(":") if p]
PROFONDEUR = int(os.environ.get("DEPOTS_PROFONDEUR", "3"))

# Un travail non sauvegardé le jour même est NORMAL (session en cours).
# Ce qui est anormal, c'est qu'il dure. Le drame mesuré faisait 9 jours.
ORANGE_JOURS = 1
ROUGE_JOURS = 3

ICONE = {"rouge": "🔴", "orange": "🟠", "vert": "🟢"}


def _git(depot, *args):
    try:
        r = subprocess.run(["git", "-C", str(depot), *args],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def trouver_depots():
    vus, depots = set(), []
    for racine in RACINES:
        if not racine.is_dir():
            continue
        try:
            out = subprocess.run(
                ["find", str(racine), "-maxdepth", str(PROFONDEUR), "-name", ".git", "-type", "d"],
                capture_output=True, text=True, timeout=60).stdout
        except Exception:
            continue
        for ligne in out.splitlines():
            d = Path(ligne).parent.resolve()
            if d not in vus:
                vus.add(d)
                depots.append(d)
    return sorted(depots)


def examiner(depot):
    """Un constat par dépôt. Le niveau vient des FAITS mesurés, pas d'une appréciation."""
    nom = depot.name
    remotes = _git(depot, "remote") or ""
    sale = len([l for l in (_git(depot, "status", "--porcelain") or "").splitlines() if l])
    dernier = _git(depot, "log", "-1", "--format=%ct")
    age = (time.time() - int(dernier)) / 86400 if dernier and dernier.isdigit() else None

    # 1. Aucune destination : le travail n'existe nulle part ailleurs. Structurel, jamais toléré.
    if not remotes:
        return dict(depot=nom, chemin=str(depot), niveau="rouge",
                    msg="aucun dépôt distant — ce travail n'existe que sur ce Mac",
                    observable="git remote → (vide)", sale=sale, ahead=0, age_j=age)

    # 2. Branche sans destination : les commits partent nulle part, et `ahead` est illisible.
    upstream = _git(depot, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    branche = _git(depot, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    if upstream is None:
        return dict(depot=nom, chemin=str(depot), niveau="rouge",
                    msg=f"branche « {branche} » sans destination — ses commits ne partent nulle part",
                    observable="git rev-parse @{u} → échec", sale=sale, ahead=0, age_j=age)

    ahead_s = _git(depot, "rev-list", "--count", "@{u}..HEAD")
    ahead = int(ahead_s) if ahead_s and ahead_s.isdigit() else 0

    # 3. Du travail existe qui n'est pas sur GitHub. La gravité vient de sa DURÉE.
    if sale or ahead:
        if age is None:
            niveau = "rouge"
        elif age >= ROUGE_JOURS:
            niveau = "rouge"
        elif age >= ORANGE_JOURS:
            niveau = "orange"
        else:
            niveau = "vert"          # session du jour : normal
        bouts = []
        if sale:
            bouts.append(f"{sale} fichier(s) non enregistré(s)")
        if ahead:
            bouts.append(f"{ahead} commit(s) jamais poussé(s)")
        suffixe = f", dernier enregistrement il y a {age:.1f} j" if age is not None else ""
        return dict(depot=nom, chemin=str(depot), niveau=niveau,
                    msg=" et ".join(bouts) + suffixe,
                    observable=f"git status --porcelain → {sale} · rev-list @{{u}}..HEAD → {ahead}",
                    sale=sale, ahead=ahead, age_j=age)

    return dict(depot=nom, chemin=str(depot), niveau="vert", msg="à jour sur son dépôt distant",
                observable="git status --porcelain → 0 · rev-list @{u}..HEAD → 0",
                sale=0, ahead=0, age_j=age)


def mesurer():
    constats = [examiner(d) for d in trouver_depots()]
    return {
        "quand": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "constats": constats,
        "rouges": [c for c in constats if c["niveau"] == "rouge"],
        "oranges": [c for c in constats if c["niveau"] == "orange"],
    }


def notifier(rouges):
    """Une alerte qui ne se voit pas ne sert à rien — c'est exactement le défaut qu'on corrige."""
    if not rouges:
        return
    txt = " · ".join(c["depot"] for c in rouges[:4])
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{txt}" with title "Dépôts non sauvegardés" sound name "Basso"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def main():
    args = sys.argv[1:]
    etat = mesurer()

    if "--hook" in args:
        if etat["rouges"]:
            print("<depots-non-sauvegardes> Du travail n'existe que sur ce Mac :")
            for c in etat["rouges"]:
                print(f"- {c['depot']} : {c['msg']}")
            print("</depots-non-sauvegardes>")
        return 0

    if "--notifier" in args:
        notifier(etat["rouges"])

    if "--json" in args:
        print(json.dumps(etat, indent=2, ensure_ascii=False))
        return 0

    print(f"🗄  Dépôts non sauvegardés — {etat['quand']}")
    for c in etat["constats"]:
        print(f"   {ICONE[c['niveau']]} {c['depot']:<28} {c['msg']}")
        print(f"      observable : {c['observable']}")
    n = len(etat["rouges"])
    print("   ✅ rien au rouge" if not n else f"   ⚠ {n} dépôt(s) au rouge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
