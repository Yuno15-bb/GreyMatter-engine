"""The README's architecture diagram: how a session becomes memory.

Writes architecture.html beside this file; render it with
    python3 docs/media/src/architecture.py && docs/media/src/render.sh architecture 1000 1308
Sized for a GitHub page: 1000 wide, text large enough to stay legible at ~880 px.
Every statement in it is checked against the code: auto_maintain.py and brain_upkeep.py
(ORDER, COOLDOWN_H = 12) for the agents, the README's benchmark table for the recall times."""
from pathlib import Path

W, H = 1000, 1270

AMBRE = "#E9B824"
BLEU_CLAIR = "#8CB3F5"
BLEU_FORT = "#3B6FE0"
BEIGE = "#E4DFC6"
GRIS = "#E8E8E8"
VERT = "#1B7F3B"
ENCRE = "#1A1A1A"
ENCRE_BLEUE = "#15224A"
BLANC = "#FFFFFF"
TRAIT = "#3C3C3C"

parts: list[str] = []


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def boite(x, y, w, h, fill, lignes, *, stroke=None):
    st = f' stroke="{stroke}" stroke-width="2"' if stroke else ""
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{st} filter="url(#ombre)"/>')
    hauteurs = [li.get("s", 17) * 1.34 for li in lignes]
    cur = y + (h - sum(hauteurs)) / 2 + hauteurs[0] * 0.76
    cx = x + w / 2
    for li, ht in zip(lignes, hauteurs):
        parts.append(
            f'<text x="{cx:.0f}" y="{cur:.0f}" text-anchor="middle" font-size="{li.get("s", 17)}" '
            f'font-weight="{li.get("w", 400)}" fill="{li.get("c", ENCRE)}">{esc(li["t"])}</text>')
        cur += ht


def fleche(d, *, double=False):
    deb = ' marker-start="url(#pointe)"' if double else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{TRAIT}" stroke-width="2" '
                 f'stroke-dasharray="8 6"{deb} marker-end="url(#pointe)"/>')


def libelle(x, y, t, *, s=16, c=ENCRE, w=700, anchor="middle"):
    parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{s}" '
                 f'font-weight="{w}" fill="{c}">{esc(t)}</text>')


# Centre column: x 330..670 (340 wide, centre 500). Side notes: 730..950.
CX, CW = 330, 340
NX, NW = 730, 220
ETAGE = 55  # the gap between two rows

libelle(50, 62, "How a session becomes memory", s=26, anchor="start")
libelle(50, 94, "Everything runs on your machine. Nothing here is a service.", s=17, w=400,
        c="#555555", anchor="start")

y = 140
boite(CX, y, CW, 96, AMBRE, [
    {"t": "YOU WORK WITH YOUR AGENT", "s": 18, "w": 700},
    {"t": "any project, any prompt", "s": 17},
])
y_ask = y

y += 96 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX, y, CW, 118, BLEU_CLAIR, [
    {"t": "WHEN YOU ASK", "s": 18, "w": 700, "c": ENCRE_BLEUE},
    {"t": "the few notes that match", "s": 17, "c": ENCRE_BLEUE},
    {"t": "are handed to your agent", "s": 17, "c": ENCRE_BLEUE},
])
boite(NX, y + 9, NW, 100, GRIS, [
    {"t": "lexical search", "s": 16, "w": 700},
    {"t": "2 ms at 1,000 notes", "s": 16},
    {"t": "15 ms at 5,000", "s": 16},
])
fleche(f"M670,{y + 59} H{NX - 2}", double=True)
y_prompt = y

y += 118 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX, y, CW, 96, BLEU_CLAIR, [
    {"t": "DURING THE SESSION", "s": 18, "w": 700, "c": ENCRE_BLEUE},
    {"t": "what is written and read is noted", "s": 17, "c": ENCRE_BLEUE},
])

y += 96 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX, y, CW, 118, BLEU_CLAIR, [
    {"t": "AT SESSION END", "s": 18, "w": 700, "c": ENCRE_BLEUE},
    {"t": "the session is archived", "s": 17, "c": ENCRE_BLEUE},
    {"t": "and the agents wake up", "s": 17, "c": ENCRE_BLEUE},
])

y += 118 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX, y, CW, 128, BEIGE, [
    {"t": "EVERY TIME", "s": 18, "w": 700},
    {"t": "the distiller turns the session", "s": 17},
    {"t": "into notes; the gardener", "s": 17},
    {"t": "files and links them", "s": 17},
])
boite(NX, y + 14, NW, 100, GRIS, [
    {"t": "the gardener runs", "s": 16, "w": 700},
    {"t": "only if the distiller", "s": 16},
    {"t": "succeeded", "s": 16},
])
fleche(f"M670,{y + 64} H{NX - 2}", double=True)

y += 128 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX + 20, y, CW - 40, 104, BEIGE, [
    {"t": "SOMETIMES, AT MOST ONE", "s": 17, "w": 700},
    {"t": "challenger · architect", "s": 16},
    {"t": "archivist · mechanic", "s": 16},
])
boite(NX, y + 2, NW, 100, GRIS, [
    {"t": "only when needed", "s": 16, "w": 700},
    {"t": "its own sensor decides,", "s": 16},
    {"t": "never twice in 12 h", "s": 16},
])
fleche(f"M650,{y + 52} H{NX - 2}", double=True)

y += 104 + ETAGE
fleche(f"M500,{y - ETAGE} V{y - 4}")
boite(CX, y, CW, 118, VERT, [
    {"t": "YOUR TRUNK", "s": 18, "w": 700, "c": BLANC},
    {"t": "plain markdown on your disk,", "s": 17, "c": BLANC},
    {"t": "versioned with git", "s": 17, "c": BLANC},
])
boite(NX, y + 9, NW, 100, GRIS, [
    {"t": "three ways to look", "s": 16, "w": 700},
    {"t": "the menu bar pill,", "s": 16},
    {"t": "the map app, the brain CLI", "s": 16},
])
fleche(f"M670,{y + 59} H{NX - 2}", double=True)
y_trunk = y

# The loop: the trunk feeds the next recall, down the left side.
fleche(f"M{CX},{y_trunk + 59} H200 V{y_prompt + 59} H{CX - 4}")
libelle(186, (y_trunk + y_prompt) / 2 + 118 / 2, "the next recall", s=16, w=700, anchor="end")

H = y_trunk + 118 + 60

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <filter id="ombre" x="-30%" y="-30%" width="180%" height="180%">
      <feDropShadow dx="2.5" dy="3.5" stdDeviation="2.5" flood-color="#000" flood-opacity=".2"/>
    </filter>
    <marker id="pointe" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6"
            orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{TRAIT}"/>
    </marker>
  </defs>
  <rect width="{W}" height="{H}" rx="14" fill="#FFFFFF"/>
  {"".join(parts)}
</svg>'''

html = f'''<!doctype html>
<meta charset="utf-8">
<title>GreyMatter — how a session becomes memory</title>
<style>
  html, body {{ margin:0; padding:0; background:transparent; }}
  svg {{ display:block; font-family: Arial, Helvetica, "Helvetica Neue", sans-serif; }}
</style>
{svg}
'''
sortie = Path(__file__).with_name("architecture.html")
sortie.write_text(html, encoding="utf-8")
print(f"wrote {sortie} ({W}x{H})")
