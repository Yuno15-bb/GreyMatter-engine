#!/usr/bin/env python3
"""
english_only.py — guards the ONE thing nothing else watches: the translation.

`main` is English, `fr` is the French source, and the step between them is a
human reading a diff. That step has already failed four times in the open:
`brain status` answering "(pas de statut)", `brain review` answering "aucune
paire en attente", `brain selftest` printing "hors-tronc", and the planet
labelling a panel "⚠ avis du challenger" — each of them on a screen a user
looks at, each shipped in a release.

WHAT IT CHECKS, AND WHAT IT DELIBERATELY DOES NOT. Only text a USER can see:
string literals and HTML content. Not comments — the README says plainly that
hook comments are still being translated, and a check that fails on a known,
declared state is a check people learn to ignore.

SOME FRENCH IS THE FEATURE. Several patterns match the USER's notes, not this
codebase: resume-point markers, the challenger's verdicts, the tokenizer's
letter class. Dropping their French would quietly stop serving anyone who
writes in French. Those lines opt out where they live — an `i18n-ok` on the
line, or the word BILINGUAL in the comment just above — so the reason travels
with the code instead of rotting in a list at the top of this file.

The signal is the French accent. It is nearly absent from English (café, résumé
— both listed as allowed below), and it is present in almost every French
sentence long enough to be a UI string. A word list would be endless and would
false-positive on "la", "on", "site"; accents are cheap and precise.

Run: python3 tests/english_only.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACCENTS = "àâäçéèêëîïôöùûüÿœÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒ"

# Files whose French is the subject, not a leak.
SKIP_FILES = {
    "docs/translation.md",   # documents the fr branch, quotes it
    "sync.sh",               # reads the author's living, French Brain
    "rules.json",            # the French→English rules themselves
    "generalize.py",         # ships the French patterns it rewrites
    "leakcheck.py",          # French markers are what it hunts for
    "tests/leakcheck_fixtures.py",  # its counter-proof: same markers, same reason
    "tests/english_only.py",
}
SKIP_DIRS = {".git", "node_modules", "docs/media", "planet/media", "skeleton", "demo"}

# English words that legitimately carry an accent.
ALLOWED = re.compile(r"\b(caf[ée]|r[ée]sum[ée]|na[ïi]ve|expos[ée]|clich[ée])\b", re.I)

# A user-visible string: quoted literal, or text between HTML tags.
PATTERNS = [
    re.compile(r"'([^'\\\n]{4,})'"),
    re.compile(r'"([^"\\\n]{4,})"'),
    # BACKTICKS (2026-08-15). Absent until now, and the planet's top bar is built
    # from template literals: `◉ ${region} EN VOLUME — glisser pour tourner` sat in
    # the published English branch, unreachable by every pattern above. A checker
    # that cannot see the syntax the code is written in reports on a smaller
    # program than the one that ships.
    re.compile(r"`([^`\\\n]{4,})`"),
    re.compile(r">([^<>{}\n]{4,})<"),
]

EXTS = {".py", ".sh", ".js", ".html", ".md", ""}


def visible_strings(text):
    for pat in PATTERNS:
        for m in pat.finditer(text):
            yield m.group(1)


def strip_comments(text, suffix):
    """Comments are out of scope — see the module docstring.

    ⚠️ `.html` USED TO FALL THROUGH HERE, AND IT MATTERED (fixed 2026-08-15).
    An HTML page carries its script and its style inline, so its `//` and `/* */`
    comments were scanned like content. That is not a small over-reach: French
    contractions put an apostrophe mid-comment (« qu'elles », « l'écran »), and
    the `'([^'\\n]{4,})'` pattern happily reads the text BETWEEN two of them as a
    string literal. Measured on the planet: 95 findings, of which the large
    majority were phantom strings cut out of French prose — every one of them
    starting right after an apostrophe.
    A checker that reports mostly noise gets silenced, not obeyed. It has to
    measure what its own docstring claims it measures.

    Only whole comment lines go: `const s = 'texte'; // note` does NOT start with
    `//`, so it is still scanned and a real string on it is still caught.
    """
    if suffix in (".py", ".sh", ""):
        # DOCSTRINGS TOO (2026-08-15). A docstring is a comment that happens to be
        # a string literal, and the README states plainly that hook comments stay
        # French. The accent rule never reached them by luck — most carry an accent
        # somewhere and were already being skipped for other reasons; the moment the
        # accent-free rule below landed, one unaccented French docstring surfaced as
        # a "user-visible string". It is not visible to any user.
        # Blanked via `ast`, not a regex: a regex for triple quotes trips over the
        # quotes inside them, and would silently eat half a file.
        if suffix == ".py":
            try:
                import ast
                arbre = ast.parse(text)
                lignes = text.splitlines()
                for noeud in ast.walk(arbre):
                    if not isinstance(noeud, (ast.Module, ast.FunctionDef,
                                              ast.AsyncFunctionDef, ast.ClassDef)):
                        continue
                    corps = getattr(noeud, "body", None)
                    if not corps or not isinstance(corps[0], ast.Expr):
                        continue
                    val = corps[0].value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        for i in range(val.lineno - 1, val.end_lineno):
                            if i < len(lignes):
                                lignes[i] = ""
                text = "\n".join(lignes)
            except SyntaxError:
                pass          # un fichier qui ne compile pas : on le scanne tel quel
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    if suffix in (".js", ".html", ".css"):
        # blocs d'abord (ils enjambent les lignes), lignes ensuite
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
        # INLINE `//` TOO, not just whole comment lines (2026-08-15). Leaving them
        # in was survivable while the only signal was an accent; the accent-free
        # rule turned them into a noise source overnight — `// Y = la rotation du
        # globe, X = l'inclinaison` was reported as a user-visible string, cut out
        # of a comment between two apostrophes.
        # `(?<!:)` spares `https://`, the one `//` that is never a comment. A real
        # string followed by a comment keeps its string: only what comes AFTER the
        # slashes is dropped.
        text = re.sub(r"(?<!:)//[^\n]*", " ", text)
        return text
    return text


# ── French WITHOUT accents — the hole the accent rule cannot see ────────────────
# The accent signal is cheap and precise, and it is blind to a whole class of real
# leaks. Measured on 2026-08-15: the planet shipped `◉ 3D — S pour le sens` and
# `glisser pour tourner` to the public branch. Not one accented character; the
# check said "no French left" while a French sentence sat in the top bar of the
# published product. The failure had even been written down beforehand — "French
# WITHOUT accents, invisible to the heuristic" — and the checker still had the gap.
#
# Function words, not vocabulary: a content-word list is endless and dates. These
# are the joints of the language, and they cannot be avoided in a real sentence.
#
# TWO of them, in the same string. One alone false-positives on things that are
# not prose at all — `sans-serif` in CSS, a `pour` inside a URL, a variable named
# `les`. Two distinct joints is what a SENTENCE has and a token does not.
FR_MOTS = {
    # articles and short joints — the ones a sentence cannot do without
    "le", "la", "les", "des", "du", "au", "aux", "une", "ce", "cet", "cette",
    "se", "ne", "il", "ils", "elle", "elles", "nous", "vous", "leur",
    # prepositions and connectives
    "pour", "dans", "avec", "sans", "vers", "chez", "sous", "entre", "pendant",
    "depuis", "avant", "apres", "parce", "quand", "comme", "ainsi", "donc",
    "alors", "puis", "mais", "aussi", "encore", "jamais", "toujours", "ici",
    # verbs and pronouns that carry a sentence
    "est", "sont", "qui", "que", "quoi", "tout", "tous", "toute",
    "rien", "peut", "faut",
    # UI infinitives — this checker looks at INTERFACE strings, and an interface
    # in French says these. A general vocabulary list would be endless; the verbs
    # a button or a hint can use are not.
    "glisser", "cliquer", "tourner", "ressortir", "entrer", "sortir", "afficher",
    "charger", "ouvrir", "fermer", "revenir", "choisir", "valider", "annuler",
    "enregistrer", "supprimer", "rechercher", "relancer", "reprendre", "lancer",
    # and the nouns an interface of THIS product says, none of them English
    "clair", "fiche", "fiches", "lien", "liens", "survol", "panneau", "amas",
    "tronc", "reglage", "reglages", "accueil", "retour", "aide", "essai",
    "chargement", "toi", "moi",
    # « vue d'ensemble » — the planet's breadcrumb carried it into the English
    # product. Both words are ordinary on their own ("ensemble" is English), so
    # they belong HERE, where two are needed, and never in the single-word list.
    "vue", "ensemble",
}
# DELIBERATELY ABSENT: "en", "on", "sur", "un", "et", "a", "plus". Every one of them is an
# ordinary English word or a common attribute value (`lang="en"`), and one false
# positive in a checker like this is worth more than one miss: a report full of
# noise gets silenced, and then the real leak goes out with it.
# SINGLE WORDS THAT SETTLE IT ON THEIR OWN. The two-word rule cannot see a French
# LABEL — one word in a chip, a header, a button — and that is not a corner case:
# the planet shipped `connexions (12)` as the heading of the panel's link list, one
# letter away from the English word, on the English branch. These are words whose
# French spelling is not an English word at all, so a single occurrence is proof.
# Keep the list SHORT and only add a word when its English spelling differs — a
# word that exists in both languages belongs in the two-word rule, never here.
FR_SEULS = {"connexion", "connexions", "fiche", "fiches", "survol", "panneau",
            "reglages", "chargement", "brouillon", "apercu", "recherche",
            "enregistrer", "supprimer", "annuler", "retour", "accueil", "amas",
            "tronc", "arborescence", "etiquette", "etiquettes"}
FR_JETON = re.compile(r"[a-zA-Z]+")


# `${…}` interpolations and `<…>` tags are removed BEFORE the words are counted.
# Rejecting any candidate that merely contained them was the first attempt, and it
# was worse than useless: the planet builds its whole top bar and its whole panel
# from template literals full of both, so the rule went blind on exactly the lines
# it was written for. Two sabotages proved it — a French string put back inside a
# template literal stayed green. Strip the machinery, keep the words.
MACHINERIE = re.compile(
    r"\$\{[^}]*\}"                       # interpolations
    r"|<[^>]*>"                          # balises
    r"|&[a-z]+;"                         # entités
    r"|\w*_\w[\w_]*"                     # snake_case : `on_fiche_write` n'est pas une phrase
    r"|[\w./~-]+\.(?:py|js|mjs|cjs|sh|md|json|html|css|webp|png)"   # chemins de fichiers
)


def sans_accent(s):
    """The French joints present in `s`, if there are at least two distinct ones.

    The CSS classes matter here: the planet has classes literally named `qui`,
    `quoi` and `clair`, so an ENGLISH label wrapped in them used to score two
    "French words" on the strength of its own markup. Stripping tags removes the
    attribute names along with them, which is the point.
    """
    texte = MACHINERIE.sub(" ", s)
    mots = {m.lower() for m in FR_JETON.findall(texte)}
    # A single strong word only counts inside something that reads like a LABEL:
    # it has a space, and it carries no bracket. Without that guard the rule fired
    # ten times on this repo and every one was code — a CSS class `.retour`, a dict
    # key `fiches[e[0]]`, a bare `tronc` in a bench page. None of them is on anyone's
    # screen, and ten false alarms is how a checker gets turned off.
    seuls = mots & FR_SEULS
    if seuls and " " in texte.strip() and not re.search(r"[\[\]{}]", texte):
        return sorted(seuls)
    trouves = mots & FR_MOTS
    return sorted(trouves) if len(trouves) >= 2 else []


OPT_OUT = re.compile(r"i18n-ok|BILINGUAL")


def opted_out(lines, line_no):
    """True when the line, or the comment block right above it, declares that its
    French is intentional. Six lines of reach: enough for a short paragraph of
    reasoning, short enough that an unrelated comment cannot cover a string."""
    lo = max(0, line_no - 7)
    return any(OPT_OUT.search(l) for l in lines[lo:line_no])


def main():
    bad = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        if rel in SKIP_FILES:
            continue
        if p.suffix not in EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        body = strip_comments(text, p.suffix)
        for s in visible_strings(body):
            hit = [c for c in s if c in ACCENTS] or sans_accent(s)
            if not hit or ALLOWED.search(s):
                continue
            line = text[: text.find(s)].count("\n") + 1
            if opted_out(lines, line):
                continue
            bad.append((rel, line, s.strip()[:90]))

    if bad:
        print(f"❌ {len(bad)} user-visible string(s) still French on this branch:\n")
        for rel, line, s in bad:
            print(f"  {rel}:{line}\n      {s}")
        print("\nTranslate them, or add the file to SKIP_FILES if its French is the point.")
        return 1

    print("✅ no French left in any user-visible string")
    return 0


if __name__ == "__main__":
    sys.exit(main())
