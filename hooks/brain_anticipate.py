#!/usr/bin/env python3
"""brain_anticipate — proactive (Part 2 · Horizon 4): the brain gets ahead of the need.

Instead of waiting to be asked, it scans the notes for RESUME POINTS
("RESUME HERE", "NEXT", "resume point"…) and surfaces, by recency, where you
left off and what the next step was — at session start (SessionStart hook)
or through `brain next`.

The brain that hands you the note BEFORE you look for it. Always exits 0.
"""
import os, re, sys, glob, subprocess

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
SKIP_PARTS = (".git", "node_modules", "capsule", "sessions/archive", "corpus", "audits")
# Notes NEVER candidates, whatever the file system's case sensitivity.
# PROJECT-STATUS.md is a generated DASHBOARD, not a working note: it contains
# "what to pick up", so it detects itself and squats first place (2026-08-13).
# Same status as MEMORY.md.
EXCLUS_TOUJOURS = frozenset(("memory.md", os.path.join("projects", "project-status.md").lower()))
# Strong markers (real resume points) then weak ones (generic todos).
# BILINGUAL on purpose: these patterns match what YOU wrote in your own notes,
# not the language of this codebase. Dropping the French forms would silently
# stop surfacing resume points for anyone writing in French.
# Add your own language here — it is a plain list of alternatives.
STRONG = re.compile(r"(RESUME HERE|RESUME POINT|PICK UP HERE|NEXT STEP|LEFT TO DO"
                    r"|REPRENDRE ICI|POINT DE REPRISE|À REPRENDRE|REPRENDRE"
                    r"|PROCHAINE ÉTAPE|RESTE À FAIRE)", re.I)
# ⚠️ A BARE "À FAIRE" CATCHES ORDINARY FRENCH. The pattern was `À FAIRE\b`: it matched an
# ordinary sentence using "à faire" as a verb, and a note saying "SETTLED, nothing left to
# do" carried the resume badge ↻ for it. A weak marker counts only when it is PRESENTED as
# one: at the start of a line, in a heading, in a bullet, or followed by a colon.
# ⚠️ A BARE "PROCHAIN(E)" IS THE SAME TRAP, and it weighed more. Measured on 2026-08-15 on
# `projects/**`: 41 hits on ordinary French ("the next note", "next time") against 24 markers
# really presented as a task. The detector was mostly noise — and since `graph_export.py`
# imports it, that noise also lit the planet's ↻ badges, which saturated at 31.
# ("RESTE À FAIRE" and "PROCHAINE ÉTAPE" are still caught by STRONG, which runs first.)
# BILINGUAL on purpose, like STRONG above.
WEAK = re.compile(r"(TODO\b|NEXT\b"
                  r"|PROCHAIN[E]?\s*[:：]"
                  r"|^[ \t]*(?:[#>\-*•]+[ \t]*)*PROCHAIN[E]?\b"
                  r"|À FAIRE\s*[:：]"
                  r"|^[ \t]*(?:[#>\-*•]+[ \t]*)*À FAIRE\b)", re.I | re.M)
# How many resume points are put forward. ONE number for the whole system: the session
# start message reads it, and so does the planet's ↻ badge (`graph_export.py`) —
# otherwise the map lights points the Brain does not offer, and the reverse.
TOP_REPRISES = 4


def _line_of(text, m):
    """The whole line carrying the marker."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    return text[start: end if end != -1 else len(text)]


# BILINGUAL on purpose: the markers above are, so their negations must be. The notes are
# the user's, in the user's language.
NEGATED = re.compile(
    r"(n'est plus|n’est plus|ne sont plus|plus un\b|plus de\b|aucun\b|"
    # "plus rien à faire": the marker matched is "à faire", so the "à" is INSIDE the match
    # and the preceding window ends at "rien" alone — "rien à" could never match it. A
    # negation pattern has to be written against the marker it cancels, not against the
    # sentence as one imagines it.
    r"rien à\b|rien\b|pas de\b|jamais de\b"
    r"|no longer\b|nothing left\b|nothing\b|none\b|not a\b|never\b)", re.I)


def _cancelled(text, m):
    """Two ways a marker is not one — both observed on real notes.

    1. STRUCK THROUGH (`~~pick up here~~`): a headstone, not a task. A note marked
       abandoned in the morning came back at the top of the resume list that evening.
    2. NEGATED ("this is no longer something left to do"): writing that a thing is closed
       made it be detected as open. A note closed by an explicit decision offered itself
       as the next task, quoting the very sentence that said the opposite.

    The BEST-WRITTEN note is the one that suffered most, which is what makes this filter
    non-negotiable rather than a nicety.
    """
    line = _line_of(text, m)
    if "~~" in line:
        return True
    # A MARKDOWN TABLE CELL is data, never a task. Measured on a 492-note trunk: table
    # cells are 6% of all detections but were HALF of the four lines actually injected,
    # because the list is ordered by recency and recent notes are the ones with tables.
    # The clearest case was a note documenting the "resume badge lit on everything"
    # problem, whose own comparison table made it light the badge again.
    if line.lstrip().startswith("|"):
        return True
    before = line[: m.start() - (text.rfind("\n", 0, m.start()) + 1)]
    # The last 4 WORDS, not the last 40 characters: a negation bears on what immediately
    # follows it. Too wide a window and "Fixed lot A; LEFT TO DO: lot B" is cancelled by
    # mistake; too narrow and the weak marker of a sentence whose strong marker was already
    # cancelled slips back underneath.
    return bool(NEGATED.search(" ".join(before.split()[-4:])))


def best_marker(text):
    """Prefer a STRONG marker; fall back to a weak one. Takes the LAST occurrence
    (resume points usually sit at the end of a note), skipping cancelled ones."""
    for pattern in (STRONG, WEAK):
        hits = [m for m in pattern.finditer(text) if not _cancelled(text, m)]
        if hits:
            return hits[-1]
    return None


def snippet(text, m):
    """~160 characters around the marker, on a single line."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    if end == -1:
        end = len(text)
    line = text[start:end].strip()
    return re.sub(r"\s+", " ", line)[:180]


class CapabiliteIndisponible(Exception):
    """git missing, or trunk outside a repository: ranking resume points is IMPOSSIBLE.

    Never a silent fallback on `mtime`. A mute fallback would return a plausible,
    false list — exactly the false nominal the Brain forbids itself. The caller must
    SAY that the capability is missing, not offer something else.
    """


class TrunkNotVersioned(CapabiliteIndisponible):
    """The trunk is not under git. On this engine that is a legitimate CHOICE, not a
    breakdown: brain_doctor reports it, with the command that turns git on. As a hook,
    it is therefore not repeated in every session — a permanent line nobody can act on
    from inside the conversation is noise. `brain next` still says it."""


def _dates_git(racine):
    """{relative path -> timestamp of the last commit that touched it}.

    ONE sweep for the whole repository (measured on 20/08: 66 ms, 2147 paths), not
    one `git log` per note. `git log` being newest-first, the FIRST date seen for a
    path is the most recent one.
    """
    try:
        r = subprocess.run(["git", "-C", racine, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        raise CapabiliteIndisponible("git not found: %s" % e)
    if r.returncode != 0 or r.stdout.strip() != "true":
        raise TrunkNotVersioned("%s is not a git repository" % racine)
    r = subprocess.run(["git", "-C", racine, "log", "--format=@%ct", "--name-only",
                        "--no-renames", "-z", "HEAD"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise CapabiliteIndisponible("git log failed: %s" % r.stderr.strip()[:120])
    out, ts = {}, None
    for champ in r.stdout.split("\0"):
        for ligne in champ.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                continue
            if ligne.startswith("@"):
                ts = int(ligne[1:])
            elif ts is not None:
                out.setdefault(ligne, ts)
    return out


def collect():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # Skip by folder SEGMENT, not substring: otherwise a project note named
        # "capsule-…" would be wrongly skipped, missing its resume point.
        # PROJECT-STATUS.md is a generated DASHBOARD, not a working note: it contains
        # "what to pick up", so it detected itself and squatted first place (2026-08-13).
        # ⚠️ CASE-INSENSITIVE COMPARISON (2026-08-20). It was literal, and
        # `planet/graph.json` carried `projects/project-status.md` while the disk carried
        # `PROJECT-STATUS.md`: on a case-insensitive file system, the same note has two
        # spellings and the exclusion misses one. The dashboard then lit up again among
        # the resume points it summarises.
        if rel.lower() in EXCLUS_TOUJOURS \
                or any(part in rel.split(os.sep) for part in SKIP_PARTS):
            continue
        zone = rel.split(os.sep)[0]
        if zone not in ("projects",):     # resume points live in project notes
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        m = best_marker(txt)
        if m:
            name = re.search(r"^name:\s*(.+)$", txt, re.M)
            out.append({"path": rel, "mtime": os.path.getmtime(p),
                        "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
                        "reprise": snippet(txt, m)})
    # ── THE RANKING (2026-08-20) ──────────────────────────────────────────────
    # `mtime` was the key until then. It is a property of the FILE SYSTEM, not of the
    # knowledge: a `git clone`, a `checkout`, a `stash pop` or an `rsync` rewrite it
    # wholesale. MEASURED on 20/08: on a fresh clone, the 60 candidates share a single
    # mtime — the top 4 became an arbitrary tie-break, and the planet's ↻ badge (a
    # SNAPSHOT) could no longer agree with what the session start offers (a RECOMPUTE).
    #
    # So the key is the date of the last commit that touched the note: it describes the
    # VERSIONED state, it travels with the repository, and maintenance that changes
    # nothing does not move it. Tie-break declared BEFORE measuring: ascending path.
    # A candidate git does not track has no date: it comes after all the others, never
    # quietly tie-broken by its mtime. `mtime` stays in each entry — `etat_projets.py`
    # uses it to show an age in days.
    dates = _dates_git(BRAIN)
    out.sort(key=lambda x: (0 if dates.get(x["path"]) is not None else 1,
                            -(dates.get(x["path"]) or 0),
                            x["path"]))
    return out


def main():
    mode_hook = "--hook" in sys.argv
    try:
        items = collect()[:TOP_REPRISES]
    except CapabiliteIndisponible as e:
        if mode_hook and isinstance(e, TrunkNotVersioned):
            return
        # A missing capability is SAID. Keeping quiet here would amount to announcing
        # "no pending resume point", which is a plausible and false answer.
        sortie = ("<brain-resume> Resume points unavailable: %s </brain-resume>"
                  if mode_hook else "🧭 Resume points unavailable: %s")
        print(sortie % e)
        return
    if not items:
        # As a HOOK, say nothing: an empty trunk must not add a line to every
        # prompt. As a COMMAND, say so — `brain next` is a display command, and
        # a display command that prints nothing cannot be told apart from a
        # broken one. That silence is exactly what selftest §8 goes red on, on
        # a brand-new trunk where having no resume point is the normal state.
        if not mode_hook:
            print("🧭 No pending resume point.")
        return
    if mode_hook:
        print("<brain-resume> Pending resume points (from your project notes, "
              "newest first) — offer to continue if relevant:")
    else:
        print("🧭 Pending resume points:\n")
    for it in items:
        if mode_hook:
            print(f"- {it['name']} ({it['path']}): {it['reprise']}")
        else:
            print(f"  • {it['name']}  ({it['path']})")
            print(f"      ↳ {it['reprise']}")
    if mode_hook:
        print("</brain-resume>")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
