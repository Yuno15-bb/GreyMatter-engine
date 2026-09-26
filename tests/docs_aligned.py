#!/usr/bin/env python3
"""docs_aligned — does the prose still describe the code it claims to describe?

WHY THIS EXISTS
    Documentation does not rot loudly. It keeps rendering, keeps reading well,
    and quietly describes a program that no longer behaves that way. On
    2026-08-15 the hover panel of the planet stopped listing a note's
    connections (they moved to the click). `docs/planet.md` went on saying
    "point at a note: its links light up... connections sit at the end of the
    panel" — true the day it was written, false the day it was read. Nothing in
    the repository could tell the difference: no test covers prose.

WHAT IT MEASURES — AND WHAT IT DELIBERATELY DOES NOT
    It does NOT read the prose and does NOT try to judge whether a sentence is
    true. That would need a model, and a check that needs a model to decide is
    not a check.

    It measures one mechanical fact: **has the code a document claims to
    describe changed since that document was last touched?** If yes, the prose
    is not proven wrong — it is proven UNREVIEWED. That is a fact a script can
    establish, and it is exactly the fact nobody notices by hand.

    Baseline: the last commit that edited the document itself. Self-starting —
    no stamp to remember, no registry to keep in sync with reality. Re-aligning
    is not a command to run: you edit the document (or, if the prose was already
    correct, you touch it and say so in the commit message). Editing the doc is
    the whole point.

USAGE
    python3 tests/docs_aligned.py            report; exit 1 if a doc is behind
    python3 tests/docs_aligned.py --quiet    exit code only, for publish.sh
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVERAGE = os.path.join(ROOT, "docs", "_coverage.json")


def git(*args):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def last_commit_touching(paths):
    out = git("log", "-1", "--format=%H", "--", *paths)
    return out or None


def commits_since(sha, paths):
    if not sha:
        return []
    out = git("log", "--oneline", f"{sha}..HEAD", "--", *paths)
    return [l for l in out.splitlines() if l.strip()]


# ── Section 2: a COUNT written in prose, checked against the code ──────────────
#
# The freshness check above is deliberately blind to what a sentence SAYS. That
# leaves one failure it cannot see: a number frozen into the prose. On 2026-09-20
# `docs/design-doc.md` read "CLI, 18 subcommands" and listed them — it had said
# "17" since the day `brain review` was added, and no commit to the CLI had made
# it red, because the doc had been edited for other reasons since. A count is the
# rare prose claim a script CAN verify, so it is verified here.
#
# Each entry names: the document, the regex that reads the claim out of it, and a
# function that reads the same fact out of the code. Adding the next one is three
# lines. Keep them to facts with a single mechanical source — a count that needs
# judgement to compute does not belong here, it belongs in the freshness section.

def _cli_verbs():
    """The verbs the CLI itself advertises, read from its own Usage: line."""
    with open(os.path.join(ROOT, "brain"), encoding="utf-8") as f:
        for line in f:
            m = re.search(r"Usage: brain <([^>]+)>", line)
            if m:
                return [v.strip() for v in m.group(1).split("|") if v.strip()]
    return []


def _doc_cli_verbs(text):
    """The verbs design-doc.md claims, and the number it puts in front of them."""
    m = re.search(r"CLI, (\d+) subcommands \(", text)
    if not m:
        return None, []
    tail = text[m.end():]
    listed = tail[:tail.index(")")] if ")" in tail else ""
    listed = re.sub(r"[#\n]", " ", listed)
    return int(m.group(1)), [v.strip() for v in listed.split("|") if v.strip()]


COUNTS = [
    ("docs/design-doc.md", "the CLI's subcommands", _doc_cli_verbs, _cli_verbs),
]


def check_counts():
    """Returns (agreements, disagreements) — each a list of printable lines."""
    good, bad = [], []
    for doc, what, read_doc, read_code in COUNTS:
        path = os.path.join(ROOT, doc)
        if not os.path.isfile(path):
            bad.append(f"{doc} — the document is missing, so its count of {what} cannot be checked")
            continue
        with open(path, encoding="utf-8") as f:
            claimed_n, claimed = read_doc(f.read())
        real = read_code()
        if claimed_n is None:
            bad.append(f"{doc} — no longer states a count of {what}; either restore it or drop this entry")
            continue
        if not real:
            bad.append(f"{doc} — the code side of {what} read nothing; the reader is broken, not the doc")
            continue
        if claimed_n != len(claimed):
            bad.append(f"{doc} — says {claimed_n} for {what} but lists {len(claimed)} of them")
        elif set(claimed) != set(real):
            missing = sorted(set(real) - set(claimed))
            extra = sorted(set(claimed) - set(real))
            detail = []
            if missing:
                detail.append("absent from the doc: " + ", ".join(missing))
            if extra:
                detail.append("in the doc only: " + ", ".join(extra))
            bad.append(f"{doc} — {what}: the code has {len(real)}, the doc {claimed_n} · " + " · ".join(detail))
        else:
            good.append(f"{doc} — {what}: {len(real)}, and the same names on both sides")
    return good, bad


def main():
    quiet = "--quiet" in sys.argv
    if not os.path.isfile(COVERAGE):
        print(f"⛔ no coverage registry ({COVERAGE}) — every doc is unwatched.")
        return 1
    with open(COVERAGE, encoding="utf-8") as f:
        registry = json.load(f)

    behind, unwatched, ok = [], [], []
    for doc, entry in sorted(registry.get("docs", {}).items()):
        sources = entry.get("documents", [])
        if not os.path.isfile(os.path.join(ROOT, doc)):
            unwatched.append((doc, "the document itself is missing"))
            continue
        missing = [s for s in sources if not os.path.exists(os.path.join(ROOT, s))]
        if missing:
            # A path that no longer exists means the registry points at nothing:
            # the check would pass forever while watching a hole. Loud, not silent.
            unwatched.append((doc, "watches a path that no longer exists: " + ", ".join(missing)))
            continue
        base = last_commit_touching([doc])
        if not base:
            unwatched.append((doc, "never committed — no baseline to compare against"))
            continue
        newer = commits_since(base, sources)
        (behind if newer else ok).append((doc, newer))

    # Every doc under docs/ must be in the registry, or a new one escapes the net
    # the day it is written — the failure mode this whole file exists to prevent.
    docs_dir = os.path.join(ROOT, "docs")
    on_disk = {f"docs/{n}" for n in os.listdir(docs_dir)
               if n.endswith(".md") and not n.startswith("_")} if os.path.isdir(docs_dir) else set()
    orphans = sorted(on_disk - set(registry.get("docs", {})))
    counts_ok, counts_ko = check_counts()

    if not quiet:
        print(f"📄 docs_aligned — {len(on_disk)} document(s) under docs/")
        for doc, _ in ok:
            print(f"  ✅ {doc}")
        for doc, why in unwatched:
            print(f"  ⛔ {doc} — {why}")
        for doc, newer in behind:
            print(f"  ⚠️  {doc} — {len(newer)} commit(s) to the code it describes "
                  f"since the doc was last edited:")
            for line in newer[:8]:
                print(f"        {line}")
            if len(newer) > 8:
                print(f"        … and {len(newer) - 8} more")
        for doc in orphans:
            print(f"  ⛔ {doc} — not in docs/_coverage.json, so nothing watches it")
        for line in counts_ok:
            print(f"  ✅ {line}")
        for line in counts_ko:
            print(f"  ⚠️  {line}")
        if not (behind or unwatched or orphans or counts_ko):
            print("  Every document has been reviewed since the code it describes last moved.")
        else:
            print("\n  → open the document, check the claim, edit it. The commit that edits it "
                  "is the new baseline; there is no stamp to run.")

    return 1 if (behind or unwatched or orphans or counts_ko) else 0


if __name__ == "__main__":
    sys.exit(main())
