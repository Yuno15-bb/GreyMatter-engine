#!/usr/bin/env python3
"""quota_probe — the credit probe: "can I spend RIGHT NOW?"

Why it exists (2026-08-13, at the author's request): the quota guard used to set a
waiting time GUESSED from the error message (1 h, 2 h, 4 h… cf.
[[account-quota-resilience]]). Such a delay cannot know that the user has just
TOPPED UP their cap or SWITCHED ACCOUNTS. What actually happened that morning: the
cap was raised at 08:35, yet maintenance stayed frozen until 09:32 for nothing, and
the marker had to be cleared by hand.

The principle: stop GUESSING, ASK. A one-token request carries the
`anthropic-ratelimit-unified-*` headers, which give the exact state of the account
and the exact reset time.

Measured cost: 22 input tokens + 1 output token on Haiku ≈ $0.00003. Probing every
15 min, a whole day of being blocked costs less than a cent — compare that with
blindly restarting a full agent (~$1 a go), which is precisely the dead loop the
progressive backoff had to put out.

Hence the separation to keep in mind when touching this file:
  - the PROBE is free      → fixed cadence (15 min), it may repeat;
  - the AGENT is expensive → it only starts on an OBSERVED green light, never on
    the expiry of an assumed delay.

Command-line usage (readable, because it is the observable of check #2):
    python3 quota_probe.py
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"       # the cheapest: the probe does not judge, it tests access
KEYCHAIN = "Claude Code-credentials"
TIMEOUT = 20

# The Claude Code OAuth API requires this first system block, otherwise it rejects the token.
SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."


def _token() -> str:
    """The OAuth token of the active account, read from the Keychain. Never logged."""
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN, "-w"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return ""
        return json.loads(out.stdout)["claudeAiOauth"]["accessToken"]
    except Exception:
        return ""


def token_fingerprint() -> str:
    """Fingerprint of the ACTIVE account, derived from the token — not the token itself.

    An immediate, free signal: the user switches account → the token changes → this
    fingerprint changes. More reliable than reading a transcript's accountUuid
    (cf. account_fingerprint in brain_guard), which only moves once a session has
    already run on the new account."""
    t = _token()
    return hashlib.sha256(t.encode()).hexdigest()[:12] if t else ""


def _limit_headers(headers) -> dict:
    """The unified counters, in plain form. Absent = plan/route with no declared limit."""
    d = {}
    for h in headers:
        hl = h.lower()
        if hl.startswith("anthropic-ratelimit-unified-"):
            d[hl.replace("anthropic-ratelimit-unified-", "")] = headers[h]
    return d


def probe() -> dict:
    """One one-token request. Returns a verdict you can act on:

      {"ok": bool,          # True = a real request has just GONE THROUGH, we may spend
       "http": int|None,    # HTTP code (429 = refused, 401 = stale token, None = network)
       "reason": str,       # human-readable
       "reset": float|None, # exact epoch of the return, given by the API (no more guessing)
       "limits": {...},     # raw counters (5h, 7d, overage…)
       "fingerprint": str,  # account probed
       "ts": float}

    `ok` is True on HTTP 200 even when the `unified-status` header says "rejected":
    that is exactly the state seen that morning — the 5 h window exhausted BUT overage
    active, so requests go through. What counts is not what the counter announces, it
    is that a real request has just succeeded. (Check #2: the observable is the
    request that goes through, not the counter that comments on it.)"""
    base = {"ok": False, "http": None, "reason": "", "reset": None,
            "limits": {}, "fingerprint": "", "ts": time.time()}
    token = _token()
    if not token:
        base["reason"] = "unreadable token (Keychain locked or account signed out)"
        return base
    base["fingerprint"] = hashlib.sha256(token.encode()).hexdigest()[:12]

    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1,
        "system": [{"type": "text", "text": SYSTEM}],
        "messages": [{"role": "user", "content": "."}],
    }).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "authorization": "Bearer " + token,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "content-type": "application/json",
    })
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT)
        base.update(ok=True, http=r.status, reason="credit available",
                    limits=_limit_headers(r.headers))
    except urllib.error.HTTPError as e:
        lim = _limit_headers(e.headers)
        try:
            msg = json.loads(e.read())["error"]["message"][:200]
        except Exception:
            msg = f"HTTP {e.code}"
        base.update(http=e.code, reason=msg, limits=lim)
        if e.code == 401:
            # Stale token: this is NOT a verdict about credit. We do not unblock,
            # but we do not tighten anything either — the CLI will refresh the token.
            base["reason"] = "stale token (401) — probe without a verdict"
    except Exception as e:
        base["reason"] = f"network unreachable ({type(e).__name__})"
        return base

    for key in ("reset", "5h-reset", "7d-reset"):
        if key in base["limits"]:
            try:
                base["reset"] = float(base["limits"][key])
                break
            except Exception:
                pass
    return base


def _pct(v):
    try:
        return f"{float(v) * 100:.0f} %"
    except Exception:
        return str(v)


if __name__ == "__main__":
    v = probe()
    print("credit available:", "YES" if v["ok"] else "NO",
          f"(HTTP {v['http']}) — {v['reason']}")
    lim = v["limits"]
    if lim:
        print("account", v["fingerprint"], "—",
              "overage active" if lim.get("overage-in-use") == "true" else "overage inactive")
        for win, name in (("5h", "5 h window"), ("7d", "7 d window"), ("overage", "overage")):
            u, s, rs = lim.get(f"{win}-utilization"), lim.get(f"{win}-status"), lim.get(f"{win}-reset")
            if u is None and s is None:
                continue
            when = time.strftime("%d/%m %H:%M", time.localtime(float(rs))) if rs else "?"
            print(f"  {name:<12} {_pct(u):>6}  {s or '':<16} back at {when}")
    sys.exit(0 if v["ok"] else 7)
