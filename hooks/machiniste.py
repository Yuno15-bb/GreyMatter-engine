#!/usr/bin/env python3
"""
Machiniste — le 8e agent du C Brain, couche MACHINE PHYSIQUE.

The other agents maintain the knowledge; the mechanic maintains the software infrastructure.
The machinist maintains **the machine that runs all of it**: RAM, CPU, heat.

It runs with NO LLM (launchd, every 10 minutes) — zero cost, no quota consumed.
It does not reason; it applies verifiable rules. The fine analysis is the job of the
`machinist.md` agent, which reads what this daemon measured.

SAFETY DOCTRINE — an automatic killer that gets it wrong destroys work.
  · Il ne tue QUE des serveurs de dev ORPHELINS, INACTIFS et VIEUX. Trois conditions, toutes requises.
  · Everything else is REPORTED, never touched.
  · A hardcoded protection list plus a user-editable list come first, always.
  · Every action is logged with its full justification.

Usage :
  python3 machiniste.py            # a normal round (measure + safe actions)
  python3 machiniste.py --dry-run  # shows what it would do, touches nothing
  python3 machiniste.py --report   # the last state, readable
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
STATE = os.path.join(BRAIN, "state")
SNAPSHOT = os.path.join(STATE, "machiniste.json")       # the last state, overwritten
JOURNAL = os.path.join(STATE, "machiniste.jsonl")       # historique, append-only
PROTECT = os.path.join(STATE, "machiniste-protect.txt") # user-editable patterns
LOG = os.path.join(BRAIN, "sessions", "machiniste.log")

PAGE = 16384  # memory page size on Apple Silicon

# --- Ce qu'on ne touche JAMAIS, quoi qu'il arrive -----------------------------
#     Work sessions, security agents, applications, system infrastructure, the capsule.
#
#     ⚠️ Lesson from testing: an early version matched the word "claude"
#     anywhere in the command line. As a result, EVERY process whose path
#     contenait « claude » (donc tout ~/.c-brain/trunk/, tout /tmp/claude-501/) devenait
#     intouchable — le filet attrapait tout et ne prouvait plus rien. On ancre donc les
#     patterns anchored on the executable, not on a path fragment.
NEVER_KILL = re.compile(
    r"(?:^|/)claude(?:\s|$)"                    # the claude binary itself
    # ⚠️ Second trap from the same test: ".app/Contents/MacOS/" looked like it meant GUI apps.
    #    In reality EVERY Python interpreter lives inside a .app bundle
    #    (Homebrew and CommandLineTools alike) — so the rule made immune the very
    #    dev server that motivated this whole thing. We anchor on /Applications/.
    r"|^/Applications/|^/System/Applications/|/Applications/[^/]+\.app/Contents/"
    r"|/System/|/usr/libexec/|/usr/sbin/|/sbin/"  # system infrastructure
    r"|(?:^|/)(gpg-agent|ssh-agent|launchd|sshd|cron)(?:\s|$)"
    r"|node_modules/electron"                   # la capsule du Brain
    r"|(?:^|/)(Code|Cursor|Xcode|Docker)(?:\s|$)",
    re.I)

# --- Dev servers: the only permitted game -------------------------------
#     Deliberately precise patterns. Too broad a pattern would kill real work.
DEV_SERVER = re.compile(
    r"(backend/server\.py|manage\.py\s+runserver|uvicorn|gunicorn|flask\s+run|"
    r"http\.server|vite(\s|$)|next\s+dev|nodemon|webpack(-dev-server)?|"
    r"rails\s+s(erver)?|php\s+-S|serve\s+-p|live-server)",
    re.I)

MIN_AGE_S = 20 * 60      # an orphan must be at least 20 min old to be suspect
IDLE_SAMPLE_S = 5        # sampling window used to prove inactivity
IDLE_MAX_CPU_S = 0.2     # above this the process is working → we do not touch it
MIN_FOOTPRINT_MB = 200   # below this it is not worth the risk


def sh(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ============================ CAPTEURS ======================================

def read_memory():
    """Real memory state. 'Compressed' is the metric that matters on a small-RAM machine."""
    out = sh(["vm_stat"])
    vals = {}
    for line in out.splitlines():
        m = re.match(r"([^:]+):\s+(\d+)", line)
        if m:
            vals[m.group(1).strip()] = int(m.group(2))
    g = lambda k: vals.get(k, 0) * PAGE / 1073741824
    swap = sh(["sysctl", "-n", "vm.swapusage"])
    sm = re.search(r"used\s*=\s*([\d.,]+)M", swap)
    return {
        "active_gb": round(g("Pages active"), 2),
        "wired_gb": round(g("Pages wired down"), 2),
        "inactive_gb": round(g("Pages inactive"), 2),
        "free_gb": round(g("Pages free"), 2),
        "compressed_gb": round(g("Pages occupied by compressor"), 2),
        "swap_mb": round(float((sm.group(1) if sm else "0").replace(",", ".")), 1),
    }


def read_cpu():
    """Load and frequency. No temperature: that requires sudo (powermetrics)."""
    up = sh(["uptime"])
    la = re.search(r"averages?:?\s*([\d.,]+)[,\s]+([\d.,]+)[,\s]+([\d.,]+)", up)
    f = lambda s: float(s.replace(",", "."))
    ncpu = int(sh(["sysctl", "-n", "hw.ncpu"]).strip() or 8)
    return {
        "load1": f(la.group(1)) if la else 0.0,
        "load5": f(la.group(2)) if la else 0.0,
        "load15": f(la.group(3)) if la else 0.0,
        "ncpu": ncpu,
        "uptime_days": round(float(sh(["sysctl", "-n", "kern.boottime"]) and
                                   (time.time() - _boottime()) / 86400 or 0), 2),
    }


def _boottime():
    m = re.search(r"sec\s*=\s*(\d+)", sh(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else time.time()


def footprint_mb(pid):
    """Empreinte PHYSIQUE, compression comprise.

    The trap: an abandoned dev server showed 10 MB of RSS while it was holding
    2.2 GB. All of its content was compressed, therefore invisible in `ps` and in
    Activity Monitor sorted by RSS. Only vmmap tells the truth.
    """
    out = sh(["vmmap", "--summary", str(pid)], timeout=25)
    m = re.search(r"Physical footprint:\s+([\d.]+)([KMG])", out)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return n * (1024 if unit == "G" else 1 if unit == "M" else 1 / 1024)


def cpu_time_s(pid):
    t = sh(["ps", "-o", "time=", "-p", str(pid)]).strip()
    m = re.match(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return (int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + float(s))


def load_protect():
    """Extra patterns the user wants to protect. One per line."""
    pats = []
    try:
        with open(PROTECT) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    pats.append(line)
    except FileNotFoundError:
        pass
    return pats


def scan_processes():
    """Inventory: pid, ppid, age, command. A single ps call."""
    out = sh(["ps", "-Ao", "pid=,ppid=,etime=,command="])
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, cmd = parts
        try:
            procs.append({"pid": int(pid), "ppid": int(ppid),
                          "age_s": _etime_s(etime), "cmd": cmd})
        except ValueError:
            continue
    return procs


def _etime_s(e):
    m = re.match(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$", e)
    if not m:
        return 0
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + int(s)


def _ancestors():
    """The machinist's own ancestry chain — untouchable by construction."""
    out, pid = set(), os.getpid()
    while pid and pid > 1:
        out.add(pid)
        try:
            pid = int(sh(["ps", "-o", "ppid=", "-p", str(pid)]).strip() or 0)
        except ValueError:
            break
    return out


def has_live_connection(pid):
    """A server with an ESTABLISHED connection is serving somebody right now."""
    out = sh(["lsof", "-a", "-p", str(pid), "-i", "-P", "-n"], timeout=15)
    return "ESTABLISHED" in out


# ============================ DECISION ======================================

def find_zombies(procs, protect, dry):
    """Serveurs de dev orphelins, inactifs, vieux et gros. Les 4 conditions.

    Orphan (ppid == 1) means the terminal that launched it is dead. A server
    started in the foreground, or with & in an open shell, has that shell as parent —
    so it is NEVER a candidate. That is what makes the rule safe.
    """
    found, killed = [], []
    ancetres = _ancestors()          # jamais se tirer une balle dans le pied
    for p in procs:
        cmd = p["cmd"]
        if p["pid"] in ancetres:                          continue
        if p["ppid"] != 1:                                continue
        if not DEV_SERVER.search(cmd):                    continue
        if NEVER_KILL.search(cmd):                        continue
        if any(pat in cmd for pat in protect):            continue
        if p["age_s"] < MIN_AGE_S:                        continue

        fp = footprint_mb(p["pid"])
        if fp is None or fp < MIN_FOOTPRINT_MB:           continue

        # Proof of inactivity: we sample, we do not assume.
        c0 = cpu_time_s(p["pid"])
        time.sleep(IDLE_SAMPLE_S)
        c1 = cpu_time_s(p["pid"])
        if c0 is None or c1 is None:                      continue
        delta = c1 - c0
        if delta > IDLE_MAX_CPU_S:                        continue
        if has_live_connection(p["pid"]):                 continue

        item = {"pid": p["pid"], "cmd": cmd[:160], "age_min": round(p["age_s"] / 60),
                "footprint_mb": round(fp), "cpu_delta_s": round(delta, 3),
                "reason": "serveur de dev orphelin, inactif et vieux"}
        found.append(item)
        if not dry:
            try:
                os.kill(p["pid"], 15)          # SIGTERM : on demande, on n'arrache pas
                time.sleep(3)
                try:
                    os.kill(p["pid"], 0)
                    item["result"] = "SIGTERM ignored — left alive, check by hand"
                except ProcessLookupError:
                    item["result"] = "stopped cleanly"
                    killed.append(item)
            except ProcessLookupError:
                item["result"] = "already dead"
            except PermissionError:
                item["result"] = "permission denied"
        else:
            item["result"] = "dry-run"
    return found, killed


def find_reportable(procs, mem, cpu):
    """What we REPORT without touching. Judgement belongs to the user or the agent."""
    alerts = []
    if mem["compressed_gb"] > 5:
        alerts.append({"niveau": "warn", "sujet": "ram-compressee",
                       "msg": f"{mem['compressed_gb']} GB compressed — "
                              "close tabs or reboot; it does not come back down on its own"})
    if mem["swap_mb"] > 2000:
        alerts.append({"niveau": "warn", "sujet": "swap",
                       "msg": f"{mem['swap_mb']} MB of swap — the machine is writing to the SSD"})
    if cpu["load15"] > cpu["ncpu"]:
        alerts.append({"niveau": "warn", "sujet": "charge",
                       "msg": f"15-min load {cpu['load15']} > {cpu['ncpu']} cores — work is queuing"})
    if cpu["uptime_days"] > 5:
        alerts.append({"niveau": "info", "sujet": "uptime",
                       "msg": f"{cpu['uptime_days']} days without a reboot — "
                              "compressed memory keeps accumulating"})

    # Doublons de capsule (cf. lesson electron-zombie-process-cleanup)
    caps = [p for p in procs if "c-brain/trunk/capsule/node_modules/electron/dist" in p["cmd"]
            and "--type=" not in p["cmd"]]
    if len(caps) > 1:
        alerts.append({"niveau": "warn", "sujet": "capsule-doublon",
                       "msg": f"{len(caps)} instances de capsule — pids "
                              f"{[c['pid'] for c in caps]}"})

    # Large orphans outside the firing range: we name them, we let them live.
    for p in procs:
        if p["ppid"] != 1 or p["age_s"] < MIN_AGE_S:      continue
        if NEVER_KILL.search(p["cmd"]) or DEV_SERVER.search(p["cmd"]): continue
        if not re.search(r"(python|node|ruby|java|deno|bun)", p["cmd"], re.I): continue
        fp = footprint_mb(p["pid"])
        if fp and fp > 500:
            alerts.append({"niveau": "info", "sujet": "orphelin-inconnu",
                           "msg": f"pid {p['pid']} · {round(fp)} Mo · "
                                  f"{p['cmd'][:90]} — unrecognized orphan, NOT touched"})
    return alerts


# ============================ SORTIE ========================================

def write_out(payload):
    os.makedirs(STATE, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(SNAPSHOT, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with open(JOURNAL, "a") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if payload["actions"] or payload["alerts"]:
        with open(LOG, "a") as f:
            f.write(f"\n[{payload['when']}] compressed {payload['memory']['compressed_gb']} GB · "
                    f"swap {payload['memory']['swap_mb']} Mo · charge {payload['cpu']['load15']}\n")
            for a in payload["actions"]:
                f.write(f"  ⚑ KILLED pid {a['pid']} ({a['footprint_mb']} MB) — {a['cmd'][:90]}\n")
            for a in payload["alerts"]:
                f.write(f"  · [{a['niveau']}] {a['sujet']} : {a['msg']}\n")


def report():
    try:
        with open(SNAPSHOT) as f:
            d = json.load(f)
    except Exception:
        print("No round recorded yet. Run: python3 machiniste.py")
        return
    m, c = d["memory"], d["cpu"]
    print(f"🔧 Machinist — last round {d['when']}")
    print(f"   RAM   compressed {m['compressed_gb']} GB · free {m['free_gb']} GB · swap {m['swap_mb']} MB")
    print(f"   CPU   load {c['load1']} / {c['load5']} / {c['load15']} across {c['ncpu']} cores")
    print(f"   Uptime {c['uptime_days']} j")
    if d["actions"]:
        print("   Actions :")
        for a in d["actions"]:
            print(f"     ⚑ pid {a['pid']} ({a['footprint_mb']} Mo) — {a.get('result')}")
    if d["alerts"]:
        print("   Signalements :")
        for a in d["alerts"]:
            print(f"     · [{a['niveau']}] {a['msg']}")
    if not d["actions"] and not d["alerts"]:
        print("   ✅ nothing to report")


def main():
    if "--report" in sys.argv:
        return report()
    dry = "--dry-run" in sys.argv

    procs = scan_processes()
    mem, cpu = read_memory(), read_cpu()
    protect = load_protect()
    candidats, killed = find_zombies(procs, protect, dry)
    alerts = find_reportable(procs, mem, cpu)
    mem_after = read_memory() if killed else mem

    payload = {
        "when": now_iso(),
        "dry_run": dry,
        "memory": mem,
        "memory_after": mem_after,
        "freed_gb": round(mem["compressed_gb"] - mem_after["compressed_gb"], 2),
        "cpu": cpu,
        "actions": candidats,
        "alerts": alerts,
    }
    write_out(payload)
    if dry or "--verbose" in sys.argv:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # A daemon never breaks the machine it watches: it exits 0 and records.
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a") as f:
                f.write(f"[{now_iso()}] ERREUR machiniste : {e}\n")
        except Exception:
            pass
    sys.exit(0)
