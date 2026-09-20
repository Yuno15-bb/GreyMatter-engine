#!/usr/bin/env python3
"""paire_session_transcript — un identifiant de session et son transcript voyagent ENSEMBLE.

POURQUOI CE BANC EXISTE (mesuré le 2026-09-20, entrée C7 de C bis)
    Le dossier qui porte les transcripts est nommé d'après le répertoire d'où la session a
    été OUVERTE, jamais d'après `$HOME`. Mesuré ce jour : `~/.claude/projects/` porte HUIT
    dossiers et 733 transcripts, et celui que `expanduser("~")` reconstruit n'en contient
    que 155. Reconstruire ce chemin, c'est donc viser juste dans le cas courant et rater
    en silence partout ailleurs — sans code d'erreur, sans refus, sans trace.

    Deux défauts de cette famille ont été payés ici. Le premier en août 2026 : le compteur
    de messages retombait à 0 pour une session ouverte ailleurs, donc sous le seuil de
    distillation, donc jamais distillée — 87 sessions de 20 à 221 messages perdues, retrouvées
    par un balayage rétrospectif. Le second, resté vivant jusqu'au 2026-09-20 : quand la file
    d'attente n'est pas vide, la maintenance reprend une AUTRE session que celle qui se
    termine, et elle transportait le chemin de la session EN COURS sous l'identifiant de la
    session REPRISE. Le distillateur recevait une paire incohérente : des fiches attribuées
    à une session qu'elles ne décrivent pas, et la session reprise jamais lue.

    Ce second défaut est LATENT — il ne sort que la file pleine — et c'est exactement
    pourquoi personne ne l'avait vu. Un défaut latent reste un défaut : il attend.

CE QUE CE BANC VÉRIFIE — quatre propriétés, jouées pour de vrai dans un faux dossier personnel
    Chaque cas tourne dans un processus séparé, avec `HOME` et `BRAIN_HOME` pointés sur un
    laboratoire jetable AVANT l'import, et sur une COPIE des trois hooks concernés. Le
    laboratoire porte deux dossiers de projet : celui que `$HOME` reconstruit, et un autre.

      1. « resolveur »  — le résolveur retrouve une session dont le transcript vit dans un
                          AUTRE dossier que celui dérivé de `$HOME` ;
      2. « inconnu »    — un identifiant inconnu rend `None`, jamais un chemin fabriqué :
                          « je n'ai pas trouvé » et « voilà un fichier » sont deux réponses
                          différentes, et la seconde fait lire le vide sans le dire ;
      3. « reprise »    — la reprise d'une session en file appareille l'identifiant repris
                          avec SON propre transcript et SON propre compte de messages,
                          jamais avec ceux de la session qui se termine ;
      4. « index »      — l'index des sessions dit ce qu'il NE lit PAS, avec le compte et le
                          nom des dossiers laissés dehors, au lieu de se déclarer complet.

CE QU'IL NE VÉRIFIE PAS
    Que le distillateur fasse quelque chose de juste avec la paire : `launch_agent` est
    remplacé par un mouchard, on regarde ce qu'on lui tend, pas ce qu'il en fait. Il ne
    vérifie pas non plus les quatre autres endroits qui reconstruisent encore le chemin
    mono-dossier (`brain_audit.py`, `brain_guard.py`, `robots_permissions.py`, et le balayage
    de `rebuild_timeline`) : trois d'entre eux sont des diagnostics, le quatrième est
    volontairement restreint — élargir son balayage serait une RÉGRESSION, puisque 371 des
    376 transcrits du plus gros dossier sont des sessions de maintenance automatique, tenues
    hors de la timeline humaine depuis le 2026-08-03 (garde ANTI-RÉCURSION dans `main`).
    Enfin il ne mesure rien sur la vraie machine : il joue un laboratoire, pas le Mac — et
    ce laboratoire est fondé sur `$HOME`, donc exposé à la borne D2 de C bis, qui dit qu'un bac
    à sable bâti sur `$HOME` seul mesure encore partiellement l'hôte (voir la leçon
    `home-isole-n-est-pas-un-environnement-isole`). Ici la surface d'hôte restante a été réduite
    à la main : les trois hooks tournent sur une COPIE, `BRAIN_HOME` est détourné lui aussi, et
    les deux fonctions qui sortiraient du bac — `launch_agent` et `inbox_has_work` — sont
    remplacées. Ce qui n'est pas prouvé, c'est qu'il n'en reste AUCUNE.

LA RECHERCHE QUI A ÉCHOUÉ AVANT D'ÉCRIRE CE BANC
    Grepé `claude/projects` dans `hooks/`, `tools/*.py` et `tests/*.py` → cinq sites
    reconstruisent le même chemin mono-dossier, aucun résolveur transverse n'existait. Lu
    `tests/reprises_cle_stable.py` et `tests/contrat_distillateur.py` → hors sujet : l'un
    verrouille la clé de la file d'attente, l'autre le contrat de sortie du distillateur ;
    ni l'un ni l'autre n'apparie un identifiant et un fichier.
"""
import json
import os
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
HOOKS = os.path.join(BRAIN, "hooks")
COPIES = ("auto_maintain.py", "brain_guard.py", "archive_session.py")

SID_COURANT = "11111111-1111-4111-8111-111111111111"
SID_AILLEURS = "22222222-2222-4222-8222-222222222222"
SID_VOISINE = "44444444-4444-4444-8444-444444444444"
SID_INCONNU = "33333333-3333-4333-8333-333333333333"
AILLEURS = "-un-autre-dossier-de-travail"
N_COURANT, N_AILLEURS, N_VOISINE = 25, 30, 12

# Chaque sabotage : (fichier, texte à remplacer, remplacement, cas qui DOIT rougir).
# Le texte de départ doit apparaître une fois et une seule — sinon le sabotage ne
# s'applique plus, et un sabotage qui ne s'applique plus est un trou, pas un succès.
SABOTAGES = {
    "resolveur-mono-dossier": (
        "auto_maintain.py",
        "return ailleurs[0] if ailleurs else None",
        "return None",
        "resolveur"),
    "chemin-invente": (
        "auto_maintain.py",
        "    if os.path.exists(direct):\n        return direct",
        "    if True:\n        return direct",
        "inconnu"),
    "reprise-garde-le-chemin": (
        "auto_maintain.py",
        "            tp = transcript_for(sid)\n",
        "",
        "reprise"),
    "index-muet": (
        "archive_session.py",
        "    hors = transcripts_hors_index()",
        "    hors = []",
        "index"),
}

PILOTE = '''import io, json, os, sys
sys.path.insert(0, os.environ["LAB_HOOKS"])
cas = sys.argv[1]
sortie = {}

if cas in ("resolveur", "inconnu"):
    import auto_maintain as am
    sid = os.environ["SID_AILLEURS"] if cas == "resolveur" else os.environ["SID_INCONNU"]
    sortie["trouve"] = am.transcript_for(sid)

elif cas == "reprise":
    import brain_guard as guard
    import auto_maintain as am
    guard.enqueue(os.environ["SID_AILLEURS"])
    recu = {}
    am.launch_agent = lambda sid, n, to_distill, transcript_path=None: recu.update(
        sid=sid, n=n, to_distill=to_distill, tp=transcript_path)
    am.inbox_has_work = lambda: False
    am.shutil.which = lambda nom: "/bin/echo"
    sys.stdin = io.StringIO(json.dumps({"session_id": os.environ["SID_COURANT"],
                                        "transcript_path": os.environ["TP_COURANT"]}))
    am.main()
    sortie = recu

elif cas == "index":
    import archive_session as asn
    asn.rebuild_timeline()
    with open(os.path.join(asn.SESSIONS, "TIMELINE.md"), encoding="utf-8") as f:
        sortie["entete"] = f.read()[:1500]

print("<<<" + json.dumps(sortie))
'''


def ecrire_transcript(chemin, n, sujet):
    lignes = [json.dumps({"type": "user", "timestamp": "2026-09-20T09:00:00.000Z",
                          "message": {"role": "user", "content": sujet}})]
    for i in range(n - 1):
        role = "assistant" if i % 2 == 0 else "user"
        lignes.append(json.dumps({"type": role, "timestamp": "2026-09-20T09:%02d:00.000Z" % (i + 1),
                                  "message": {"role": role, "content": "message %d" % i}}))
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")


def batir_lab(racine, sabotage=None):
    """Monte le laboratoire. Rend (env, chemins) ou lève RuntimeError si un sabotage
    déclaré ne s'applique plus au code réel."""
    home = os.path.join(racine, "home")
    brain = os.path.join(racine, "brain")
    hooks = os.path.join(racine, "hooks")
    projets = os.path.join(home, ".claude", "projects")
    d_home = os.path.join(projets, home.replace(os.sep, "-"))
    d_ailleurs = os.path.join(projets, AILLEURS)
    for d in (d_home, d_ailleurs, hooks, os.path.join(brain, "sessions", "archive"),
              os.path.join(brain, "state")):
        os.makedirs(d, exist_ok=True)

    chemins = {"courant": os.path.join(d_home, SID_COURANT + ".jsonl"),
               "ailleurs": os.path.join(d_ailleurs, SID_AILLEURS + ".jsonl"),
               "voisine": os.path.join(d_ailleurs, SID_VOISINE + ".jsonl"),
               "invente": os.path.join(d_home, SID_INCONNU + ".jsonl"),
               "timeline": os.path.join(brain, "sessions", "TIMELINE.md")}
    ecrire_transcript(chemins["courant"], N_COURANT, "la session qui se termine")
    ecrire_transcript(chemins["ailleurs"], N_AILLEURS, "la session reprise dans la file")
    ecrire_transcript(chemins["voisine"], N_VOISINE, "une voisine du meme dossier")

    for nom in COPIES:
        with open(os.path.join(HOOKS, nom), encoding="utf-8") as f:
            src = f.read()
        if sabotage and SABOTAGES[sabotage][0] == nom:
            _, avant, apres, _ = SABOTAGES[sabotage]
            if src.count(avant) != 1:
                raise RuntimeError(
                    "le sabotage « %s » ne s'applique plus à %s : le texte visé y apparaît "
                    "%d fois. Le code a bougé sous le sabotage — le réécrire, ou ce banc ne "
                    "prouve plus rien." % (sabotage, nom, src.count(avant)))
            src = src.replace(avant, apres)
        with open(os.path.join(hooks, nom), "w", encoding="utf-8") as f:
            f.write(src)

    pilote = os.path.join(racine, "pilote.py")
    with open(pilote, "w", encoding="utf-8") as f:
        f.write(PILOTE)

    env = dict(os.environ)
    env.update(HOME=home, BRAIN_HOME=brain, LAB_HOOKS=hooks,
               SID_COURANT=SID_COURANT, SID_AILLEURS=SID_AILLEURS, SID_INCONNU=SID_INCONNU,
               TP_COURANT=chemins["courant"])
    env.pop("CLAUDE_BRAIN_GARDENING", None)
    return env, chemins, pilote


def jouer(cas, sabotage=None):
    """Monte un laboratoire neuf, y joue un cas, rend (sortie, chemins)."""
    with tempfile.TemporaryDirectory(prefix="paire-session-") as racine:
        env, chemins, pilote = batir_lab(racine, sabotage)
        r = subprocess.run([sys.executable, pilote, cas], env=env,
                           capture_output=True, text=True, timeout=120)
        marque = [l for l in r.stdout.splitlines() if l.startswith("<<<")]
        if not marque:
            raise RuntimeError("le cas « %s » n'a rien rendu.\n--- sortie ---\n%s\n--- erreurs ---\n%s"
                               % (cas, r.stdout.strip(), r.stderr.strip()))
        return json.loads(marque[-1][3:]), chemins


def p_resolveur(res, chemins):
    if res.get("trouve") != chemins["ailleurs"]:
        return ("le résolveur n'a pas retrouvé une session ouverte depuis un AUTRE dossier : "
                "il rend %r au lieu de %r. Une telle session est archivée puis jamais "
                "distillée, en silence." % (res.get("trouve"), chemins["ailleurs"]))
    return None


def p_inconnu(res, chemins):
    trouve = res.get("trouve")
    if trouve is None:
        return None
    existe = os.path.exists(trouve) if isinstance(trouve, str) else False
    return ("un identifiant inconnu a rendu un chemin au lieu de « je n'ai pas trouvé » : %r "
            "(ce fichier %s). L'appelant le passe tel quel au distillateur, qui lit alors le "
            "vide sans le dire." % (trouve, "existe" if existe else "n'existe pas"))


def p_reprise(res, chemins):
    if not res:
        return ("la reprise n'a lancé aucun agent : la session en file n'a pas été reprise du "
                "tout, donc la paire identifiant/transcript n'a jamais été formée.")
    if res.get("sid") != SID_AILLEURS:
        return ("la session reprise n'est pas celle qui était en file : identifiant %r au lieu "
                "de %r." % (res.get("sid"), SID_AILLEURS))
    if res.get("tp") != chemins["ailleurs"]:
        quoi = ("le transcript de la session qui se TERMINE"
                if res.get("tp") == chemins["courant"] else "un chemin étranger")
        return ("la reprise a transporté %s sous l'identifiant de la session REPRISE : %r au "
                "lieu de %r. Le distillateur reçoit une paire incohérente — des fiches "
                "attribuées à une session qu'elles ne décrivent pas." % (quoi, res.get("tp"),
                                                                        chemins["ailleurs"]))
    if res.get("n") != N_AILLEURS:
        return ("le compte de messages n'a pas suivi l'identifiant : %r au lieu de %d, le "
                "nombre de messages de la session reprise." % (res.get("n"), N_AILLEURS))
    return None


def p_index(res, chemins):
    entete = res.get("entete", "")
    if "sans perte de l'intégralité" in entete:
        return ("l'index se déclare complet (« sans perte de l'intégralité de nos sessions ») "
                "alors qu'il ne balaie qu'un dossier sur plusieurs.")
    if "ne lit PAS" not in entete:
        return ("l'index ne dit pas ce qu'il laisse dehors : un dossier entier de transcrits "
                "n'est pas lu et rien ne le signale.")
    attendu = "`%s` (%d)" % (AILLEURS, 2)
    if attendu not in entete:
        return ("l'index annonce un angle mort sans le chiffrer correctement : « %s » attendu, "
                "absent de l'en-tête." % attendu)
    return None


CAS = (("resolveur", p_resolveur), ("inconnu", p_inconnu),
       ("reprise", p_reprise), ("index", p_index))


def main():
    check = "--check" in sys.argv
    mode_sabotages = "--sabotages" in sys.argv

    if mode_sabotages:
        muets = []
        for nom, (fichier, _, _, cas) in sorted(SABOTAGES.items()):
            verdict = dict(CAS)[cas]
            try:
                res, chemins = jouer(cas, sabotage=nom)
                echec = verdict(res, chemins)
            except RuntimeError as e:
                echec = str(e)
            if echec is None:
                muets.append((nom, fichier, cas))
            elif not check:
                print("   ✅ %-24s → %s rougit" % (nom, cas))
        if muets:
            print("⛔ un sabotage n'a pas fait rougir le banc — la propriété qu'il vise n'est "
                  "donc pas réellement tenue par ce banc :")
            for nom, fichier, cas in muets:
                print("     · %s (%s) — le cas « %s » reste vert" % (nom, fichier, cas))
            return 1
        if not check:
            print("✅ les %d sabotages rougissent" % len(SABOTAGES))
        return 0

    echecs = []
    for cas, verdict in CAS:
        try:
            res, chemins = jouer(cas)
            faute = verdict(res, chemins)
        except RuntimeError as e:
            faute = str(e)
        if faute:
            echecs.append((cas, faute))

    if echecs:
        print("⛔ un identifiant de session et son transcript se sont séparés :")
        for cas, faute in echecs:
            print("     · %s — %s" % (cas, faute))
        print("   La règle : le chemin suit l'identifiant, et un échec de résolution se dit "
              "(None), il ne se déguise pas en chemin.")
        return 1

    if not check:
        print("✅ identifiant et transcript restent appariés — %d propriétés jouées dans un "
              "faux dossier personnel à deux dossiers de projet" % len(CAS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
