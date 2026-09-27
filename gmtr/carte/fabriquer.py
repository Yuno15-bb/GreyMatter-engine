#!/usr/bin/env python3
"""Build the GMTR map from the engine map without changing the source.

Every substitution has an expected count. A changed source stops the build.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "planet" / "index.html"
OUTPUT = HERE / "index.html"
STYLE = '\n<style id="gmtr">\n\n@font-face{ font-family:"Geist Mono"; font-weight:400; src:url(/fonts/geist-mono-latin-400-normal.woff2) format("woff2"); }\n@font-face{ font-family:"Geist Mono"; font-weight:500; src:url(/fonts/geist-mono-latin-500-normal.woff2) format("woff2"); }\n:root{\n  \n  --ph-100:#f2f2ee; --ph-200:#c9c9c9; --ph-300:#a9a6ad; --ph-400:#8a868f; --ph-500:#5e5b62;\n  --ph-600:#3a373f; --ph-700:#2a282e; --ph-800:#1d1c21; --ph-900:#151418; --ph-950:#0d0c10;\n  --glow:0,0,0;\n  --disp:"Geist Mono", ui-monospace, Menlo, monospace;\n  --gmtr-actif:#b6ff3b; --gmtr-alerte:#ff321e; --gmtr-fond:#09080b;\n  \n  --fond:#09080b; --actif:#b6ff3b; --alerte:#ff321e;\n  --police-pixel:"Departure Mono", "Geist Mono", ui-monospace, monospace;\n  --police-texte:"Geist Mono", ui-monospace, Menlo, monospace;\n}\nhtml,body{ background:var(--gmtr-fond); }\n\n#title{ font-family:"Departure Mono", var(--disp); font-size:14px; letter-spacing:.14em; color:var(--ph-100); text-shadow:none; }\n#counts{ color:var(--ph-300); }\n#viewtag{ color:var(--ph-400); }\n#fil .ici{ color:var(--ph-500); }\n#fil .retour{ color:var(--gmtr-actif); }\n#livenow{ color:var(--gmtr-actif); }\n#livenow .off{ color:var(--ph-500); }\n#session{ color:var(--gmtr-actif); }\n#session b{ color:var(--gmtr-actif); }\n#counts, #fil, #viewtag, #grow, #livenow, #session, #hint{ text-shadow:0 0 3px #000, 0 0 8px rgba(0,0,0,.9); }\n\n\n#modes button{ border:1px solid var(--ph-600); border-radius:0; color:var(--ph-300); text-shadow:none;\n  text-transform:uppercase; letter-spacing:.12em; font-size:10px; padding:4px 10px; }\n#modes button:hover{ background:rgba(255,255,255,.04); border-color:var(--ph-400); color:var(--ph-100); }\n#modes button.on{ background:var(--gmtr-actif); border-color:var(--gmtr-actif); color:var(--gmtr-fond); box-shadow:none; }\n\n\n#legend .hd{ color:var(--ph-500); letter-spacing:.14em; }\n#legend .nom{ color:var(--ph-200); }\n#legend .nb{ color:var(--ph-400); }\n#legend .bar{ background:var(--ph-800); height:2px; }\n#legend .bar i{ box-shadow:none; }\n#legend .dot{ box-shadow:none; border-radius:0; }\n#legend .row:hover{ background:rgba(182,255,59,.07); }\n#legend .row:hover .nom{ color:var(--gmtr-actif); }\n#legend .mk{ color:var(--ph-500); }\n#legend .repli > summary{ color:var(--ph-500); }\n\n\n#pod{ background:none; border:1px solid var(--ph-700); border-radius:0; box-shadow:none; }\n#pod .hd{ color:var(--ph-500); }\n#pod .hd .bascule.on{ color:var(--gmtr-actif); text-decoration:none; }\n#pod .cap{ color:var(--ph-300); }\n#pod .cap b{ color:var(--gmtr-actif); }\n\n\n#tip{ background:rgba(17,16,20,.94); background-image:none; border:1px solid var(--ph-700); border-radius:0;\n  color:var(--ph-200); box-shadow:none; }\n#tip::before,#tip::after{ border-color:var(--ph-500); }\n#tip .src{ color:var(--ph-400); border-bottom:1px solid var(--ph-700); }\n#tip .n{ color:var(--ph-100); text-shadow:none; }\n#tip .ch, #tip .cv, #tip .rs{ border-left:0; padding-left:0; }\n#tip .lnk .c{ border-color:var(--ph-700); color:var(--ph-300); }\n#tip .lnk .c:hover{ border-color:var(--gmtr-actif); color:var(--gmtr-actif); }\n\n\n#gmtr-nav{ pointer-events:auto; display:flex; gap:6px; margin-top:10px; font-family:"Departure Mono", var(--disp);\n  font-size:11px; letter-spacing:.12em; text-transform:uppercase; }\n#gmtr-nav a{ color:var(--ph-300); text-decoration:none; padding:2px 6px; }\n#gmtr-nav a:hover, #gmtr-nav a:focus-visible{ color:var(--gmtr-fond); background:#c9c9c9; outline:none; }\n#gmtr-nav .courant{ color:var(--gmtr-fond); background:#c9c9c9; padding:2px 6px; }\n\n\n#grille{ opacity:.55; }\n</style>\n'
HEAD = '<meta name="viewport" content="width=device-width, initial-scale=1">\n<link rel="stylesheet" href="/gmtr-motion.css">\n<link rel="stylesheet" href="/carte/gmtr-carte.css">\n' # i18n-ok
BODY = '<script src="/gmtr-motion.js"></script>\n<script src="/logo/marque-cotes.js"></script>\n<script src="/logo/gmtr-marque.js"></script>\n<script src="/carte/gmtr-carte.js"></script>\n' # i18n-ok
SUBSTITUTIONS = [
    ('<html lang="fr">', '<html lang="en">', 1),
    ('window.__planete = { showPanel, entrerRegion, sortirRegion, setMode,', 'window.__planete = { showPanel, entrerRegion, sortirRegion, setMode, get camera_objet(){ return camera; },', 1),
    ('map:RING_TEX, color:0xFF4F0C,', 'map:RING_TEX, color:0xB6FF3B,', 2),
    ('<button data-mode="struct">▦ structure</button>', '<button data-mode="struct">structure</button>', 1),
    ('const HOT = new THREE.Color(0xFFBCA2);', 'const HOT = new THREE.Color(0xB6FF3B);', 1),
    ('const LINK_GREY = new THREE.Color(0x8A3A02);', 'const LINK_GREY = new THREE.Color(0x34333A);', 1),
    ('color:0x5B1A00', 'color:0x2A282E', 1),
    ('color:0x872600', 'color:0x2C2B31', 1),
    ('new THREE.SpriteMaterial({ map:PLAY_TEX, color:0xFF6F36,', 'new THREE.SpriteMaterial({ map:PLAY_TEX, color:0x8FD52A,', 1),
    ('const mat=new THREE.LineBasicMaterial({ color:0xFF6F36, transparent:true, opacity:0, depthTest:false, depthWrite:false });', 'const mat=new THREE.LineBasicMaterial({ color:0x6E6B75, transparent:true, opacity:0, depthTest:false, depthWrite:false });', 1),
    ('new THREE.MeshBasicMaterial({ color:0x7A2200, wireframe:true, transparent:true,', 'new THREE.MeshBasicMaterial({ color:0x3A383F, wireframe:true, transparent:true,', 1),
    ("x.fillStyle='rgba(255,188,162,0.97)';", "x.fillStyle='rgba(182,255,59,0.97)';", 1),
    ('const LABEL_W = 4.6, LABEL_H = 0.62;', 'const LABEL_W = 8.0, LABEL_H = 1.08;', 1),
    ('  const rang=[...REGION_LIST].sort((a2,b2)=>(REGION_COUNT[b2]||0)-(REGION_COUNT[a2]||0));', '\n  const GMTR_TEINTES=[215,35,275,190,330,250];\n  const rang=[...REGION_LIST].sort((a2,b2)=>(REGION_COUNT[b2]||0)-(REGION_COUNT[a2]||0));', 1),
    ('REGION_COLOR[r]=new THREE.Color().setHSL((9+20*t)/360, 0.78, 0.44 - 0.04*t);', "REGION_COLOR[r]=(new URLSearchParams(location.search).get('teintes')==='0') ? new THREE.Color().setHSL(0, 0, 0.86 - 0.07*i) : new THREE.Color().setHSL(GMTR_TEINTES[i]/360, 0.45, 0.62);", 1),
    ('REGION_COLOR[r]=new THREE.Color().setHSL(17/360, 0.80, 0.29 - 0.10*t);', 'REGION_COLOR[r]=new THREE.Color().setHSL(260/360, 0.05, 0.46 - 0.12*t);', 1),
    ('if(L.hot){ L.mat.opacity=0.92*facing; L.mat.color.copy(colorOf(L.a.userData.data)).lerp(HOT,0.45); }', 'if(L.hot){ L.mat.opacity=0.92*facing; L.mat.color.copy(HOT); }', 1),
    ('b.userData.labMat.opacity = (b.userData.region===(hoveredRegion||podPin||podHover) ? 1 : Math.min(0.95, poids))*kLab;', 'b.userData.labMat.opacity = (b.userData.region===(hoveredRegion||podPin||podHover) ? 1 : 0.92)*kLab;', 1),
    ('else { L.mat.opacity=0.30*facing*niveau2Global*(1-0.80*sem);', 'else { L.mat.opacity=0.22*facing*niveau2Global*(1-0.80*sem);', 1),
    ('const m=new THREE.Mesh(new THREE.SphereGeometry(nd.frontier?0.16:0.125, 12, 12),', 'const m=new THREE.Mesh(new THREE.PlaneGeometry(nd.frontier?0.26:0.2, nd.frontier?0.26:0.2),', 1),
    ('    m.visible = true;\n', '    m.visible = true;\n    m.quaternion.copy(camera.quaternion);\n', 1),
    ('new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.12, 0.32, 0.72)', 'new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.0, 0.32, 0.72)', 1),
    ('new THREE.PointsMaterial({ color:col, map:POINT_TEX, size:0.40,', 'new THREE.PointsMaterial({ color:col, size:0.30,', 1),
    ('`<b style="color:#f5e2a0">✦</b> ${data.counts.convictions} convictions`', '`<b style="color:#f2f2ee">✦</b> ${data.counts.convictions} convictions`', 1),
    ('<title>🗺️ 3D/2D Knowledge Map — GreyMatter</title>', '<title>GMTR — map</title>', 1),
    ('<div id="title">[ TRUNK MAP — MEANING ]</div>', '<div id="title">GMTR · MEANING MAP</div>', 1),
    ('<button data-mode="sens">✦ meaning</button>', '<button data-mode="sens">meaning</button>', 1),
    ('<div class="hd">[ globe — <span class="bascule" data-mode="folders">folders</span> · <span class="bascule" data-mode="topics">topics</span> ]</div>', '<div class="hd">globe — <span class="bascule" data-mode="folders">folders</span> · <span class="bascule" data-mode="topics">topics</span></div>', 1),
    ('color:#e0a13a">⚠ ${data.counts.challenged} challenged', 'color:#ff321e">⚠ ${data.counts.challenged} challenged', 1),
    ('<b style="color:#e0a13a">⚠</b> ${data.counts.challenged} challenged', '<b style="color:#ff321e">⚠</b> ${data.counts.challenged} challenged', 1),
    ('<b style="color:#7fd4a0">↻</b> ${data.counts.resume} to resume', '<b style="color:#c9c9c9">↻</b> ${data.counts.resume} to resume', 1),
    ('<b style="color:#5ad7e6">▷</b> ${data.counts.media} replayable', '<b style="color:#8fd52a">▷</b> ${data.counts.media} replayable', 1),
    ('<b style="color:#b9c6ff">§</b> ${data.counts.regles} cross-cutting rules', '<b style="color:#c9c9c9">§</b> ${data.counts.regles} cross-cutting rules', 1),
    ('<b style="color:#7fe9ff">◯</b> ring = read less than', '<b style="color:#b6ff3b">◯</b> ring = read less than', 1),
]


def fabriquer():
    html = SOURCE.read_text(encoding="utf-8")
    missing = []
    for old, new, expected in SUBSTITUTIONS:
        count = html.count(old)
        if count != expected:
            missing.append(f"{old[:90]!r}: expected {expected}, found {count}")
            continue
        html = html.replace(old, new)
    if missing:
        raise RuntimeError("Map source changed; build stopped:\n" + "\n".join(missing))
    for tag, addition in (("</head>", STYLE + HEAD), ("</body>", BODY)):
        if html.count(tag) != 1:
            raise RuntimeError(f"Map source changed; expected one {tag}")
        html = html.replace(tag, addition + tag)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"GMTR map built: {OUTPUT} ({len(SUBSTITUTIONS)} substitutions)")


if __name__ == "__main__":
    fabriquer()
