"""The README's recall chart: the two measurements a reader can compare at a glance.

Writes recall-chart.html beside this file; render it with
    python3 docs/media/src/recall-chart.py && docs/media/src/render.sh recall-chart 880 420
Same palette and type as architecture.py. Every number is copied from the README's
tables ("On a real trunk", "On a public benchmark"); change them there first. Bars start
at zero, so a tie looks like a tie."""
from pathlib import Path

W, H = 880, 420
BLEU_FORT = "#3B6FE0"
GRIS = "#C9CCD2"
ENCRE = "#1A1A1A"
DOUX = "#555555"

parts: list[str] = []


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def texte(x, y, t, *, s=15, w=400, c=ENCRE, anchor="start"):
    parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{s}" '
                 f'font-weight="{w}" fill="{c}">{esc(t)}</text>')


def panneau(x0, titre, sous_titre, barres, maxi, fmt):
    """Horizontal bars: label above, bar, value at its end."""
    largeur = 360
    texte(x0, 50, titre, s=19, w=700)
    texte(x0, 74, sous_titre, s=14, c=DOUX)
    y = 108
    for nom, valeur, fort in barres:
        texte(x0, y, nom, s=14, w=700 if fort else 400)
        long = largeur * valeur / maxi
        parts.append(f'<rect x="{x0}" y="{y + 8}" width="{max(long, 3):.1f}" height="20" rx="3" '
                     f'fill="{BLEU_FORT if fort else GRIS}"/>')
        texte(x0 + max(long, 3) + 8, y + 23, fmt(valeur), s=14, w=700 if fort else 400)
        y += 52


# Left: README "On a real trunk" — 10 questions, 50 isolated runs, 2026-08-12.
panneau(30, "On a real trunk", "right answers out of 10 questions", [
    ("nothing", 0, False),
    ("the trunk, without recall", 8, False),
    ("GreyMatter, the full system", 10, True),
], 10, lambda v: f"{v}/10")

# Right: README "On a public benchmark" — LongMemEval M, recall-any@5, 2026-09-26.
panneau(470, "LongMemEval, M set", "a conversation with the answer in the top 5", [
    ("a plain BM25", 86.8, False),
    ("GreyMatter, default search", 86.4, True),
    ("claude-mem's search alone", 83.0, False),
    ("agentmemory hybrid", 78.6, False),
    ("GreyMatter, semantic mode", 61.0, False),
], 100, lambda v: f"{v:.1f} %")

texte(30, 290, "Tokens per exchange, top to bottom:", s=14, c=DOUX)
texte(30, 312, "178 k, 264 k, 168 k. Recall saves context", s=14, c=DOUX)
texte(30, 334, "instead of spending it.", s=14, c=DOUX)
texte(470, H - 22, "GreyMatter ties BM25 (p = 0.77): not behind, not better.", s=14, c=DOUX)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <rect width="{W}" height="{H}" rx="14" fill="#FFFFFF"/>
  <line x1="440" y1="36" x2="440" y2="{H - 50}" stroke="#E4E4E4" stroke-width="1.5"/>
  {"".join(parts)}
</svg>'''

html = f'''<!doctype html>
<meta charset="utf-8">
<title>GreyMatter — how well it recalls</title>
<style>
  html, body {{ margin:0; padding:0; background:transparent; }}
  svg {{ display:block; font-family: Arial, Helvetica, "Helvetica Neue", sans-serif; }}
</style>
{svg}
'''
sortie = Path(__file__).with_name("recall-chart.html")
sortie.write_text(html, encoding="utf-8")
print(f"wrote {sortie} ({W}x{H})")
