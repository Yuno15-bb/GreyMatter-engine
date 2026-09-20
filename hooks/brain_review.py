#!/usr/bin/env python3
"""brain_review — AUDIT GLOBAL du contenu/topologie du tronc (≠ brain_audit).

Trois audits distincts coexistent, ne pas confondre :
  - brain_audit  = health of the PIPELINE (distillation, quota, queue).
  - brain_doctor = INDIVIDUAL defects (dead links, orphans, front matter, naming).
  - brain_review (HERE) = an AGGREGATED view of KNOWLEDGE HEALTH: gathers
    into ONE report what topology + utility + challenger + doctor already
    measure, plus two new checks (notes stale for >3 months, inconsistent
    infrastructure paths), so a human or an agent gets a complete view of the
    trunk at a glance — without reading five separate JSON files.

Separation of powers:
  ce module MESURE et PROPOSE, il ne MODIFIE AUCUNE fiche — exactement comme
  topology/utility (mechanical, cheap, zero LLM). JUDGEMENT and action stay
  aux agents : l'architecte tisse les liens, le challenger tranche les doutes,
  the archivist proposes archiving, the gardener files, the mechanic repairs
  the infrastructure. brain_review writes ONLY state/review.{json,md}.

Usage :
  brain_review.py            → regenerates topology+utility, aggregates everything, writes
                               state/review.{json,md}, prints the markdown summary.
  brain_review.py --stale    → does not call the engines, reads existing state
                               (fast; reports how fresh the data is).
  brain_review.py --json     → also prints the aggregated JSON on stdout.
  brain_review.py --quiet    → writes the files, prints nothing.
"""
import os, re, sys, json, time, glob, subprocess

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
STATE = os.path.join(BRAIN, "state")
HOOKS = os.path.join(BRAIN, "hooks")
STALE_DAYS = 90                                     # « plus de trois mois »
FICHE_DIRS = ("projects", "lessons", "meta", "life", "agents", "planet", "sessions")
SKIP_PARTS = {".git", "node_modules", "audits", "capsule", "planet/dist"}
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}


def _rj(name, default):
    try:
        return json.load(open(os.path.join(STATE, name), encoding="utf-8"))
    except Exception:
        return default


def _run(engine, *args):
    """Runs a measuring engine (topology/utility) to refresh its state."""
    p = os.path.join(HOOKS, engine)
    if not os.path.exists(p):
        return
    try:
        subprocess.run([sys.executable, p, *args], cwd=BRAIN, capture_output=True, timeout=120)
    except Exception:
        pass


def _fiches_in(dirs):
    out = []
    for d in dirs:
        for p in glob.glob(os.path.join(BRAIN, d, "**", "*.md"), recursive=True):
            rel = os.path.relpath(p, BRAIN)
            if rel in STRUCTURAL_MAPS:
                continue
            if any(part in SKIP_PARTS for part in rel.split(os.sep)):
                continue
            out.append((rel, p))
    return out


def _all_fiches():
    return _fiches_in(FICHE_DIRS)


def _git_last_ts():
    """Timestamp of the last commit per file, in a single git pass."""
    last = {}
    try:
        r = subprocess.run(["git", "-C", BRAIN, "log", "--format=@%ct", "--name-only"],
                           capture_output=True, text=True, timeout=60)
        cur = 0
        for line in r.stdout.splitlines():
            if line.startswith("@"):
                cur = int(line[1:])
            elif line.strip() and line not in last:
                last[line.strip()] = cur      # first occurrence = the most recent commit
    except Exception:
        pass
    return last


def stale_fiches():
    """Notes whose last commit is older than STALE_DAYS days."""
    now = time.time()
    last = _git_last_ts()
    out = []
    for rel, p in _all_fiches():
        ts = last.get(rel)
        if ts is None:
            try:
                ts = os.path.getmtime(p)      # non suivie par git → mtime en repli
            except OSError:
                continue
        age_days = (now - ts) / 86400
        if age_days > STALE_DAYS:
            out.append({"note": rel, "days": int(age_days),
                        "date": time.strftime("%Y-%m-%d", time.localtime(ts))})
    out.sort(key=lambda x: x["days"], reverse=True)
    return out


# INFRASTRUCTURE notes only: describing a stale path there is a real bug. Elsewhere
# (sessions/archive, project logs), an old home is a dated HISTORICAL fact,
# not an inconsistency — we do not report it (noise).
INFRA_DIRS = ("meta", "agents")


def path_incoherences():
    """Inconsistent paths in INFRASTRUCTURE notes: a reference to a home that is not
    pas celui de la machine courante (migration de compte, copier-coller d'une
    autre machine). Constat, pas correction.

    The user name is DERIVED, never hardcoded: that is exactly the bug that
    broke distillation during an account migration."""
    me = os.path.basename(os.path.expanduser("~"))
    other = re.compile(r"/Users/(?!" + re.escape(me) + r"\b)([A-Za-z0-9._-]+)")
    hits = []
    for rel, p in _fiches_in(INFRA_DIRS):
        try:
            lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            m = other.search(line)
            if m:
                hits.append({"note": rel, "line": i,
                             "type": f"path of another user ({m.group(1)})",
                             "excerpt": line.strip()[:160]})
    return hits


def build():
    topo = _rj("topology.json", {})
    util = _rj("utility.json", {})
    challenges = _rj("challenges.json", [])
    coherence = _rj("coherence.json", [])
    doctor = _rj("doctor.json", {})

    review = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "topology_generated_at": topo.get("generated_at"),
        # ⚠️ TWO COUNTERS, TWO DIFFERENT SETS — corrected 2026-09-20 (C bis, B4).
        #   This line used to read `topo.get("n_notes", doctor.get("notes"))`, which
        #   looks like a harmless default and is not: the two numbers do not count the
        #   same thing. brain_topology counts NOTES WOVEN INTO THE GRAPH — five zones
        #   (agents, lessons, life, meta, projects), frontmatter with a `name:`, README
        #   and structural maps excluded. brain_doctor counts MARKDOWN FILES IN THE
        #   REPOSITORY — twelve zones, skills/ and tools/ included. MEASURED on the
        #   author's trunk that day: 726 against 946, a gap of 220, printed under the
        #   same word "notes" with nothing saying the measurement had changed.
        #   Reproduced by hiding topology.json: the summary line went from
        #   "726 notes · 2968 links · 1 component(s)" to
        #   "945 notes · None links · None component(s) · topology measured on None".
        #   So: no substitution. A missing topology leaves these fields None and the
        #   report SAYS it did not look, which is the one thing the old line could not
        #   express. The doctor's count is kept, under its own name, as what it is.
        "n_notes": topo.get("n_notes"),
        "n_links": topo.get("n_links"),
        "n_files_in_repo": doctor.get("notes"),
        # — topology (l'architecte tisse / reclasse) —
        "missing_links": topo.get("missing_links", []),
        "isolated": topo.get("isolated", []),
        "faiblement_liees": topo.get("faiblement_liees", []),
        "n_components": topo.get("n_components"),
        "components": topo.get("components", []),
        "odd_placement": topo.get("odd_placement", []),
        # — utility (the archivist prunes) —
        "dead_weight": util.get("dead_weight", []),
        "ignorees": util.get("ignorees", []),
        # — challenger (tranche les doutes) —
        "doubts": challenges,
        "overlaps": coherence,
        # — doctor (individual defects; the mechanic/gardener repairs) —
        "dead_links": doctor.get("dead_links", []),
        "orphans": doctor.get("orphans", []),
        "off_index": doctor.get("off_index", []),
        "memory_too_heavy": doctor.get("memory_too_heavy", []),
        "naming": doctor.get("naming", []),
        "frontmatter": doctor.get("frontmatter", []),
        "drift_git": doctor.get("drift_git"),
        # — brain_review's own new checks —
        "stale_notes": stale_fiches(),
        "odd_paths": path_incoherences(),
    }
    return review


def _n(x):
    return len(x) if isinstance(x, (list, dict)) else (x or 0)


def to_markdown(r):
    L = []
    a = L.append
    a(f"# Global trunk audit — {r['generated_at']}")
    if r.get("n_notes") is None:
        # "Nothing to report" and "I did not look" must not print the same way — the
        # property tests/doctor_contract.py states for the doctor, applied here.
        a("\n⚠️  Topology not measured: no note, link or component count in this report."
          " Run brain_review.py without --stale to measure it.")
        if r.get("n_files_in_repo"):
            a(f"    (brain_doctor counts {r['n_files_in_repo']} markdown files in the"
              " repository — a different set: it includes skills/, tools/ and the maps.)\n")
        else:
            a("")
    else:
        a(f"\n{r['n_notes']} notes woven · {r['n_links']} links · {r['n_components']} component(s)"
          f" · topology measured on {r.get('topology_generated_at','?')}\n")

    a("## 🔴 To handle (by impact)\n")
    rows = [
        ("Missing links (close notes not connected)", "missing_links", "→ architect: weave"),
        ("Isolated notes (0-1 link)", "isolated", "→ architect: connect"),
        ("Disconnected components (>1)", None, ""),
        ("Odd placement (neighbours from another domain)", "odd_placement", "→ gardener: refile"),
        ("Dead weight (never consulted / useful)", "dead_weight", "→ archivist: archive"),
        ("Challenger doubts (stale/false/contradicted)", "doubts", "→ challenger: settle"),
        ("Heavy overlaps (duplicate?)", "overlaps", "→ gardener: dedupe/contradiction"),
        ("Stale notes (>3 months)", "stale_notes", "→ archivist: check freshness"),
        ("Inconsistent infrastructure paths", "odd_paths", "→ mechanic: fix the infrastructure"),
        ("Dead links", "dead_links", "→ mechanic/gardener"),
        ("Orphans (off the map)", "orphans", "→ gardener: index it"),
        ("Off-map (MEMORY + lessons/INDEX)", "off_index", "→ gardener: index it"),
        ("MEMORY.md above 20 kB", "memory_too_heavy", "→ gardener: lighten the startup map"),
    ]
    for label, key, who in rows:
        n = (r["n_components"] - 1 if key is None and r.get("n_components") else _n(r.get(key)))
        if not n or n <= 0:
            continue
        a(f"- **{label}** : {n} {who}")
    if all((_n(r.get(k)) == 0) for _, k, _ in rows if k) and (r.get("n_components") or 1) <= 1:
        a("- ✅ Nothing outstanding — the trunk is healthy.")

    def section(title, items, fmt, cap=25):
        if not items:
            return
        a(f"\n## {title} ({len(items)})\n")
        for it in items[:cap]:
            a(f"- {fmt(it)}")
        if len(items) > cap:
            a(f"- … et {len(items)-cap} autres (voir state/review.json)")

    section("Stale notes (>3 months)", r["stale_notes"],
            lambda x: f"`{x['note']}` — {x['days']} j ({x['date']})")
    section("Inconsistent infrastructure paths", r["odd_paths"],
            lambda x: f"`{x['note']}:{x['line']}` — {x['type']} — `{x['excerpt']}`")
    section("Isolated notes", r["isolated"], lambda x: f"`{x}`" if isinstance(x, str) else f"`{x.get('note', x)}`")
    section("Odd placement", r["odd_placement"],
            lambda x: f"`{x.get('note', x)}`" if isinstance(x, dict) else f"`{x}`")
    section("Liens manquants", r["missing_links"],
            lambda x: (f"`{x.get('a','?')}` ↔ `{x.get('b','?')}` (sim {x.get('sim','?')})" if isinstance(x, dict) else f"`{x}`"))
    section("Poids mort", r["dead_weight"], lambda x: f"`{x}`")
    section("Challenger doubts", r["doubts"],
            lambda x: f"`{x.get('note','?')}` — {x.get('problem','')[:160]}" if isinstance(x, dict) else f"{x}")

    a("\n---\n*brain_review OBSERVES and PROPOSES; it modifies no note. "
      "Judgement and action belong to the agents (separation of powers).*")
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    if "--stale" not in args:
        _run("brain_topology.py", "--json")
        _run("brain_utility.py", "--json")

    r = build()
    os.makedirs(STATE, exist_ok=True)
    try:
        json.dump(r, open(os.path.join(STATE, "review.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass
    md = to_markdown(r)
    try:
        open(os.path.join(STATE, "review.md"), "w", encoding="utf-8").write(md + "\n")
    except Exception:
        pass

    if "--json" in args:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    elif "--quiet" not in args:
        print(md)
    sys.exit(0)


if __name__ == "__main__":
    main()
