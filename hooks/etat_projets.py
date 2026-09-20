#!/usr/bin/env python3
"""etat_projets — la fiche d'état de TOUS les projets, refaite à chaque passage.

POURQUOI CE FICHIER EXISTE (2026-08-13). l'auteur a demandé « le topo de tout ce qu'il me
reste à faire ». Le premier que j'ai produit récitait des « reste à faire » de juillet
déjà réglés depuis, parce qu'il était copié des fiches au lieu d'être mesuré. Une fiche
d'état écrite à la main pourrit en trois jours ; celle-ci se REGÉNÈRE.

LE PARTAGE, ET IL EST LE CŒUR DU TRUC :

  1. MESURÉ MAINTENANT — l'état des dépôts git (dernier commit, travail non enregistré,
     commits non poussés, absence de sauvegarde hors machine). Vrai à la seconde près,
     jamais recopié, jamais périmé.

  2. DIT PAR LES FICHES — les points de reprise, lus dans `projects/**`. C'est du
     déclaratif : ça peut être périmé, et la fiche le DIT au lieu de le cacher.
     Chaque ligne porte l'âge de sa source.

  3. EN ATTENTE DE DYLAN — `projects/decisions-dylan.json`, tenu à la main par Claude quand
     une décision lui revient. Chaque entrée porte sa date : une décision qui traîne
     depuis trois semaines se voit, au lieu de se fondre dans la liste.

Ne fait AUCUN appel LLM : c'est une ronde mécanique, comme le machiniste. Gratuite,
donc elle peut tourner deux fois par jour sans jamais discuter avec le quota.

⚠️ POURQUOI MESURE ET ANNONCE SONT SÉPARÉES (2026-08-13, trouvé en regardant la sortie).
Branché naïvement sur launchd, ce script s'exécutait sans erreur et rendait « 5 dépôts »
au lieu de 22 : macOS REFUSE à un service launchd l'accès à ~/Desktop (TCC), où vivent
la plupart des dépôts de travail. Code de sortie 0, fiche écrite, 17 projets évaporés en
silence — le défaut exact de `brain status`, à six semaines d'intervalle.

Donc :
  • la MESURE tourne là où l'accès existe — dans une session Claude (hook), qui hérite
    des autorisations du terminal ;
  • l'ANNONCE de 8 h et 19 h lit la dernière mesure et DIT SON ÂGE, au lieu d'en
    fabriquer une fausse ;
  • un garde-fou refuse d'écraser une mesure complète par une mesure amputée.

Pour que la ronde mesure elle-même : donner l'Accès complet au disque à /usr/bin/python3
(Réglages Système › Confidentialité). Non requis — l'annonce reste juste sans lui.

Usage :
    python3 hooks/etat_projets.py              # mesure (si possible) + fiche + annonce
    python3 hooks/etat_projets.py --annonce    # annonce depuis la dernière mesure, n'écrit rien
    python3 hooks/etat_projets.py --notifier   # + notification macOS (launchd matin/soir)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
HOME = os.path.expanduser("~")
FICHE = os.path.join(BRAIN, "projects", "etat-des-projets.md")
# Dans projects/ et pas state/ : state/ est ignoré par git, la liste des décisions
# dues par l'auteur ne survivrait pas à un `git clone`. C'est du savoir, pas de l'état machine.
DECISIONS = os.path.join(BRAIN, "projects", "decisions-dylan.json")
CACHE = os.path.join(BRAIN, "state", "etat-projets.json")

# En dessous de cette fraction du plus grand nombre de dépôts déjà vu, la mesure est
# tenue pour AMPUTÉE (accès refusé) et n'écrase rien. 0,6 laisse passer la disparition
# légitime de quelques dépôts, jamais l'évaporation de tout un dossier.
SEUIL_AMPUTATION = 0.6

EXCLUS = ("/Library/", "/node_modules/", "/.venv", "/.codex/", "/_archive/", "/.Trash/")

# Un dépôt qui n'a pas bougé depuis plus de ça n'est plus « en pause », il dort.
JOURS_ACTIF = 7
JOURS_PAUSE = 30


def _git(repo: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def depots() -> list[dict]:
    """Tous les dépôts git de la machine, avec leur état réel."""
    try:
        r = subprocess.run(
            ["find", HOME, "-maxdepth", "7", "-name", ".git", "-not", "-path", "*/Library/*"],
            capture_output=True, text=True, timeout=120,
        )
        chemins = r.stdout.splitlines()
    except Exception:
        return []

    out = []
    aujourdhui = dt.date.today()
    for g in chemins:
        if any(x in g for x in EXCLUS):
            continue
        repo = g[: -len("/.git")]
        iso = _git(repo, "log", "-1", "--date=short", "--pretty=%ad")
        if not iso:
            continue
        try:
            jours = (aujourdhui - dt.date.fromisoformat(iso)).days
        except ValueError:
            jours = 999
        sale = len([l for l in _git(repo, "status", "--porcelain").splitlines() if l.strip()])
        non_pousse = _git(repo, "rev-list", "--count", "@{u}..HEAD")
        out.append({
            "nom": os.path.basename(repo),
            "chemin": repo.replace(HOME, "~"),
            "dernier": iso,
            "jours": jours,
            "sale": sale,
            "non_pousse": int(non_pousse) if non_pousse.isdigit() else None,
            "remote": bool(_git(repo, "remote")),
            "sujet": _git(repo, "log", "-1", "--pretty=%s")[:90],
        })
    out.sort(key=lambda d: d["jours"])
    return out


def reprises() -> list[dict]:
    """Points de reprise déclarés dans les fiches projet (déclaratif, pas mesuré)."""
    sys.path.insert(0, os.path.join(BRAIN, "hooks"))
    try:
        import brain_anticipate
        items = brain_anticipate.collect()
    except Exception:
        return []
    maintenant = dt.datetime.now().timestamp()
    for it in items:
        it["jours"] = int((maintenant - it["mtime"]) // 86400)
    return items


def decisions() -> list[dict]:
    try:
        with open(DECISIONS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    aujourdhui = dt.date.today()
    for d in data:
        try:
            d["jours"] = (aujourdhui - dt.date.fromisoformat(d.get("depuis", ""))).days
        except ValueError:
            d["jours"] = None
    return data


def alertes(reps: list[dict]) -> list[str]:
    """Ce qui mérite un geste, par ordre de gravité. Vide = rien ne cloche."""
    a = []
    for d in reps:
        if not d["remote"]:
            a.append(f"**{d['nom']}** n'a aucune sauvegarde hors machine (pas de dépôt distant)")
    for d in reps:
        if d["sale"]:
            a.append(f"**{d['nom']}** : {d['sale']} fichier(s) de travail jamais enregistrés "
                     f"(dernier commit il y a {d['jours']} j)")
    for d in reps:
        if d["non_pousse"]:
            a.append(f"**{d['nom']}** : {d['non_pousse']} commit(s) jamais poussés")
    return a


def rendre(reps, reprs, decs) -> str:
    ts = dt.datetime.now()
    actifs = [d for d in reps if d["jours"] <= JOURS_ACTIF]
    pause = [d for d in reps if JOURS_ACTIF < d["jours"] <= JOURS_PAUSE]
    dorment = [d for d in reps if d["jours"] > JOURS_PAUSE]
    al = alertes(reps)

    L = []
    L.append("---")
    L.append("name: etat-des-projets")
    L.append('description: "État de TOUS les projets, regénéré automatiquement deux fois par jour '
             "(hooks/etat_projets.py). Partie MESURÉE (dépôts git) + partie DÉCLARÉE (points de "
             'reprise des fiches, potentiellement périmés) + décisions en attente du propriétaire."')
    L.append("metadata:")
    L.append("  type: project")
    L.append("  node_type: memory")
    L.append("---")
    L.append("")
    L.append("# État des projets")
    L.append("")
    L.append(f"*Regénéré le {ts.strftime('%Y-%m-%d à %H:%M')}. Ne pas éditer à la main : "
             "le prochain passage écrase tout.*")
    L.append("")

    L.append("## En clair")
    L.append("")
    L.append("Cette page est le tableau de bord de TOUS les projets de l'auteur, refait tout seul "
             "deux fois par jour. Personne ne l'écrit à la main : le passage suivant remplace "
             "tout ce qu'on y aurait tapé.")
    L.append("")
    L.append("Elle sépare deux choses qu'il ne faut pas confondre. Ce qui est **mesuré** vient "
             "directement des dépôts de code sur la machine — du travail jamais enregistré, des "
             "enregistrements jamais envoyés ailleurs, un projet sans aucune copie hors du Mac. "
             "Ce qui est **déclaré** vient des fiches que j'écris, et vaut ce que vaut la fiche.")
    L.append("")
    L.append("On la lit pour une seule question : est-ce qu'un travail risque de disparaître, "
             "et est-ce qu'une décision attend l'auteur ?")
    L.append("")

    L.append("## ⚠️ Ce qui demande un geste")
    L.append("")
    if al:
        for x in al:
            L.append(f"- {x}")
    else:
        L.append("Rien. Tout est enregistré, poussé, sauvegardé hors machine.")
    L.append("")

    L.append("## 🙋 En attente d'une décision de l'auteur")
    L.append("")
    if decs:
        for d in decs:
            age = f" — ouvert depuis **{d['jours']} j**" if d.get("jours") is not None else ""
            L.append(f"- **{d.get('projet', '?')}** : {d.get('texte', '')}{age}")
    else:
        L.append("Rien en attente.")
    L.append("")

    L.append("## 📊 Les projets, par activité réelle")
    L.append("")
    L.append("Mesuré à l'instant sur les dépôts git — cette partie ne peut pas être périmée.")
    L.append("")
    for titre, groupe in (("Actifs (≤ 7 jours)", actifs),
                          ("En pause (8 à 30 jours)", pause),
                          ("Dormants (> 30 jours)", dorment)):
        L.append(f"### {titre} — {len(groupe)}")
        L.append("")
        if not groupe:
            L.append("*(aucun)*")
            L.append("")
            continue
        L.append("| Projet | Dernier commit | Dernier sujet |")
        L.append("|---|---|---|")
        for d in groupe:
            L.append(f"| `{d['nom']}` | {d['dernier']} ({d['jours']} j) | {d['sujet']} |")
        L.append("")

    L.append("## 🧭 Ce que les fiches disent qu'il faut reprendre")
    L.append("")
    L.append("⚠️ **Déclaratif, pas mesuré.** Ces lignes sont écrites dans les fiches ; certaines "
             "peuvent être réglées depuis. L'âge dit à quel point il faut s'en méfier — "
             "au-delà de 14 jours, re-prouver avant d'annoncer.")
    L.append("")
    for it in reprs[:12]:
        vieux = " 🕸️" if it["jours"] > 14 else ""
        L.append(f"- **{it['name']}** ({it['jours']} j{vieux}) — {it['reprise']}")
    L.append("")
    return "\n".join(L) + "\n"


def lire_cache() -> dict:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ecrire_cache(reps: list[dict], plafond: int) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"mesure_le": dt.datetime.now().isoformat(timespec="seconds"),
                   "depots": reps, "depots_max": plafond}, f, ensure_ascii=False, indent=1)


def amputee(reps: list[dict], cache: dict) -> bool:
    """La mesure a-t-elle perdu l'accès à une partie du disque ?

    Se juge sur le PLAFOND historique, pas sur la mesure précédente : deux passages
    amputés de suite feraient sinon descendre la référence jusqu'à valider la panne.
    """
    plafond = int(cache.get("depots_max") or 0)
    return plafond > 0 and len(reps) < SEUIL_AMPUTATION * plafond


def annonce(reps, reprs, decs, age=None) -> str:
    actifs = [d for d in reps if d["jours"] <= JOURS_ACTIF]
    al = alertes(reps)
    moment = "matin" if dt.datetime.now().hour < 14 else "soir"
    vu = "" if age is None else f" — mesuré {age}"
    lignes = [f"🌳 État des projets ({moment}) — {len(reps)} dépôts, "
              f"{len(actifs)} actifs cette semaine{vu}."]
    if al:
        lignes.append(f"⚠️  {len(al)} chose(s) à régler : {al[0]}")
    else:
        lignes.append("✅ Rien à régler : tout est enregistré, poussé, sauvegardé.")
    if decs:
        vieille = max(decs, key=lambda d: d.get("jours") or 0)
        lignes.append(f"🙋 {len(decs)} décision(s) en attente — la plus ancienne : "
                      f"{vieille.get('projet')} ({vieille.get('jours')} j)")
    if reprs:
        lignes.append(f"🧭 À reprendre en tête : {reprs[0]['name']}")
    lignes.append(f"📄 {FICHE.replace(HOME, '~')}")
    return "\n".join(lignes)


ANNONCE = os.path.join(BRAIN, "state", "ronde-a-annoncer.json")


def notifier(texte: str) -> None:
    """Annonce la ronde par DEUX canaux, dont un vérifiable.

    Le 2026-08-14, L'utilisateur : « un résumé ce matin ne s'est pas lancé ». Le service AVAIT tourné
    (`runs = 4, last exit code = 0`, ligne « matin » dans le log) et `osascript` avait renvoyé 0.
    Mais aucune bannière n'est jamais apparue : `osascript` lancé depuis un agent launchd poste
    ses notifications au nom de Script Editor, qui n'est même pas enregistré dans le Centre de
    notifications (0 occurrence dans `com.apple.ncprefs` après une tentative). Autrement dit le
    canal échoue en silence ET rend 0 — nouvelle instance de « un code de sortie n'est jamais
    l'observable », appliquée cette fois au canal d'annonce lui-même.

    On garde donc la bannière en best-effort, mais on dépose surtout un MARQUEUR que la
    prochaine session Claude Code affichera : le seul endroit où l'on est certain que l'utilisateur
    regarde, c'est là où il travaille.
    """
    titre = "C Brain — état des projets"
    corps = texte.split("\n")[1] if "\n" in texte else texte
    corps = corps.replace('"', "'").replace("**", "")
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{corps}" with title "{titre}"'],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass

    # Le canal qui, lui, se vérifie : un fichier, lu au démarrage de la prochaine session.
    try:
        os.makedirs(os.path.dirname(ANNONCE), exist_ok=True)
        with open(ANNONCE, "w", encoding="utf-8") as f:
            json.dump({"texte": texte, "ecrit_le": dt.datetime.now().isoformat(),
                       "annonce_le": None}, f, ensure_ascii=False, indent=2)
    except Exception as e:                      # jamais fatal : la ronde a déjà écrit sa fiche
        print(f"⚠️  marqueur d'annonce non écrit : {e}")


def _age(iso: str) -> str:
    try:
        delta = dt.datetime.now() - dt.datetime.fromisoformat(iso)
    except Exception:
        return "à une date inconnue"
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        return "il y a moins d'une heure"
    if h < 24:
        return f"il y a {h} h"
    return f"il y a {h // 24} j"


def main() -> int:
    cache = lire_cache()
    reprs, decs = reprises(), decisions()
    reps = depots()

    degrade = amputee(reps, cache)
    if degrade or "--annonce" in sys.argv:
        # On n'écrase RIEN : on parle de la dernière mesure complète, en disant son âge.
        reps = cache.get("depots", reps)
        texte = annonce(reps, reprs, decs, age=_age(cache.get("mesure_le", "")))
        if degrade:
            texte += ("\n⚠️  mesure du moment ignorée : accès disque refusé à ce service "
                      "(le Bureau n'était pas lisible). La fiche n'a pas été touchée.")
    else:
        ecrire_cache(reps, max(len(reps), int(cache.get("depots_max") or 0)))
        os.makedirs(os.path.dirname(FICHE), exist_ok=True)
        with open(FICHE, "w", encoding="utf-8") as f:
            f.write(rendre(reps, reprs, decs))
        texte = annonce(reps, reprs, decs)

    print(texte)
    if "--notifier" in sys.argv:
        notifier(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
