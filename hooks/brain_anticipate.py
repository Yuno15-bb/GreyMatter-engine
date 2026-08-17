#!/usr/bin/env python3
"""brain_anticipate — proactif (Volet 2 · Horizon 4) : le cerveau devance le besoin.

Au lieu d'attendre qu'on l'interroge, il scanne les fiches pour les POINTS DE REPRISE
("RESUME HERE", "NEXT", "resume point"…) and surfaces, by recency, where you
left off and what the next step was — at session start (SessionStart hook)
ou via `brain next`.

Le cerveau qui tend la fiche AVANT qu'on la cherche. Sort toujours 0.
"""
import os, re, sys, glob

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
SKIP_PARTS = (".git", "node_modules", "capsule", "sessions/archive", "corpus", "audits")
# Strong markers (real resume points) then weak ones (generic todos).
# BILINGUAL on purpose: these patterns match what YOU wrote in your own notes,
# not the language of this codebase. Dropping the French forms would silently
# stop surfacing resume points for anyone writing in French.
# Add your own language here — it is a plain list of alternatives.
STRONG = re.compile(r"(RESUME HERE|RESUME POINT|PICK UP HERE|NEXT STEP|LEFT TO DO"
                    r"|REPRENDRE ICI|POINT DE REPRISE|À REPRENDRE|REPRENDRE"
                    r"|PROCHAINE ÉTAPE|RESTE À FAIRE)", re.I)
WEAK = re.compile(r"(TODO|NEXT\b|PROCHAIN[E]?\b|À FAIRE\b)", re.I)


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


def collect():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # skip par SEGMENT de dossier (pas substring : sinon une fiche projet « capsule-… »
        # would be wrongly skipped, missing its resume point). Skip by path SEGMENT, not substring.
        if rel == "MEMORY.md" or any(part in rel.split(os.sep) for part in SKIP_PARTS):
            continue
        zone = rel.split(os.sep)[0]
        if zone not in ("projects",):     # les reprises vivent dans les fiches projet
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
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def main():
    items = collect()[:4]
    mode_hook = "--hook" in sys.argv
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
