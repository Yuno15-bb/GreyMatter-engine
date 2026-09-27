#!/usr/bin/env python3

























import difflib
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "hooks"))
from brain_racine import brain_root
BRAIN = Path(brain_root(__file__))
CARTE = ICI.parent / "planet" # i18n-ok
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8767





STATIQUES = {".html", ".css", ".js", ".woff2", ".ico"}




IMAGES_OUVERTES = {"/logo/marque-carre.png", "/logo/marque-mot.png"}
FENETRE_SESSION_S = 10 * 60
CODE_P = BRAIN / "state" / "gmtr-code"
ITERATIONS = 240_000
ESSAIS_MAX, BLOCAGE_S = 5, 30
SESSIONS = set()
ECHECS = {"n": 0, "jusqua": 0.0}


def empreinte(code, sel=None):
    sel = sel or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(sel), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${sel}${h}"


def code_juste(code):
    try:
        _, it, sel, attendu = CODE_P.read_text().strip().split("$")
    except (OSError, ValueError):
        return None
    h = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(sel), int(it)).hex()
    return hmac.compare_digest(h, attendu)


def amorce():

    debut = time.perf_counter()
    lignes = []
    cibles = [
        ("planet/graph.json", "trunk map"),
        ("planet/textes.json", "note texts"),
        ("planet/index.html", "map engine"),
        ("state/doctor.json", "doctor checks"),
        ("state/status.json", "session state"),
        ("state/note-writes.jsonl", "write journal"),
        ("state/coactivation.json", "zone heat"),
        ("agents", "declared agents"),
        ("state/FREEZE", "robot freeze"),
        ("gmtr/fonts", "fonts"),
        ("state/gmtr-code", "access lock"),
    ]
    for rel, role in cibles:
        p = ICI / "fonts" if rel == "gmtr/fonts" else CARTE / "index.html" if rel == "planet/index.html" else BRAIN / rel # i18n-ok
        t = time.perf_counter()
        try:
            if p.is_dir():
                fichiers = [x for x in p.iterdir() if x.is_file() and not x.name.startswith(".")]
                taille = sum(x.stat().st_size for x in fichiers)
                if rel == "agents":
                    detail = f"{len([x for x in fichiers if x.suffix == '.md' and x.stem != 'readme'])} agents"
                else:
                    detail = f"{len(fichiers)} files"
            else:
                with open(p, "rb") as f:
                    taille = len(f.read())
                detail = None
            present = True
        except OSError:
            taille, detail, present = None, None, False
        lignes.append({
            "chemin": rel, "role": role, "present": present, "octets": taille, "detail": detail,
            "lu_ms": round((time.perf_counter() - t) * 1000, 2),
            "t": round(time.perf_counter() - debut, 4),
        })
    return {
        "programme": "GMTR", "ecoute": f"127.0.0.1:{PORT}", "pid": os.getpid(),
        "python": sys.version.split()[0], "commit": _commit(), "lignes": lignes,
        "duree_ms": round((time.perf_counter() - debut) * 1000, 2),
    }


def _commit():
    g = _json(BRAIN / "planet" / "graph.json") or {}
    return (g.get("head") or "")[:7] or None


def _releve(p):
    try:
        return int(p.stat().st_mtime)
    except OSError:
        return None


def _json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None






AGENTS_NOMS = [
    ("architect",   "HUGINN"),
    ("distiller", "MUNINN"),
    ("synthesizer", "MIMIR"),
    ("archivist",   "URD"),
    ("gardener",    "VERDANDI"),
    ("challenger",   "RATATOSK"),
    ("machinist",   "BROKKR"),
    ("mechanic",   "EITRI"),
]



AGENT_PERDU_S = 1200


def agents():










    chemin = os.environ.get("GMTR_AGENTS_JOURNAL")
    source = Path(chemin) if chemin else (BRAIN / "state" / "agents.jsonl")
    dernier, passages = {}, {}
    try:
        with source.open(encoding="utf-8", errors="replace") as f:
            for ligne in f:
                try:
                    o = json.loads(ligne)
                except ValueError:
                    continue
                nom = o.get("agent")
                if not nom:
                    continue




                if o.get("phase") == "start":
                    dernier[nom] = o
                else:
                    base = dernier.get(nom) or {}
                    dernier[nom] = {**base, **o} if base.get("phase") == "start" else o
                    passages[nom] = passages.get(nom, 0) + 1
    except OSError:
        pass
    maintenant = time.time()
    sortie = []
    for i, (cle, nom) in enumerate(AGENTS_NOMS, start=1):
        d = dernier.get(cle)
        if d is None:
            sortie.append({"case": i, "cle": cle, "nom": nom, "etat": "never-seen",
                           "passages": 0})
            continue
        age = maintenant - (d.get("ts") or maintenant)
        if d.get("phase") == "start":
            etat_ = "working" if age < AGENT_PERDU_S else "stale"
        else:
            etat_ = "idle"
        sortie.append({"case": i, "cle": cle, "nom": nom, "etat": etat_,
                       "depuis_s": int(age), "passages": passages.get(cle, 0),
                       "activite": d.get("activity"), "raison": d.get("reason"),
                       "verdict": d.get("verdict"), "duree_s": d.get("duration_s"),
                       "cout_usd": d.get("cost_usd")})
    actifs = [a for a in sortie if a["etat"] == "working"]
    return {"ts": int(maintenant), "agents": sortie,

            "delibere": bool(actifs), "source": str(source)}


def etat():
    maintenant = int(time.time())
    graphe_p = BRAIN / "planet" / "graph.json"
    docteur_p = BRAIN / "state" / "doctor.json"
    statut_p = BRAIN / "state" / "status.json"
    ecritures_p = BRAIN / "state" / "note-writes.jsonl"
    gel_p = BRAIN / "state" / "FREEZE"
    agents_d = BRAIN / "agents"

    g = _json(graphe_p) or {}
    d = _json(docteur_p)
    st = _json(statut_p)

    derniere, sur_24h = None, None
    try:
        lignes = ecritures_p.read_text(encoding="utf-8").splitlines()
        sur_24h = 0
        for l in lignes:
            try:
                e = json.loads(l)
            except ValueError:
                continue
            ts = e.get("ts")
            if not isinstance(ts, (int, float)):
                continue
            if ts >= maintenant - 86400:
                sur_24h += 1
            if derniere is None or ts >= derniere["ts"]:
                derniere = {"ts": int(ts), "fiche": Path(e.get("path", "")).stem}
    except OSError:
        pass

    try:
        agents = sorted(p.stem for p in agents_d.glob("*.md") if p.stem != "readme")
    except OSError:
        agents = None

    controles = None
    if isinstance(d, dict):
        controles = [
            {"nom": k, "defauts": v}
            for k, v in d.items()
            if isinstance(v, list)
        ]

    session = None
    if isinstance(st, dict) and isinstance(st.get("ts"), (int, float)):
        recente = maintenant - st["ts"] < FENETRE_SESSION_S



        session = {"etat": st.get("state") if recente else "idle", "ts": int(st["ts"]),
                   "activite": st.get("activity") if recente else None,
                   "detail": st.get("detail") if recente else None,
                   "qui": st.get("source") if recente else None}

    return {
        "maintenant": maintenant,
        "tronc": {
            "fiches": (g.get("counts") or {}).get("nodes"),
            "liens": (g.get("counts") or {}).get("links"),
            "regions": len(g["domains"]) if isinstance(g.get("domains"), list) else None,
            "noms_regions": g.get("domains") if isinstance(g.get("domains"), list) else [],
            "commit": (g.get("head") or "")[:7] or None,
            "source": "planet/graph.json",
            "releve": _releve(graphe_p),
        },
        "sante": {
            "ok": d.get("ok") if isinstance(d, dict) else None,
            "alertes": d.get("total") if isinstance(d, dict) else None,
            "controles": controles,
            "source": "state/doctor.json",
            "releve": _releve(docteur_p),
        },
        "agents": {"noms": agents, "source": "agents/"},
        "gel": {"pose": gel_p.exists(), "depuis": _releve(gel_p), "source": "state/FREEZE"},
        "ecritures": {
            "derniere": derniere,
            "sur_24h": sur_24h,
            "source": "state/note-writes.jsonl",
        },
        "session": dict(session or {"etat": None}, source="state/status.json"),
    }


def _queue(p, n, _plafond=8 << 20):












    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            taille = f.tell()
            fen = min(max(200 * n, 1 << 16), _plafond)
            while True:
                debut = max(0, taille - fen)
                f.seek(debut)
                brut = f.read(taille - debut).splitlines()
                if debut > 0:
                    brut = brut[1:]
                if len(brut) >= n or debut == 0 or fen >= _plafond:
                    break
                fen = min(fen * 4, _plafond)
            brut = brut[-n:]
    except OSError:
        return []
    out = []
    for l in brut:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out






















COMPANION = Path(os.environ["GMTR_COMPANION"]).expanduser() if os.environ.get("GMTR_COMPANION") else None
_VU = {}
_DISQUE = []
_SCAN = {"t": 0.0}
_EXCLUS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
_SURVEILLES = {".md", ".js", ".mjs", ".css", ".html", ".py", ".sh", ".ts", ".tsx", ".swift"}
_TROP_GROS = 400_000
_NOMS = {"t": 0.0, "par_sid": {}}


def _nom_session(sid, projet=None):
    if time.time() - _NOMS["t"] > 30:
        noms = {}
        try:
            for f in os.listdir(BRAIN / "sessions" / "archive"):
                morceaux = f[:-3].split("_") if f.endswith(".md") else []
                if len(morceaux) >= 3:
                    noms[morceaux[-1][:8]] = morceaux[-2]
        except OSError:
            pass
        _NOMS.update(t=time.time(), par_sid=noms)
    sid = sid or ""
    nom = _NOMS["par_sid"].get(sid[:8]) or projet or "session"
    return f"{nom}·{sid[:4]}" if sid else nom


_DATES = {}


def _version_commitee(rel):

    try:




        r = subprocess.run(["git", "-C", str(BRAIN), "show", f"HEAD:./{rel}"], capture_output=True, timeout=3)
        return r.stdout.decode("utf-8", "replace").splitlines() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _scruter_disque():






    if time.time() - _SCAN["t"] < 1.5:
        return
    premier = _SCAN["t"] == 0.0
    _SCAN["t"] = time.time()
    for racine, dossiers, fichiers in os.walk(BRAIN):
        dossiers[:] = [d for d in dossiers if d not in _EXCLUS]
        for f in fichiers:
            if os.path.splitext(f)[1] not in _SURVEILLES:
                continue
            chemin = os.path.join(racine, f)
            try:
                st = os.stat(chemin)
            except OSError:
                continue
            if st.st_size > _TROP_GROS:
                continue
            rel = os.path.relpath(chemin, BRAIN)
            ancienne = _DATES.get(rel)
            _DATES[rel] = st.st_mtime
            if premier or ancienne == st.st_mtime:
                continue
            try:
                lignes = Path(chemin).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            vu = _VU.pop(rel, None)
            if vu is not None:
                avant, base = vu, "previous"
            elif ancienne is None:
                avant, base = [], "new file"
            else:
                avant = _version_commitee(rel)
                base = "since last commit" if avant is not None else "new file"
                avant = avant or [] # i18n-ok
            _VU[rel] = lignes
            while len(_VU) > 300:
                _VU.pop(next(iter(_VU)))
            diff = [l for l in difflib.unified_diff(avant, lignes, n=1, lineterm="")][2:]
            if diff:
                _DISQUE.append({"ts": st.st_mtime, "chemin": rel, "fichier": chemin, "diff": diff[:120],
                                "ajoutees": sum(1 for l in diff if l.startswith("+")),
                                "retirees": sum(1 for l in diff if l.startswith("-")),
                                "outil": "disk" if base == "previous" else f"disk · {base}", "qui": "writer not logged"})
    del _DISQUE[:-200]


def ecrit(depuis=0.0, n=40):
    maintenant = time.time()
    _scruter_disque()
    evts = []
    try:
        journaux = sorted(COMPANION.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:12] if COMPANION else []
    except OSError:
        journaux = []
    for f in journaux:
        for e in _queue(f, 60):
            if e.get("type") != "diff" or not isinstance(e.get("diff"), list):
                continue
            ts = float(e.get("ts") or 0)
            if ts <= depuis:
                continue
            evts.append({"ts": ts, "chemin": e.get("rel") or e.get("file"), "fichier": e.get("file"),







                         "diff": [str(l)[:220] for l in e["diff"][:300]],
                         "coupees": max(0, len(e["diff"]) - 300),
                         "ajoutees": e.get("added"), "retirees": e.get("removed"), "outil": (e.get("tool") or "").lower(),
                         "qui": _nom_session(f.stem)})

    for d in _DISQUE:
        if d["ts"] <= depuis:
            continue
        if any(x["fichier"] == d["fichier"] and abs(x["ts"] - d["ts"]) < 15 for x in evts):
            continue
        evts.append(dict(d))
    evts.sort(key=lambda e: e["ts"])
    evts = evts[-n:]
    for e in evts:
        e.pop("fichier", None)
    return {"maintenant": maintenant, "evenements": evts,
            "source": "GMTR_COMPANION diffs (when configured) and trunk file changes"}


def flux(n=160):

    maintenant = int(time.time())
    evts = []
    for e in _queue(BRAIN / "state" / "note-writes.jsonl", n):
        evts.append({"ts": e.get("ts"), "type": "write", "session": _nom_session(e.get("sid")), "cible": e.get("path"),
                     "detail": (e.get("tool") or "").lower(), "note": e.get("attribution")})
    for e in _queue(BRAIN / "state" / "read_log.jsonl", n):
        evts.append({"ts": e.get("ts"), "type": "read", "session": _nom_session(e.get("sid")), "cible": e.get("path"),
                     "detail": "", "note": None})
    for e in _queue(BRAIN / "state" / "recall_log.jsonl", n):
        score = e.get("score")
        evts.append({"ts": e.get("ts"), "type": "recall", "session": _nom_session(e.get("sid")), "cible": e.get("path"),
                     "detail": f"{score:.1f}" if isinstance(score, (int, float)) else "", "note": e.get("moteur")})
    for e in _queue(BRAIN / "state" / "git-journal.jsonl", n):


        if e.get("event") != "released" or not e.get("head_moved"):
            continue
        fichiers = e.get("committed_files") or []
        perimetre = e.get("scope") or []
        evts.append({"ts": e.get("ts"), "type": "commit", "session": str(e.get("pid") or "")[:6],
                     "cible": ", ".join(perimetre) if isinstance(perimetre, list) else str(perimetre),
                     "detail": (e.get("head_after") or "")[:7],
                     "note": f"{len(fichiers)} files · {e.get('operation') or ''}".strip(" ·")})
    evts = [e for e in evts if isinstance(e["ts"], (int, float))]
    evts.sort(key=lambda e: e["ts"], reverse=True)
    compte = {}
    for e in evts:
        if e["ts"] >= maintenant - 86400:
            compte[e["type"]] = compte.get(e["type"], 0) + 1
    return {"maintenant": maintenant, "evenements": evts[:n], "sur_24h": compte,
            "sources": ["state/note-writes.jsonl", "state/read_log.jsonl", "state/recall_log.jsonl", "state/git-journal.jsonl"]}


class Guichet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):






        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _envoyer(self, corps, type_, statut=200, cookie=None):
        self.send_response(statut)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _session(self):
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            cle, _, val = morceau.strip().partition("=")
            if cle == "gmtr_session" and val in SESSIONS:
                return True
        return False

    def do_POST(self):
        if self.path != "/deverrouiller":
            return self.send_error(404)
        maintenant = time.time()
        if maintenant < ECHECS["jusqua"]:
            corps = {"ok": False, "raison": "bloque", "attendre_s": int(ECHECS["jusqua"] - maintenant) + 1}
            return self._envoyer(json.dumps(corps).encode(), "application/json", 429)
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 256)
            code = str(json.loads(self.rfile.read(n) or b"{}").get("code", ""))
        except (ValueError, AttributeError):
            code = ""
        juste = code_juste(code)
        if juste is None:
            return self._envoyer(json.dumps({"ok": False, "raison": "non_arme"}).encode(), "application/json", 503)
        if not juste:
            ECHECS["n"] += 1
            restants = ESSAIS_MAX - ECHECS["n"]
            if restants <= 0:
                ECHECS.update(n=0, jusqua=maintenant + BLOCAGE_S)
            corps = {"ok": False, "raison": "refuse", "restants": max(restants, 0), "attendre_s": BLOCAGE_S if restants <= 0 else 0}
            return self._envoyer(json.dumps(corps).encode(), "application/json", 401)
        ECHECS.update(n=0, jusqua=0.0)
        jeton = secrets.token_urlsafe(32)
        SESSIONS.add(jeton)
        cookie = f"gmtr_session={jeton}; HttpOnly; SameSite=Strict; Path=/"
        return self._envoyer(json.dumps({"ok": True}).encode(), "application/json", 200, cookie)

    def do_GET(self):
        chemin = unquote(self.path.split("?", 1)[0])
        if chemin == "/amorce.json":
            return self._envoyer(json.dumps(amorce(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if (chemin in ("/etat.json", "/flux.json", "/ecrit.json", "/agents.json") or chemin.startswith(("/carte", "/panneau", "/flux/"))) and not self._session():
            if chemin.startswith(("/carte", "/panneau", "/flux/")):
                self.send_response(302)
                self.send_header("Location", "/")
                return self.end_headers()
            return self._envoyer(b'{"verrouille": true}', "application/json", 401)
        if chemin == "/flux.json":
            return self._envoyer(json.dumps(flux(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if chemin == "/ecrit.json":
            try:
                depuis = float((self.path.split("depuis=", 1) + ["0"])[1].split("&")[0] or 0) # i18n-ok
            except ValueError:
                depuis = 0.0
            return self._envoyer(json.dumps(ecrit(depuis), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if chemin == "/agents.json":
            return self._envoyer(json.dumps(agents(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if chemin == "/etat.json":
            return self._envoyer(json.dumps(etat(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if chemin == "/panneau":


            self.send_response(301)
            self.send_header("Location", "/panneau/")
            return self.end_headers()
        if chemin == "/carte":
            self.send_response(301)
            self.send_header("Location", "/carte/")
            return self.end_headers()
        if chemin in ("/carte/", "/carte/index.html") and (ICI / "carte" / "index.html").is_file(): # i18n-ok






            racine, relatif = ICI / "carte", "index.html" # i18n-ok
        elif chemin.startswith("/carte/gmtr-carte.") and Path(chemin).suffix in (".js", ".css"): # i18n-ok

            racine, relatif = ICI / "carte", chemin[len("/carte/"):] # i18n-ok
        elif chemin.startswith("/carte/"):
            relatif = chemin[len("/carte/"):] or "index.html"
            racine = BRAIN / "planet" if relatif in ("graph.json", "textes.json") else CARTE
        else:
            racine, relatif = ICI, chemin.lstrip("/") or "index.html"
            if relatif.endswith("/"):
                relatif += "index.html"
            if Path(relatif).suffix not in STATIQUES and chemin not in IMAGES_OUVERTES:
                return self.send_error(404)
        cible = (racine / relatif).resolve()
        if racine not in cible.parents or not cible.is_file():
            return self.send_error(404)
        self.path = "/" + str(cible.relative_to(racine))
        self.directory = str(racine)
        return super().do_GET()

    def translate_path(self, path):
        return str(Path(self.directory) / path.split("?", 1)[0].lstrip("/"))


if __name__ == "__main__":
    if "--definir-code" in sys.argv:
        code = sys.stdin.read().strip()
        if len(code) < 4:
            sys.exit("Code too short (minimum four characters); nothing was written")
        CODE_P.parent.mkdir(parents=True, exist_ok=True)
        CODE_P.write_text(empreinte(code) + "\n")
        os.chmod(CODE_P, 0o600)
        sys.exit(f"Access code set: {CODE_P}")
    print(f"GMTR launch screen: http://127.0.0.1:{PORT} (Ctrl+C to stop)")




    class Serveur(ThreadingHTTPServer):
        request_queue_size = 128
        daemon_threads = True
    Serveur(("127.0.0.1", PORT), Guichet).serve_forever()
