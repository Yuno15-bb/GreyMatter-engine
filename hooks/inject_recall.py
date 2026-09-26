#!/usr/bin/env python3
"""inject_recall — UserPromptSubmit hook: recall of relevant memory, ON REQUEST.

The hook runs brain_recall on the request and can inject into context the 2-3 most
relevant notes of the trunk (name + description + path).

⚠️ SINCE 2026-09-09, IT NO LONGER SHOWS ANYTHING ON ITS OWN. The owner's decision, on
measurement: over 30 days, 4.27 % of the notes offered were then opened (139 / 3,256), and
1.95 % over the last 7 days; the other way round, when a note ended up being read, the
suggestion had guessed it 8.8 % of the time. The block cost its noise on every message for a
service rendered 2 to 4 times in 100. August's measurement: 1.98 % — a month without the
slightest improvement.

⚠️ WHAT IS NOT REMOVED, AND MUST NOT BE: the SEARCH. 61 % of the notes actually opened are
not named in MEMORY.md (193 / 495 over 30 days) — with no way to dig, that knowledge becomes
unfindable. Three doors stay open:
  - `./brain recall "my question"` on the command line (unchanged);
  - a keyword in the message (see DEMANDS and MARKER below);
  - BRAIN_RECALL_AUTO=1 in the environment, which restores the old behaviour.

The BM25 computation, however, STILL RUNS on every message (~105 ms, no token): it feeds the
A8.8 instrument `state/query-shape.jsonl` and the held-out channel. Cutting them would have
silently switched off a measurement in progress.

Safeguards:
  - shows ONLY on explicit request, and ONLY when relevance crosses a threshold,
  - silent and non-blocking: always exits 0, injects nothing if anything goes wrong,
  - lightweight: pointers (name/description/path), not full content → minimal token cost.
"""
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall
except Exception:
    recall = None
try:
    from context_usage import read_context_tokens
except Exception:
    def read_context_tokens(_transcript_path):
        return None

TOP_K = 3
MIN_SCORE = 4.0   # below this: not relevant enough → nothing is injected
CONTEXT_WARN_TOKENS = 300_000

# ─── Recall switched to "on request" on 2026-09-09 ─────────────────────────────────────
# The marker is deliberately unpronounceable in everyday language: it cannot fire by
# accident. The phrases are all search REQUESTS — an intent verb is required, never the
# word "brain" alone: that word comes up in a third of the month's reads (the Brain
# talking about itself), it would switch the noise back on exactly where it was densest.
MIN_SCORE_DEMAND = 1.0   # on explicit request we answer even weakly: see clean_query()
MARKER = "?brain"
DEMANDS = (
    "search the brain", "search my notes", "search the notes",
    "look in the brain", "check the brain", "dig in the brain",
    "what does the brain say", "what does the brain know",
    "brain recall", "recall from the brain",
    "any notes on", "any lessons on", "a lesson on",
    "have we seen this before", "did we see this before", "seen this before",
    # BILINGUAL: the French phrasings the engine was first used with, already folded.
    "cherche dans le brain", "cherche dans la memoire", "cherche dans les fiches",
    "fouille le brain", "fouille la memoire",
    "regarde dans le brain", "regarde dans la memoire",
    "que dit le brain", "qu en dit le brain", "qu est ce que dit le brain",
    "rappel brain", "rappelle le brain",
    "une fiche sur", "des fiches sur", "une lecon sur", "des lecons sur",
    "on a deja vu", "on l a deja vu", "deja croise ca",
)


def _fold(s):
    """lowercase, no accents, apostrophes and punctuation brought down to a space.

    Written here rather than imported from brain_recall: detecting the request must
    work even when the recall engine is unreachable, otherwise a failed import would
    silence the keyword without anything saying so.
    """
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9?]+", " ", s)


def explicit_request(prompt):
    """did the author ASK for a search in THIS message?

    ⚠️ THIS FUNCTION NO LONGER ANSWERS "DO WE SHOW" (fixed on 2026-09-20). Until then it
    returned True as soon as `BRAIN_RECALL_AUTO=1`, and that shortcut made the promise
    written everywhere false — "BRAIN_RECALL_AUTO=1 restores the old behaviour". One name
    carried two questions: "do we show?" and "which bar?". The switch answered yes to BOTH,
    so it applied the explicit-request bar (`MIN_SCORE_DEMAND`, 1.0) where the old
    behaviour went up to `MIN_SCORE` (4.0) — four times stricter. Measured that day on a
    two-note corpus: the switch showed a block at 2.69, a score no automatic recall would
    ever have shown before 09/09. Side effect: `MIN_SCORE` only governed a path whose output
    was shown nowhere — a dead constant that looked alive.

    The two questions are now separate: this one says whether the author asked (it picks
    the bar and the query cleaning), `auto_armed()` says whether we may speak without being
    asked. See `un-champ-homonyme-fait-citer-un-chiffre-qui-mesure-autre-chose`: the fault
    is not the number, it is the name that covers two of them.
    """
    p = _fold(prompt)
    if _fold(MARKER) in p:
        return True
    return any(d in p for d in DEMANDS)


def auto_armed():
    """May recall speak WITHOUT being asked?

    This is the reverse gear of the 2026-09-09 cut: it gives back automatic display, never
    the threshold's leniency. An ordinary message is still judged at `MIN_SCORE`, and when
    nothing clears the bar NOTHING happens — not even the "nothing found", reserved for a
    real request. Without that reserve, every message of the day would come back with a
    block, which is exactly the noise that got automatic recall cut.
    """
    return os.environ.get("BRAIN_RECALL_AUTO") == "1"


def clean_query(prompt):
    """Removes the words of the REQUEST before searching.

    Measured on the first try, and it is a real defect, not a precaution: "cherche dans le
    brain railway deploiement github" fell to a score of 3.195 when "railway ne deploie pas
    mon service depuis github" rose to 4.947. The four words of the polite formula count in
    the computation and dilute the real question — the explicit request punished itself,
    and ended up under the threshold.

    BM25 already folds case and accents: handing it the folded version changes nothing to
    its result. The RAW prompt stays intact for the A8.8 instrument.
    """
    p = _fold(prompt)
    p = p.replace(_fold(MARKER), " ")
    for d in DEMANDS:
        p = p.replace(d, " ")
    p = " ".join(p.split())
    return p or _fold(prompt)


def context_notice(data):
    """Warning independent of recall; no error here may ever block the prompt."""
    try:
        used = read_context_tokens((data or {}).get("transcript_path"))
    except Exception:
        return None
    if used is None or used <= CONTEXT_WARN_TOKENS:
        return None
    return (
        f"<context> {used//1000}k tokens — prefer targeted reads, "
        "suggest /clear if the task at hand has changed. </context>"
    )


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    lines = []
    notice = context_notice(data)
    if notice:
        lines.append(notice)

    prompt = (data.get("prompt") or data.get("user_prompt") or "").strip()
    requested = explicit_request(prompt)
    # `requested` picks the BAR and the cleaning; `show` picks the SPEECH.
    show = requested or auto_armed()

    # Keep the engine label in state logs for existing readers.
    choice = {"moteur": "v2"}

    results = []
    _bm25 = None                       # kept for the A8.8 instrumentation (query shape)
    query = clean_query(prompt) if requested else prompt
    threshold = MIN_SCORE_DEMAND if requested else MIN_SCORE
    if len(prompt) >= 8:
        if recall is not None:
            try:
                _bm25 = recall.BM25(recall.load_corpus())
                raw = _bm25.search(query, TOP_K)
            except Exception:
                raw = []
            results = [(s, d) for s, d in raw if s >= threshold]

    if results and show:
        lines += ["<brain-recall> Notes from your trunk that may be relevant "
                  "for this request (read them if useful, ignore otherwise):"]
        for s, d in results:
            desc = (" — " + d["desc"][:120]) if d["desc"] else ""
            lines.append(f"- {d['name']} ({d['path']}){desc}")
        lines.append("</brain-recall>")
    elif requested:
        # Without this line, an empty search and an unrecognised keyword look exactly
        # alike — the author would not know which of the two just happened.
        lines.append("<brain-recall> Nothing relevant found in your trunk for "
                     "this request. </brain-recall>")

    # a UserPromptSubmit hook's stdout = context added to the session
    if lines:
        print("\n".join(lines))

    # truth loop: log what was SURFACED (so usefulness can be measured).
    # ⚠️ Only what was actually shown is logged: writing proposals nobody saw would skew
    # the open rate (the denominator would swell without the note ever having had its
    # chance to be read) and feed recall_feedback.py's utility bonus with ghost lines.
    if results and show:
        try:
            import time
            sid = data.get("session_id") or ""
            log = os.path.join(recall.BRAIN, "state", "recall_log.jsonl")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                for s, d in results:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid,
                                        "path": d["path"],
                                        "score": round(s, 2) if s is not None else None,
                                        "moteur": choice["moteur"]},
                                       ensure_ascii=False) + "\n")
        except Exception:
            pass

    log_shape(query, _bm25, bool(results), choice, data.get("session_id") or "",
              bool(results) and show, threshold, requested)
    capture_heldout(prompt, _bm25, data)


def _project_dir(path):
    """How Claude Code names a working directory's transcript folder: `/` and `.` → `-`."""
    return re.sub(r"[/.]", "-", os.path.realpath(path))


def capture_heldout(prompt, bm25, data):
    """EVALUATION channel, separate from A8.8 and OFF by default.

    Does nothing as long as the out-of-git `tests/heldout/` protocol does not exist. Once
    armed, it captures the first N ELIGIBLE queries that come along — consecutive, without
    choosing — then stops on its own. Consecutiveness must be mechanical: capturing "by
    hand" amounts to keeping what looks interesting, hence distorting the very distribution
    we want to discover.

    ⚠️ This channel keeps the TEXT, in tests/heldout/ (JSON, out of the corpus, gate P1).
    `state/query-shape.jsonl` stays free of any text. The two never mix.
    The capture module and its protocol are the owner's evaluation tooling, kept out of
    git: in a fresh install the import fails and this function costs nothing.
    """
    if bm25 is None or recall is None:
        return
    try:
        sys.path.insert(0, os.path.join(recall.BRAIN, "tests", "heldout"))
        import capture_heldout as ch
        if not os.path.exists(ch.PROTOCOLE):
            return                                   # not armed: nothing, at no cost
        if len(bm25.rank(prompt, 2)) < 2:
            return                                   # no rank1/rank2 gap to compute
        tp = data.get("transcript_path") or ""
        # An agent works from inside the trunk, the author from their home folder.
        kind = ("agent" if _project_dir(recall.BRAIN) in tp else
                "human" if _project_dir(os.path.expanduser("~")) in tp else "other")
        ch.capturer(prompt, data.get("session_id") or "", kind)
    except Exception:
        pass


def log_shape(query, bm25, injected, choice, sid, shown=False,
              threshold=None, requested=False):
    """A8.8 — records the SHAPE of the query, never its text. See hooks/forme_requete.py.

    Logs even when NOTHING was injected: knowing which shapes trigger nothing is part of
    the distribution we are trying to learn.
    Best-effort and silent: this hook must never make a prompt fail.

    ⚠️ THE LOG RECORDS ITS RULE, NOT ONLY ITS MEASUREMENT (fixed on 2026-09-19). Until
    then the line carried `s1` (the best score seen) and `injected` ("there was a candidate
    above the threshold"), but NEVER the threshold itself — while there are two,
    `MIN_SCORE` at 4.0 in automatic mode and `MIN_SCORE_DEMAND` at 1.0 on explicit request.
    The same field name thus covered two different rules, chosen by a variable written
    nowhere: a line `injected: false, s1: 2.5` is unreadable without knowing whether the bar
    was at 4.0 or 1.0. It is the homonymy defect of
    `un-champ-homonyme-fait-citer-un-chiffre-qui-mesure-autre-chose`, applied no longer to a
    field name but to the invisible rule behind it. `threshold` and `requested` are now
    written on every line; their ABSENCE dates a line from before 09/19.

    ⚠️ THE MEASUREMENT NOW BEARS ON WHAT WAS REALLY SEARCHED. This pass scored the raw
    `prompt` while production scored `clean_query(prompt)` on an explicit request: `s1` and
    `injected` did not come from the same text. No effect on the 1,809 automatic lines
    (where both are identical), a real fix on the 10 explicit-request lines of the log as
    of 09/19.
    """
    if bm25 is None or recall is None:
        return
    try:
        import time
        from forme_requete import mesurer
        # SEPARATE pass, at k=10: production keeps its k=3 intact. The engine is already
        # built and indexed, so this second ranking only costs the scoring again.
        records = bm25.rank(query, 10)
        shape = mesurer(recall.tokenize(query), records, k=10)
        # `injected` keeps its original meaning — "the engine had a candidate above the
        # threshold" — so the A8.8 series stays comparable on both sides of 2026-09-09.
        # The `shown` field says what was really displayed.
        shape.update(ts=int(time.time()), sid=sid, injected=injected,
                     shown=shown, moteur=choice.get("moteur"),
                     threshold=threshold, requested=requested)
        path = os.path.join(recall.BRAIN, "state", "query-shape.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(shape, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
