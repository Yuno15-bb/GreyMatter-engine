#!/usr/bin/env python3
"""
gmtr_lock.py — the map's access code holds under parallel guesses, and a
session does not outlive its token.

Holes an external audit pointed at, each measured before it was closed:

- The lockout (five wrong codes, then 30 s) was a counter shared by threads with
  nothing around it. Forty wrong codes sent at once were ALL verified: every
  request passed the "are we locked?" check before any of them had counted.
- A session token lived as long as the server did.
- Any page could reach the server under another name (DNS rebinding) and
  read the launch screen or try codes; the Host header is now checked.

This starts the real server on a throwaway HOME, sends twenty wrong codes at
once, and requires exactly five to be verified. Then it opens a session with
the right code, ages its token past expiry, and requires the map to lock again.

Run:      HOME=$(mktemp -d) python3 tests/gmtr_lock.py
Sabotage: ... --sabotage race    (no lock: more than five get verified)
          ... --sabotage ttl     (the old check: an expired token still opens)
          ... --sabotage host    (no Host check: a rebound page is served)
Both must exit 1.
"""
import contextlib
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = 0


def check(ok, what):
    global FAILS
    print(f"  {'✅' if ok else '❌'} {what}")
    FAILS += 0 if ok else 1


def main():
    sabotage = sys.argv[sys.argv.index("--sabotage") + 1] if "--sabotage" in sys.argv else None
    os.environ["HOME"] = tempfile.mkdtemp()     # the access code goes here, never in a real HOME
    subprocess.run([sys.executable, str(ROOT / "gmtr" / "serveur.py"), "--definir-code"],
                   input="the-right-code", text=True, capture_output=True, check=True)

    sys.path.insert(0, str(ROOT / "gmtr"))
    import serveur

    if sabotage == "race":
        serveur.VERROU = contextlib.nullcontext()
    if sabotage == "host":
        serveur.Guichet._hote_local = lambda self: True
    if sabotage == "ttl":
        def ancien(self):
            for morceau in (self.headers.get("Cookie") or "").split(";"):
                cle, _, val = morceau.strip().partition("=")
                if cle == "gmtr_session" and val in serveur.SESSIONS:
                    return True
            return False
        serveur.Guichet._session = ancien

    class Serveur(ThreadingHTTPServer):     # as in serveur.py: a backlog of 5 resets a burst
        request_queue_size = 128
        daemon_threads = True
    srv = Serveur(("127.0.0.1", 0), serveur.Guichet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(code):
        r = urllib.request.Request(f"{base}/deverrouiller", method="POST",
                                   data=json.dumps({"code": code}).encode())
        try:
            with urllib.request.urlopen(r) as rep:
                return rep.status, rep.headers.get("Set-Cookie") or ""
        except urllib.error.HTTPError as e:
            return e.code, ""

    def get(path, cookie, host=None):
        r = urllib.request.Request(f"{base}{path}", headers={"Cookie": cookie})
        if host:
            r.add_unredirected_header("Host", host)
        try:
            with urllib.request.urlopen(r) as rep:
                return rep.status
        except urllib.error.HTTPError as e:
            return e.code

    print("▸ 1. twenty wrong codes at once")
    with cf.ThreadPoolExecutor(20) as ex:
        codes = [c for c, _ in ex.map(lambda _: post("wrong"), range(20))]
    check(codes.count(401) == serveur.ESSAIS_MAX,
          f"exactly {serveur.ESSAIS_MAX} verified, the rest refused as locked "
          f"(got {codes.count(401)} verified, {codes.count(429)} locked)")

    print("▸ 2. a session, then its expiry")
    serveur.ECHECS.update(n=0, jusqua=0.0)
    statut, cookie = post("the-right-code")
    check(statut == 200 and "HttpOnly" in cookie and "SameSite=Strict" in cookie,
          "the right code opens a session, cookie HttpOnly and SameSite=Strict")
    jeton_cookie = cookie.split(";", 1)[0]
    check(get("/etat.json", jeton_cookie) == 200, "…which opens the map's data")
    jeton = jeton_cookie.split("=", 1)[1]
    serveur.SESSIONS[jeton] = time.time() - 1
    check(get("/etat.json", jeton_cookie) == 401, "an expired token no longer opens it")

    print("▸ 3. a page under another name is turned away (DNS rebinding)")
    port = srv.server_address[1]
    check(get("/amorce.json", "") == 200, "the launch screen answers on 127.0.0.1")
    check(get("/amorce.json", "", host=f"localhost:{port}") == 200, "…and on localhost")
    check(get("/amorce.json", "", host=f"attacker.example:{port}") == 403,
          "a rebound name gets 403, even on the launch screen")

    srv.shutdown()
    print(f"{'✅ all green' if FAILS == 0 else f'❌ {FAILS} failure(s)'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
