#!/usr/bin/env python3
"""Sabotage du banc de réinjection — il doit rougir, et rougir pour la bonne raison.

Un banc qui ne rougit jamais ne protège de rien. Celui-ci fabrique des journaux jetables où la
faute est connue d'avance, et vérifie que `banc_reinjection.py --check` la nomme.

Le cas le plus utile est le dernier : UN compactage écrit DEUX lignes de journal. Tant qu'elles
n'étaient pas regroupées, chaque coupure était comptée deux fois — c'est le défaut qui m'a fait
annoncer 66 coupures là où il y en avait 33.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTIL = os.path.join(RACINE, "tools", "conso-jetons", "banc_reinjection.py")
SEUILS = json.load(open(os.path.join(RACINE, "tools", "conso-jetons", "seuils-reinjection.json")))
N = SEUILS["fenetre_relectures"]


class Journal:
    """Écrit un journal de session jetable, un événement après l'autre."""

    def __init__(self, dossier, session):
        self.chemin = os.path.join(dossier, f"{session}.jsonl")
        self.session = session
        self.t = datetime.now(timezone.utc) - timedelta(hours=6)
        self.n = 0
        self.lignes = []

    def _horo(self):
        self.t += timedelta(seconds=30)
        return self.t.isoformat().replace("+00:00", "Z")

    def lit(self, fichier):
        """Un appel de relecture sur un fichier nommé."""
        self.n += 1
        self.lignes.append({
            "timestamp": self._horo(), "uuid": f"{self.session}-u{self.n}",
            "sessionId": self.session, "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"{self.session}-t{self.n}", "name": "Read",
                 "input": {"file_path": fichier}}]}})

    def coupure(self, doublee=True):
        """Un compactage — deux lignes, comme le vrai journal en écrit."""
        self.n += 1
        h = self._horo()
        self.lignes.append({"timestamp": h, "uuid": f"{self.session}-c{self.n}",
                            "sessionId": self.session, "type": "system",
                            "subtype": "compact_boundary"})
        if doublee:
            self.n += 1
            self.lignes.append({"timestamp": self._horo(), "uuid": f"{self.session}-s{self.n}",
                                "sessionId": self.session, "type": "user",
                                "isCompactSummary": True,
                                "message": {"role": "user", "content": "résumé"}})

    def relance(self):
        """l'auteur qui redit ce qu'il avait déjà dit."""
        self.n += 1
        self.lignes.append({"timestamp": self._horo(), "uuid": f"{self.session}-r{self.n}",
                            "sessionId": self.session, "type": "user",
                            "message": {"role": "user", "content": "non, je t'ai déjà dit ça"}})

    def ecrire(self):
        with open(self.chemin, "w") as f:
            for l in self.lignes:
                f.write(json.dumps(l) + "\n")


def session(dossier, nom, refait_apres, relances=0, doublee=True):
    """Une session : 2N relectures neuves, une coupure, puis N relectures.

    `refait_apres` dit combien des N relectures d'après visent un fichier déjà lu.
    """
    j = Journal(dossier, nom)
    for i in range(2 * N):
        j.lit(f"/avant/{nom}-{i}.md")
    j.coupure(doublee)
    for _ in range(relances):
        j.relance()
    for i in range(N):
        j.lit(f"/avant/{nom}-{i}.md" if i < refait_apres else f"/apres/{nom}-{i}.md")
    j.ecrire()
    return j


def lancer(dossier):
    r = subprocess.run([sys.executable, OUTIL, "--journaux", dossier, "--check", "--jours", "2"],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def cas(titre, construire, attendu, doit_rougir=True):
    dossier = tempfile.mkdtemp(prefix="reinj-")
    try:
        construire(dossier)
        code, sortie = lancer(dossier)
        rouge = code != 0
        if rouge != doit_rougir:
            print(f"  ❌ {titre} — attendu {'ROUGE' if doit_rougir else 'vert'}, "
                  f"obtenu {'ROUGE' if rouge else 'vert'}")
            print("     " + sortie.strip().replace("\n", "\n     ")[:600])
            return False
        if attendu and attendu not in sortie:
            print(f"  ❌ {titre} — rouge, mais sans nommer « {attendu} »")
            print("     " + sortie.strip().replace("\n", "\n     ")[:600])
            return False
        print(f"  ✅ {'ROUGE' if doit_rougir else 'vert '} {titre}")
        return True
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def sain(d):
    for k in range(6):
        session(d, f"s{k}", refait_apres=0)


def tout_refait(d):
    for k in range(6):
        session(d, f"s{k}", refait_apres=N)


def deux_reprises_ratees(d):
    # La médiane reste bonne : seules deux coupures sur cinq sont catastrophiques.
    for k in range(3):
        session(d, f"bon{k}", refait_apres=0)
    for k in range(2):
        session(d, f"rate{k}", refait_apres=N)


def relances(d):
    for k in range(6):
        session(d, f"s{k}", refait_apres=0, relances=1)


def trop_maigre(d):
    for k in range(2):
        session(d, f"s{k}", refait_apres=0)


def comptage_des_coupures(d):
    """Six coupures écrites en double doivent être comptées six fois, pas douze."""
    for k in range(6):
        session(d, f"s{k}", refait_apres=0, doublee=True)


def main():
    print("Sabotage du banc de réinjection\n")
    ok = [
        cas("journal sain — le banc doit se taire", sain, None, doit_rougir=False),
        cas("après chaque coupure, on relit tout ce qu'on avait lu",
            tout_refait, "surcoût de reprise médian"),
        cas("deux reprises ratées que la médiane ne voit pas",
            deux_reprises_ratees, "des coupures dépassent"),
        cas("l'auteur doit redire ce qu'il avait déjà dit", relances, "relance"),
        cas("trop peu de coupures — un banc muet n'est pas un banc vert",
            trop_maigre, "conclure"),
    ]
    dossier = tempfile.mkdtemp(prefix="reinj-")
    try:
        comptage_des_coupures(dossier)
        code, sortie = lancer(dossier)
        attendu = "6 coupures mesurées"
        bon = attendu in sortie
        print(f"  {'✅' if bon else '❌'} vert  six compactages écrits en double comptent six "
              f"coupures, pas douze")
        if not bon:
            print("     " + sortie.strip().replace("\n", "\n     ")[:400])
        ok.append(bon)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)

    print(f"\n{sum(ok)}/{len(ok)} cas conformes")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
