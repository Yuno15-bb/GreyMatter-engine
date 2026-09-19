#!/usr/bin/env python3
"""
SessionEnd hook — the full AUTONOMOUS maintenance pass.
At the end of a session, detached in the background, it chains:
  1. DISTILLER  : le distillateur extrait les fiches durables de la session finie
  2. FILE       : the gardener empties the Inbox, deduplicates, refines, optimizes
  3. COMMIT     : versioned

Remplace maybe_garden.py (qui ne faisait que ranger). Ici on distille AUSSI,
automatically, without triggering anything by hand.

Garde-fous quotas/boucles :
  - recursion guard: CLAUDE_BRAIN_GARDENING=1 (the headless run does not restart itself)
  - une distillation MAX par session (marqueur sessions/.distilled.json)
  - trivial sessions ignored (< MIN_MSG messages)
  - spawns only when there is work (a substantial undistilled session OR a full Inbox)
  - detached: never blocks the session from closing

Sort toujours 0.
"""
import os, sys, re, json, time, shutil, subprocess

def _transcripts_key() -> str:
    """The folder name Claude Code uses for this HOME, under ~/.claude/projects.

    It encodes the absolute home path by replacing BOTH "/" and "." with "-".
    Replacing only "/" works for a plain account name and breaks silently for a
    home like /Users/john.smith: the transcripts folder is never found, so
    distillation runs and finds nothing to do. No error, no signal.
    """
    return os.path.expanduser("~").replace("/", "-").replace(".", "-")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass
try:
    import brain_guard as guard
except Exception:
    guard = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
SESS = os.path.join(BRAIN, "sessions")
INDEX = os.path.join(SESS, ".index.json")          # written by archive_session.py
DISTILLED = os.path.join(SESS, ".distilled.json")  # sessions already distilled
LOG = os.path.join(SESS, "gardening.log")
INBOX_HEADER = "## 🆕 Inbox — notes to file (auto)"
# Nom du dossier transcripts = $HOME avec "/" -> "-" (convention Claude Code) ; ne
# JAMAIS coder le nom d'utilisateur en dur (cf. [[restauration-machine-2026-07-22]]).
TRANSCRIPTS = os.path.join(os.path.expanduser("~/.claude/projects"), _transcripts_key())
MANUAL_SAVES = os.path.join(BRAIN, "state", "manual-saves.jsonl")  # ledger written by on_fiche_write
MIN_MSG = 20  # en dessous : session triviale, pas de distillation

def inbox_has_work():
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return False
    if INBOX_HEADER not in mem:
        return False
    return bool(re.search(r'^\s*-\s*\[', mem.split(INBOX_HEADER, 1)[1], re.M))

def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def manual_saves_for(sid):
    """Knowledge notes written BY HAND during session `sid` (ledger written by on_fiche_write).
    Used to tell the distiller NOT to recreate what has already been recorded (anti-redundancy).
    Best-effort : ledger absent/illisible → liste vide (le distillateur tourne normalement)."""
    out = []
    if not sid:
        return out
    try:
        for line in open(MANUAL_SAVES, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("sid") == sid and e.get("path") and e["path"] not in out:
                out.append(e["path"])
    except Exception:
        pass
    return out

# The capsule proves it has a WINDOW by touching state/capsule-alive every 5 s
# (cf. capsule/main.js). Looking for a PROCESS proves nothing: on 2026-08-13 a
# two-day-old Electron with no window was taken for an open capsule, and so
# blocked its own replacement at every session start — silently, since writing
# the status still worked perfectly.
MOTIF_CAPSULE = "c-brain/trunk/capsule/node_modules/electron"
HEARTBEAT_MAX = 60          # 12 missed beats: we do not react to a hiccup
STARTUP_GRACE = 90          # a capsule that just started has not beaten yet


def _process_age(pid):
    """Seconds since the process started, or None when unreadable.

    ⚠ `etimes` (raw seconds) is a GNU extension: macOS does NOT know it, and `ps`
    answers by printing its LIST OF KEYWORDS, on stdout, with exit code 0. So an
    `int(out)` fails silently, `_process_age` returned None for everyone, and the
    zombie check answered "alive" no matter what — a stillborn guard. We read
    `etime`, which is portable, and parse it: [[dd-]hh:]mm:ss."""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "etime="],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if not out or " " in out:            # unexpected output (keyword list)
            return None
        days, _, rest = out.rpartition("-")
        parts = [int(x) for x in rest.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, sec = parts[-3:]
        return (int(days or 0) * 86400) + h * 3600 + m * 60 + sec
    except Exception:
        return None


def capsule_alive(pids):
    """True when a WINDOW is beating. Otherwise the process is a zombie to replace.

    ⚠ Two cautions, without which this check would kill healthy capsules:
      · a missing beat on a YOUNG process is not a zombie, it is a startup in
        progress (STARTUP_GRACE);
      · in doubt — unreadable age, access error — we answer ALIVE. A false zombie
        restarts a capsule for nothing; a false alive only costs one more round.
        Doubt must not kill."""
    try:
        alive = os.path.join(BRAIN, "state", "capsule-alive")
        if not os.path.exists(alive):
            # ⚠ NO beat has EVER been written. This is not a zombie, it is a
            #   capsule that cannot beat. Two real cases:
            #     · a capsule never launched since the install;
            #     · a capsule from a version PREDATING the emitter — the public
            #       package long carried this check without it (`capsule/main.js`
            #       is not synced; the emitter was ported into it by hand on
            #       2026-08-13, but an older install still runs without one).
            #   Without this guard, those capsules would be declared dead past the
            #   grace delay and killed in a loop, every single pass.
            #   We only judge what has ALREADY beaten and then gone quiet.
            return True
        if time.time() - os.path.getmtime(alive) < HEARTBEAT_MAX:
            return True
        ages = [a for a in (_process_age(p) for p in pids) if a is not None]
        if not ages:
            return True                      # unreadable → we touch nothing
        return min(ages) < STARTUP_GRACE     # young → starting up, not a zombie
    except Exception:
        return True


def ensure_capsule():
    """Opens the capsule if it is not already running (the agents are waking up).

    Light mode: if the file state/no-capsule exists, nothing is launched.
    La capsule (Electron + son helper GPU) est le plus gros consommateur CPU
    de la machine au repos ; sur un MacBook Air sans ventilateur elle force
    WindowServer to recompose the screen continuously."""
    try:
        if os.path.exists(os.path.join(BRAIN, "state", "no-capsule")):
            return
        cap = os.path.join(BRAIN, "capsule")
        elec = os.path.join(cap, "node_modules", ".bin", "electron")
        if not os.path.exists(elec):
            return
        # le vrai process tourne sous .../node_modules/electron/dist/... (le .bin/electron
        # n'est qu'un symlink), donc on matche le chemin du projet, pas le symlink.
        r = subprocess.run(["pgrep", "-f", MOTIF_CAPSULE],
                           capture_output=True, text=True)
        if r.stdout.strip():
            if capsule_alive(r.stdout.split()):
                return                       # really open: a window is beating
            # ZOMBIE: the process lives, its window does not. We replace it rather
            # than take it for a healthy capsule — that is what left the author's
            # orb invisible for two days on 2026-08-13.
            subprocess.run(["pkill", "-f", MOTIF_CAPSULE], capture_output=True)
            time.sleep(1)
        subprocess.Popen([elec, "."], cwd=cap,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass

def session_msg_count(sid):
    """Message count for the session. Primary source = the index written by
    archive_session.py. BUT both SessionEnd hooks start in parallel:
    if archiving is slow or cancelled, the index does not hold the session yet
    (n=0) and distillation of large sessions is wrongly skipped.
    Race-proof fallback: we count the lines of the .jsonl directly."""
    idx = load_json(INDEX, {})
    if sid in idx and isinstance(idx[sid], dict):
        n = idx[sid].get("n", 0)
        if n:
            return n
    # index muet (course de hooks) → compte direct dans le transcript brut
    if sid:
        path = os.path.join(TRANSCRIPTS, f"{sid}.jsonl")
        try:
            with open(path, "rb") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            pass
    return 0

def launch_agent(sid, n, to_distill):
    """Launches the headless maintenance run (distill+garden OR garden only) and wires it
    to brain_guard. Assumes the caller ALREADY holds the lock.
    Reused by SessionEnd (main) and by the auto-resume (resume_pending)."""
    claude = shutil.which("claude")
    if not claude:
        # `claude` introuvable — cas typique sous launchd (PATH minimal /usr/bin:/bin, sans
        # ~/.local/bin). The caller (resume_pending) has ALREADY dequeued the session: releasing
        # the lock alone would lose it (never distilled) → the "zero loss" guarantee broken. We
        # RE-QUEUE it before releasing the lock; an interactive SessionEnd (full PATH) will replay it.
        if guard is not None:
            if to_distill and sid:
                guard.enqueue(sid)
            guard.release_lock()
        return

    ensure_capsule()  # the capsule opens as the agents wake

    # PARENTLESS ARCHITECTURE: we no longer instantiate an orchestrating
    # un LLM parent qui se contente d'orchestrer en spawnant deux sous-agents — ce
    # parent did no intellectual work but re-read, on every turn, the results
    # returned by the sub-agents (a large cache_read, pure waste). Now the
    # shell sequences TWO `claude -p --agent …` calls directly (the distiller
    # THEN the gardener), and performs the capsule pulses and the commit itself (mechanical,
    # zero LLM). Same work, same quality, one LLM context less.
    py = sys.executable
    status_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_status.py")
    mark_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mark_distilled.py")
    guard_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_guard.py")
    upkeep_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_upkeep.py")
    embed_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed.py")
    embed2_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed2.py")
    graph_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_export.py")
    coact_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coactivation.py")
    doctor_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_doctor.py")
    cost = os.path.join(BRAIN, "sessions", "cost.jsonl")
    transcript = os.path.join(TRANSCRIPTS, f"{sid}.jsonl")

    # The tasks: the call IS the agent (via --agent), so no more "launch
    # sub-agent X" — we hand it its mission directly. Anti-waste instruction:
    # do not re-read a file already read, do not commit (the shell handles it).
    distill_task = (
        f"A session has just ended (id={sid}, {n} messages, "
        f"transcript: {transcript}, plus any archive note in sessions/archive/). "
        "Extract only the DURABLE notes and lessons. TOKEN ECONOMY IS MANDATORY: "
        "Do NOT read the whole transcript; rely on the archive note, and if needed "
        "grep and read at most ~60 targeted lines. NEVER re-read a file already read. "
        "If nothing deserves to stay, create nothing. Do NOT commit (the shell handles it). "
        "Keep your report short."
    )
    # ANTI-REDUNDANCY: notes already written BY HAND during the session
    # must not be recreated by the distiller (otherwise a transient duplicate and wasted tokens). We
    # tell it explicitly; it keeps the safety net for knowledge NOT saved.
    already = manual_saves_for(sid)
    if already:
        distill_task += (
            " IMPORTANT — these notes were ALREADY written or refined by hand during this session: "
            + ", ".join(already) +
            ". DO NOT RECREATE THEM; only complete them if something is genuinely missing, and "
            "extract only the DURABLE knowledge they do not already cover."
        )
    garden_task = (
        "Empty the MEMORY.md Inbox, file each note into the right map "
        "(lessons into lessons/INDEX.md, other notes into MEMORY.md), "
        "deduplicate, repair and weave the [[...]] links, mask any secret, refine. "
        "Do not needlessly re-read a file already read. Do NOT commit (the shell "
        "handles it). Keep your report short."
    )

    env = dict(os.environ)
    env["CLAUDE_BRAIN_GARDENING"] = "1"
    try:
        logf = open(LOG, "a")
    except Exception:
        logf = subprocess.DEVNULL

    write_status("busy", "distilling" if to_distill else "gardening",
                 "Waking the agents…", source="agent")

    state_dir = os.path.join(BRAIN, "state")
    dpf = os.path.join(state_dir, ".distill.txt")
    gpf = os.path.join(state_dir, ".garden.txt")
    try:
        os.makedirs(state_dir, exist_ok=True)
        open(dpf, "w", encoding="utf-8").write(distill_task)
        open(gpf, "w", encoding="utf-8").write(garden_task)
    except Exception:
        if guard is not None:
            guard.release_lock()
        return

    # Model PER AGENT. The distiller is the only creative stage of layer 1: its
    # failure loses knowledge permanently (gardening is mechanical and replayable).
    # Hence sonnet to distil, haiku to file. Same logic as brain_upkeep.MODEL.
    MODEL_L1 = {"distiller": "sonnet", "gardener": "haiku"}
    base = lambda m: (f'"{claude}" -p --model {m} --output-format json '
                      f'--dangerously-skip-permissions')
    pulse = lambda act, det: f'"{py}" "{status_cli}" busy {act} "{det}"'
    # MECHANICAL save (no LLM), wired here on 2026-08-13.
    # Before: `git add -A` plus one catch-all commit. That `add -A` is what
    # drowned 19 files of work in progress in e61fd01 (03/08), and 612 commits of
    # that kind sleep in the history. We now commit ZONE BY ZONE: the trunk's
    # pre-commit hook already refuses mixed commits, so we lean on it instead of
    # working around it.
    # TWO LINES, AND THE SPLIT IS DELIBERATE:
    #   · `commit_par_zone` SHIPS — it commits LOCALLY, on everyone's machine.
    #   · `tools/sync_depots.py` exists ONLY on the author's machine (`tools/` is
    #     not in sync.sh's whitelist). That one pushes, and measures the public
    #     package. A user who put a remote on their trunk never asked for their
    #     notes to leave at every session end — so the package contains NO push
    #     at all, and the file simply being absent is enough for the line to do
    #     nothing there.
    save = (f'"{py}" "{BRAIN}/hooks/commit_par_zone.py" || true\n'
            f'[ -f "{BRAIN}/tools/sync_depots.py" ] && '
            f'"{py}" "{BRAIN}/tools/sync_depots.py" --auto || true')

    # False-positive guard (OS crash / SIGKILL of the `claude` binary BEFORE it writes):
    # `interpret` reads the LAST line of cost.jsonl. If claude dies without writing,
    # that last line belongs to the PREVIOUS run (possibly a success) → a false
    # success → the session is marked distilled without being → knowledge lost. Fix: we count
    # the lines before the call; if none was added, we inject a synthetic error line
    # → `interpret` sees THIS run, fails, and re-queues the session.
    sentinel = ('{"is_error":true,'
                '"result":"claude exited without writing output (SIGKILL/crash?)"}')
    nlines = f"$(awk 'END{{print NR}}' \"{cost}\" 2>/dev/null || echo 0)"

    def agent_call(agent, pf):
        return [
            f'__N0={nlines}',
            f'{base(MODEL_L1.get(agent, "haiku"))} --agent {agent} "$(cat {pf})" '
            f'>> "{cost}" 2>> "{LOG}"',
            f'if [ "{nlines}" -le "$__N0" ]; then '
            f"printf '%s\\n' '{sentinel}' >> \"{cost}\"; fi",
        ]

    lines = []
    # Capsule HEARTBEAT: throughout the pass, a background loop refreshes `ts` every 5 s
    # (a `claude -p` call lasts minutes without rewriting the status → without this the capsule
    # would flicker to idle mid-work). Bounded to 600 iterations (~50 min) as a safety net in
    # case the final kill never happens, and killed explicitly just before `idle`.
    lines.append(f'( __i=0; while [ $__i -lt 600 ]; do "{py}" "{status_cli}" touch '
                 f'>/dev/null 2>&1; sleep 5; __i=$((__i+1)); done ) & __HB=$!')
    if to_distill:
        # 1) DISTIL directly through --agent distiller, then interpret the
        #    result (df=1: re-queue the session on "Not logged in"/quota/crash).
        #    Gardening happens only if distillation REALLY succeeded.
        lines.append(pulse("distilling", "Distilling this session"))
        lines += agent_call("distiller", dpf)
        lines.append(f'if "{py}" "{guard_cli}" interpret "{cost}" "{sid}" 1 ; then')
        lines.append(f'  "{py}" "{mark_cli}" "{sid}"')
        lines.append(f'  {pulse("gardening", "Organizing the tree")}')
        lines += ['  ' + l for l in agent_call("gardener", gpf)]
        lines.append('fi')
    else:
        # Gardening alone (a full Inbox, no session to distil).
        lines.append(pulse("gardening", "Organizing the tree"))
        lines += agent_call("gardener", gpf)
        lines.append(f'"{py}" "{guard_cli}" interpret "{cost}" "{sid}" 0')
    # MECHANICAL guard after the gardener (zero LLM): the gardener is the sole judge of its own
    # pass. brain_doctor recounts the defects (dead links, orphans, front matter,
    # off-map, MEMORY size) RIGHT AFTER it, and records the verdict in gardening.log. It fixes
    # nothing — the mechanic handles that later, through its sensor. Here we only want
    # a gardening pass that degrades the tree to be VISIBLE immediately, instead of
    # waiting up to 12 h for the mechanic's next wake-up.
    lines.append(f'"{py}" "{doctor_cli}" --json >/dev/null 2>&1')
    lines.append(
        f'''__D=$("{py}" -c 'import json;print(json.load(open("{BRAIN}/state/doctor.json"))["total"])' 2>/dev/null || echo -1); '''
        f'''if [ "$__D" != "0" ]; then echo "[doctor] $(date '+%F %T') post-jardinage: $__D defaut(s)" >> "{LOG}"; fi''')
    # SECOND LAYER (cohesion watch): after distill+garden, regenerates the mechanical
    # sensors (free) and wakes AT MOST one watch agent (challenger / architect
    # / archivist) if its threshold is crossed and its cooldown elapsed. brain_upkeep handles
    # priority, cadence and cost on its own (best effort, loses no data if it fails).
    # brain_upkeep pulses the capsule activity of the agent it wakes (or nothing).
    lines.append(f'"{py}" "{upkeep_cli}" run "{sid}"')
    # Refreshes the semantic recall index (brain_embed `build` is
    # INCREMENTAL: it re-encodes only the notes whose content changed, by hash).
    # Near-zero cost, zero LLM (a local embeddings model), and recall stays current
    # instead of running on a stale index. Placed after distill+garden to index
    # the fresh notes, just before the commit. IMPORTANT: brain_embed needs
    # numpy/model2vec → we invoke it with the .venv python (the system python of
    # hooks ne les a pas) ; absent → on saute silencieusement (|| true).
    venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        # HF_HUB_OFFLINE=1: the embeddings model is already cached locally → we avoid
        # a network round trip to the HF Hub on every pass (faster, works offline).
        # ⚠️ `|| true` TOUT SEUL A CACHÉ CE DÉFAUT PENDANT UN MOIS. Il faut que la chaîne
        # continue — l'indexation sémantique est optionnelle, elle ne doit pas empêcher le
        # commit — mais « continuer » et « ne rien dire » sont deux choses différentes. Un
        # échec ici ne laissait pas UNE ligne dans le journal, et la Planète, elle, continuait
        # d'annoncer « proximity = meaning, every note » (C bis A7, mesuré le 2026-09-19).
        # Un refus qui s'annonce est un résultat ; un refus muet est un mensonge différé.
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed_cli}" build >> "{LOG}" 2>&1'
                     f' || echo "⚠️  semantic RECALL index not rebuilt (brain_embed build failed)"'
                     f' >> "{LOG}"')
        # Recompute the SEMANTIC map (state/embed2.json) from the fresh index,
        # then regenerate planet/graph.json so the "meaning" view (key S) reflects current content.
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed2_cli}" >> "{LOG}" 2>&1'
                     f' || echo "⚠️  semantic MAP not recomputed (brain_embed2 failed) —'
                     f' the planet keeps the previous positions and says so" >> "{LOG}"')
    else:
        # Le cas LÉGITIME, dit à voix haute. Les embeddings sont optionnels par dessein
        # (docs/design-doc.md) ; ce qui ne l'est pas, c'est qu'un tronc sans eux ressemble en
        # tout point à un tronc dont le calcul a échoué.
        lines.append(f'echo "· semantic module not installed (.venv absent) — BM25 only,'
                     f' the planet shows structure" >> "{LOG}"')
    # Recompute the working memory (usage heat + co-activation links) from the
    # logs de recall/lecture, AVANT graph_export (qui lit coactivation.json). Pur stdlib.
    lines.append(f'"{py}" "{coact_cli}" >> "{LOG}" 2>&1 || true')
    lines.append(f'"{py}" "{graph_cli}" >> "{LOG}" 2>&1 || true')
    # save + idle + release: ALWAYS, whatever happened above.
    lines.append(pulse("committing", "Saving to git"))
    lines.append(save)
    lines.append('kill "$__HB" >/dev/null 2>&1 || true')   # stop the heartbeat BEFORE idle
    lines.append(f'"{py}" "{status_cli}" idle')
    lines.append(f'"{py}" "{guard_cli}" release')
    wrapper = "\n".join(lines)

    try:
        proc = subprocess.Popen(
            ["sh", "-c", wrapper],
            cwd=BRAIN, env=env,
            stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
            start_new_session=True,
        )
        # the hook holding the lock is about to die; we write the detached worker's PID
        # (vivant toute la passe) → une autre session voit un lock VIVANT et n'en lance pas 2.
        if guard is not None:
            try:
                guard.update_lock_pid(proc.pid)
            except Exception:
                pass
    except Exception:
        write_status("idle")
        if guard is not None:
            guard.release_lock()


def main():
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return  # we ARE the maintenance headless run

    # FREEZE ON AUTONOMOUS WRITERS (Phase 0 of the Brain V3 RFC, 2026-08-03).
    # While Brain V3 is being built outside production, the distiller, the
    # gardener and brain_upkeep would keep modifying the trunk — and since
    # automatic commits were cut, they would do it WITHOUT a trace in git.
    # The lab would then be working on a base moving underneath it, and
    # reconciling lab and production would become impossible to reason about.
    #
    # The queue itself keeps filling up (capture-only): nothing is lost,
    # everything will be distilled after the switch-over.
    #
    # To lift the freeze: delete ~/.c-brain/trunk/state/FREEZE
    freeze = os.path.join(BRAIN, "state", "FREEZE")
    if os.path.exists(freeze):
        try:
            data = json.loads(sys.stdin.read() or "{}")
            sid = data.get("session_id")
            if sid:
                guard.enqueue(sid)  # capture-only: we note it, we do not process it
        except Exception:
            pass
        return

    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = data.get("session_id")

    distilled = set(load_json(DISTILLED, []))
    n = session_msg_count(sid) if sid else 0
    to_distill = bool(sid) and sid not in distilled and n >= MIN_MSG
    to_garden = inbox_has_work()

    if not (to_distill or to_garden):
        return  # nothing to do → no agent launched

    claude = shutil.which("claude")
    if not claude:
        return

    # --- garde-fous tokens/compte (brain_guard) ---------------------------
    if guard is not None:
        if not guard.acquire_lock(sid):
            # Maintenance is already running (e.g. several sessions closed at the same
            # temps : la 1re a pris le verrou). On ne double PAS (anti-corruption),
            # but we QUEUE this session so it gets distilled afterwards —
            # otherwise it would be silently lost. Drained by the next
            # SessionEnd ou par resume_pending (launchd, ~10 min).
            if to_distill:
                guard.enqueue(sid)
            return
        if not guard.preflight_ok():
            # quota spent (reset not reached) → we DEFER, never crash
            if to_distill:
                guard.enqueue(sid)
            guard.release_lock()
            return
        # quota OK : on rejoue d'abord la session en attente la plus ancienne
        # (backlog accumulated while quota or login was down), one per pass.
        # On la retire ATOMIQUEMENT (dequeue_one) : le reste de la file reste sur
        # DISK, never in memory. The old drain_queue() emptied everything at once
        # then re-queued the rest — a process kill in between swallowed
        # the whole backlog (a real bug, surfaced by `brain audit`).
        resume_sid = guard.dequeue_one()
        if resume_sid:
            if to_distill and resume_sid != sid:
                guard.enqueue(sid)               # current session pushed back one slot
            sid, to_distill = resume_sid, True
            n = session_msg_count(sid) or MIN_MSG

    launch_agent(sid, n, to_distill)

if __name__ == "__main__":
    try:
        # `--capsule`: open the orb WITHOUT triggering any maintenance. Called by the
        # SessionStart hook. Before this, ensure_capsule() had a single caller
        # (launch_agent, at the END of a session): the orb therefore never opened
        # while you were working — 12 h of session without ever seeing it (reported
        # by the user, 2026-08-04). It always fades away on its own when idle, this
        # mode forces nothing.
        if "--capsule" in sys.argv:
            ensure_capsule()
        else:
            main()
    except Exception:
        pass
    sys.exit(0)
