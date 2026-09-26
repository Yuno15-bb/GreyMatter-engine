
"""Verify that session identifiers stay paired with their transcript paths.

The test uses isolated HOME and BRAIN_HOME directories and copied hooks. It checks
cross-project lookup, unknown IDs, queued-session resumption, and timeline coverage.
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
AILLEURS = "-another-work-folder"
N_COURANT, N_AILLEURS, N_VOISINE = 25, 30, 12




SABOTAGES = {
    "resolveur-mono-dossier": (
        "auto_maintain.py",
        "return elsewhere[0] if elsewhere else None",
        "return None",
        "resolveur"),
    "chemin-invente": (
        "auto_maintain.py",
        "    if os.path.exists(direct):\n        return direct",
        "    if True:\n        return direct",
        "inconnu"),
    "resume-keeps-path": (
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
    sortie["found"] = am.transcript_for(sid)

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
        sortie["header"] = f.read()[:1500]

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
    """Build and run this scenario in an isolated temporary lab."""
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
    ecrire_transcript(chemins["courant"], N_COURANT, "the session that is ending")
    ecrire_transcript(chemins["ailleurs"], N_AILLEURS, "the session resumed from the queue")
    ecrire_transcript(chemins["voisine"], N_VOISINE, "a neighbor in the same project folder")

    for nom in COPIES:
        with open(os.path.join(HOOKS, nom), encoding="utf-8") as f:
            src = f.read()
        if sabotage and SABOTAGES[sabotage][0] == nom:
            _, avant, apres, _ = SABOTAGES[sabotage]
            if src.count(avant) != 1:
                raise RuntimeError(
                    "sabotage %r no longer applies to %s: the target text appears %d times. "
                    "The code changed beneath the sabotage; update it or this test proves "
                    "nothing." % (sabotage, nom, src.count(avant)))
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
    """Build and run this scenario in an isolated temporary lab."""
    with tempfile.TemporaryDirectory(prefix="paire-session-") as racine:
        env, chemins, pilote = batir_lab(racine, sabotage)
        r = subprocess.run([sys.executable, pilote, cas], env=env,
                           capture_output=True, text=True, timeout=120)
        marque = [l for l in r.stdout.splitlines() if l.startswith("<<<")]
        if not marque:
            raise RuntimeError("case %r returned no result.\n--- stdout ---\n%s\n--- stderr ---\n%s"
                               % (cas, r.stdout.strip(), r.stderr.strip()))
        return json.loads(marque[-1][3:]), chemins


def p_resolveur(res, chemins):
    if res.get("found") != chemins["ailleurs"]:
        return ("the resolver did not find a session opened from ANOTHER folder: it returned "
                "%r instead of %r. Such a session is archived and never distilled, silently."
                % (res.get("found"), chemins["ailleurs"]))
    return None


def p_inconnu(res, chemins):
    trouve = res.get("found")
    if trouve is None:
        return None
    existe = os.path.exists(trouve) if isinstance(trouve, str) else False
    return ("an unknown ID returned a path instead of None: %r (the file %s). The caller "
            "passes it to the distiller, which reads nothing without saying so."
            % (trouve, "exists" if existe else "does not exist"))


def p_reprise(res, chemins):
    if not res:
        return "resumption launched no agent: the queued session was never resumed."
    if res.get("sid") != SID_AILLEURS:
        return "the resumed session is not the one in the queue: ID %r instead of %r." % (
            res.get("sid"), SID_AILLEURS)
    if res.get("tp") != chemins["ailleurs"]:
        what = ("the ending session's transcript" if res.get("tp") == chemins["courant"]
                else "an unrelated path")
        return ("resumption carried %s under the RESUMED session's ID: %r instead of %r. "
                "The distiller receives an inconsistent pair: notes attributed to a session "
                "they do not describe." % (what, res.get("tp"), chemins["ailleurs"]))
    if res.get("n") != N_AILLEURS:
        return "the message count did not follow the ID: %r instead of %d." % (
            res.get("n"), N_AILLEURS)
    return None


def p_index(res, chemins):
    entete = res.get("header", "")
    if "lossless for all sessions" in entete:
        return "the index claims to include all sessions while scanning only one folder."
    if "does NOT read" not in entete:
        return "the index does not report that transcripts from another folder are omitted."
    attendu = "`%s` (%d)" % (AILLEURS, 2)
    if attendu not in entete:
        return "the index reports the wrong blind spot count; expected %s in its header." % attendu
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
                print("   ✅ %-24s → %s fails as expected" % (nom, cas))
        if muets:
            print("⛔ a sabotage did not make the test fail; this test does not enforce its target:")
            for nom, fichier, cas in muets:
                print("     · %s (%s) — case %r still passes" % (nom, fichier, cas))
            return 1
        if not check:
            print("✅ all %d sabotages make the test fail" % len(SABOTAGES))
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
        print("⛔ a session ID became separated from its transcript:")
        for cas, faute in echecs:
            print("     · %s — %s" % (cas, faute))
        print("   The path follows the ID, and a failed lookup returns None rather than a fake path.")
        return 1

    if not check:
        print("✅ session IDs stay paired with transcripts — tested %d properties in an "
              "isolated home with two project folders" % len(CAS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
