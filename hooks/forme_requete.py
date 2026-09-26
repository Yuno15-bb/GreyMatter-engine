#!/usr/bin/env python3
"""forme_requete — characterise a query WITHOUT keeping its text (work item A8.8).

WHY. A8.7 showed that the utility bonus wins on very short queries (a two-word title
produces bundles of ties where the lexical score has nothing left to say) and loses on
questions (where the lexical gap is clear-cut). Impossible to settle: `recall_log.jsonl`
records ONLY the notes offered, never the shape of the request. So nobody knows which
of the two distributions looks like real use.

WHAT IS RECORDED — numbers, and nothing else:
  n_tokens · n_unique · length_class · s1 · s2 · gap_abs · gap_rel · k
  ties: {"1%": n, "2%": n, "5%": n, "10%": n} — a grid, not a threshold chosen in advance

WHAT NEVER IS. No raw text, no lexical fragment, no token, no hash — not even a
non-reversible one. The reason is not only privacy: the Brain has already destroyed one of
its own witnesses by copying an evaluation query into a note (see
utilite-boucle-popularite-2026-08-19, § "Why this note does not quote the question").
A journal holding the text of the queries would be the same fault, only worse.

⚠️ WHAT STILL LEAKS, and it has to be said: the `s1`/`s2` scores are the corpus's.
Someone who holds the corpus can, for a given score, narrow down the set of possible
queries. It is not a reconstruction of the text, but it is not zero either.
"""

# A GRID of tolerances, not a single threshold. The 2026-08-20 calibration showed that a
# single 2% threshold missed the very case that motivates the measure: the query "claude
# brain" has its first four candidates spread over ~3%, so counted as NOT tied. Picking
# the threshold now would amount to deciding in advance what we are trying to measure — the
# fault work item A8.4 already caught once (the whole grid, never a sorted threshold).
TOLERANCES_EXAEQUO = (0.01, 0.02, 0.05, 0.10)

_CLASSES = ((2, "1-2"), (5, "3-5"), (10, "6-10"), (float("inf"), ">10"))


def classe_longueur(n):
    for borne, nom in _CLASSES:
        if n <= borne: return nom
    return ">10"


def mesurer(tokens, records, k=10):
    """tokens: the already-tokenised list (never kept). records: output of
    BM25.classer(), of which only the scores are read. Returns a dict of NUMBERS."""
    n = len(tokens)
    out = {"n_tokens": n, "n_unique": len(set(tokens)), "length_class": classe_longueur(n),
           "k": k}

    # pure LEXICAL gap: re-sort on bm25, without the utility factor or exploration,
    # otherwise we would be measuring the very effect we are trying to investigate.
    lex = sorted((r.get("bm25", 0.0) for r in records), reverse=True)[:k]
    if not lex: return {**out, "s1": None, "s2": None, "gap_abs": None,
                        "gap_rel": None, "ties": {f"{t:.0%}": 0 for t in TOLERANCES_EXAEQUO}}
    s1 = lex[0]; s2 = lex[1] if len(lex) > 1 else None
    out["s1"] = round(s1, 3)
    out["s2"] = round(s2, 3) if s2 is not None else None
    out["gap_abs"] = round(s1 - s2, 3) if s2 is not None else None
    out["gap_rel"] = round((s1 - s2) / s1, 4) if s2 is not None and s1 else None
    out["ties"] = {f"{tol:.0%}": sum(1 for s in lex if s1 and s >= s1 * (1 - tol))
                      for tol in TOLERANCES_EXAEQUO}
    return out
