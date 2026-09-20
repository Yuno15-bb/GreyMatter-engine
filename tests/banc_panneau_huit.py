#!/usr/bin/env python3
"""Banc du PANNEAU DES HUIT (planet-v2/panneau) — ce que l'écran montre vraiment.

Pourquoi un banc qui ouvre un navigateur, alors qu'aucun autre ici ne le fait : les
défauts que ce panneau peut reprendre ne se voient QUE dans une mise en page calculée.
Depuis le 20/09 le panneau est une ROSACE (croquis IMA1.pdf de l'auteur) : huit cases
tournées en rayons autour d'un cœur. Ce dessin a deux façons de casser, vues à l'œil
sur le premier rendu :

  1. CASES SUPERPOSÉES — une case tournée de 45° est plus large qu'une case droite ;
     avec un rayon trop court, les losanges mordent sur leurs voisines. Une boîte
     englobante ne le voit pas (elle est droite, la case ne l'est pas) : le capteur
     calcule les VRAIS coins de chaque case depuis sa matrice de transformation et
     teste la séparation des polygones.
  2. TEXTE HORS DE SA CASE — le texte est centré dans la gélule ; une gélule trop
     plate le laisse sortir par le haut ET par le bas, et `scrollHeight` ne compte pas
     ce qui déborde vers le haut d'un centrage. Le capteur compare donc la boîte de
     chaque ligne à celle de son conteneur.

S'y ajoutent, des deux largeurs : aucun texte sur un autre, huit mots d'état présents
(la couleur seule ne dit rien), pas de débordement horizontal, pas d'erreur de script.

Chaque capteur est éprouvé par un SABOTAGE : on remet la faute dans la feuille de
style, et le banc EXIGE que le capteur rougisse. Un capteur qui ne rougit jamais ne
protège de rien.

Sortie : 0 tout vert · 1 un capteur au rouge · 3 banc IGNORÉ (pas de navigateur).
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent
PANNEAU = BRAIN / "planet-v2" / "panneau"
CSS = PANNEAU / "gmtr-panneau.css"

# Playwright n'est pas une dépendance du Brain : on le prend où il se trouve, et on le
# dit franchement quand il manque plutôt que de rendre un vert qui ne mesure rien.
PISTES = [
    Path.home() / "Desktop/exemple-projet/node_modules/playwright/index.mjs",
    BRAIN / "node_modules/playwright/index.mjs",
]

MESURE = r"""
import { chromium } from '%(pw)s';
const b = await chromium.launch();
const sorties = [];
for (const [w, h] of [[1440, 900], [915, 803], [400, 900]]) {
  const p = await b.newPage({ viewport: { width: w, height: h } });
  const err = []; p.on('pageerror', e => err.push(String(e)));
  await p.goto('http://127.0.0.1:%(port)d/panneau/');
  await p.waitForFunction(() => document.querySelectorAll('.case').length === 8, null, { timeout: 30000 });
  await p.waitForTimeout(400);
  sorties.push({ largeur: w, ...await p.evaluate(() => {
    const cases = [...document.querySelectorAll('.case')];
    const rosace = getComputedStyle(document.querySelector('.grille')).position === 'absolute';

    // 1. les vrais coins de chaque case (la matrice s'applique autour de son centre)
    const coins = (c) => {
      const m = new DOMMatrix(getComputedStyle(c).transform);
      const w = c.offsetWidth, h = c.offsetHeight;
      const cx = c.offsetLeft + w / 2, cy = c.offsetTop + h / 2;
      return [[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]].map(([x, y]) => {
        const q = m.transformPoint(new DOMPoint(x, y)); return [cx + q.x, cy + q.y]; });
    };
    const separes = (A, B) => {           // théorème de l'axe séparateur, deux convexes
      for (const P of [A, B]) for (let i = 0; i < P.length; i++) {
        const [x1, y1] = P[i], [x2, y2] = P[(i + 1) %% P.length];
        const nx = y2 - y1, ny = x1 - x2;
        const pr = (Q) => Q.map(([x, y]) => x * nx + y * ny);
        const a = pr(A), b = pr(B);
        if (Math.max(...a) <= Math.min(...b) + 0.5 || Math.max(...b) <= Math.min(...a) + 0.5) return true;
      }
      return false;
    };
    const superposees = [];
    if (rosace) {
      const polys = cases.map(coins);
      for (let i = 0; i < cases.length; i++) for (let j = i + 1; j < cases.length; j++)
        if (!separes(polys[i], polys[j]))
          superposees.push(cases[i].querySelector('.nom').textContent + ' × ' + cases[j].querySelector('.nom').textContent);
    }

    // 2. chaque ligne de texte reste dans son carré
    const hors = [];
    for (const c of cases) {
      const d = c.querySelector('.dedans'), r = d.getBoundingClientRect();
      for (const e of d.children) {
        const b = e.getBoundingClientRect();
        if (b.width === 0) continue;
        if (b.top < r.top - 1 || b.bottom > r.bottom + 1 || b.left < r.left - 1 || b.right > r.right + 1)
          hors.push(c.querySelector('.nom').textContent + ' : ' + e.className);
      }
    }

    // 3. aucun texte posé sur un autre. Tant que les gélules TOURNAIENT, ce capteur ne
    //    pouvait regarder que les textes droits : une boîte englobante droite ne dit rien
    //    d'un texte penché (deux lignes empilées à 45° ont des boîtes qui se croisent sans
    //    se toucher). Depuis le 20/09 plus rien ne tourne — l'auteur : « difficilement
    //    lisible » — donc on compare AUSSI ce qui est écrit dans les gélules, et c'est là
    //    qu'était la collision suivante : le numéro posé sur la ligne d'état.
    const txt = [...document.querySelectorAll('.fiche span, .coeur p, .bande .raison, .titre,'
      + ' .sceau, .case .numero, .case .nom, .case .mot, .case .detail')]
      .map(e => { const c = e.closest('.case');
        return { n: (c ? c.querySelector('.nom').textContent + ' ' : '') + (e.id || e.className),
                 r: e.getBoundingClientRect(), c }; })
      .filter(o => o.r.width > 0);
    const chev = [];
    for (let i = 0; i < txt.length; i++) for (let j = i + 1; j < txt.length; j++) {
      const a = txt[i].r, c2 = txt[j].r;
      if (a.left < c2.right - 1 && c2.left < a.right - 1 && a.top < c2.bottom - 1 && c2.top < a.bottom - 1)
        chev.push(txt[i].n + ' × ' + txt[j].n);
    }
    if (rosace) {
      const g = document.querySelector('.grille').getBoundingClientRect();
      for (const c of cases) {
        const P = coins(c).map(([x, y]) => [x + g.left, y + g.top]);   // en repère écran
        for (const t of txt) {
          if (t.c === c) continue;             // son propre texte, tenu par le capteur 2
          const r = t.r, Q = [[r.left, r.top], [r.right, r.top], [r.right, r.bottom], [r.left, r.bottom]];
          if (!separes(P, Q)) chev.push(c.querySelector('.nom').textContent + ' × ' + t.n);
        }
      }
    }

    return { rosace, superposees, hors_case: hors, chevauchements: chev,
             deborde_bas: document.documentElement.scrollHeight > innerHeight + 1,
             sans_mot: cases.filter(c => !(c.querySelector('.mot')?.textContent || '').trim()).length,
             deborde: document.documentElement.scrollWidth > innerWidth + 1 };
  }) , erreurs: err });
  await p.close();
}
await b.close();
console.log(JSON.stringify(sorties));
"""

SERVEUR = r"""
import http.server, os, sys, json, importlib.util
ICI = %(ici)r
os.environ["GMTR_AGENTS_JOURNAL"] = sys.argv[2]
spec = importlib.util.spec_from_file_location("srv", ICI + "/serveur.py")
srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.split("?")[0] == "/agents.json":
            c = json.dumps(srv.agents(), ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(c))); self.end_headers(); self.wfile.write(c); return
        return super().do_GET()
    def translate_path(self, p): return os.path.join(ICI, p.split("?")[0].lstrip("/"))
# HTTP/1.1 (donc connexion réutilisée) et une file d'attente large. En HTTP/1.0, chaque
# fichier de la page ouvre SA connexion : le navigateur en lance une poignée d'un coup,
# la file par défaut (5) déborde, le système laisse tomber les demandes en trop et le
# navigateur attend une éternité avant de réessayer. C'est ce qui faisait rendre au banc
# « waitForFunction: Timeout » sur une page pourtant saine (20/09).
H.protocol_version = "HTTP/1.1"
class S(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True
S(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""

# Un journal qui contient les CINQ situations : sans elles, le banc mesurerait une page
# où toutes les cases se ressemblent, donc il ne verrait pas grand-chose.
def journal(p):
    n = time.time()
    lignes = [
        dict(agent="architecte", phase="debut", ts=n - 95, raison="4 fiches neuves", activite="architecting"),
        dict(agent="mecanicien", phase="debut", ts=n - 20, raison="un hook a echoue", activite="auditing"),
        dict(agent="distillateur", phase="debut", ts=n - 4000, raison="session longue", activite="distilling"),
        dict(agent="synthetiseur", phase="debut", ts=n - 7200, activite="synthesizing"),
        dict(agent="synthetiseur", phase="fin", ts=n - 6900, duree_s=298.4, verdict="ok", cout_usd=0.2143),
        dict(agent="archiviste", phase="debut", ts=n - 18000, activite="archiving"),
        dict(agent="archiviste", phase="fin", ts=n - 17880, duree_s=119.7, verdict="echec-code-1"),
        dict(agent="jardinier", phase="debut", ts=n - 52000, activite="gardening"),
        dict(agent="jardinier", phase="fin", ts=n - 51940, duree_s=61.2, verdict="quota-ou-login"),
    ]
    p.write_text("\n".join(json.dumps(x) for x in lignes) + "\n", encoding="utf-8")


def mesurer(pw, port, tmp, essais=3):
    """Mesure une passe. Réessaie UNE fois, et seulement quand le navigateur n'a pas
    réussi à ouvrir la page.

    Pourquoi (mesuré le 20/09) : cinq exécutions sont mortes sur « waitForFunction:
    Timeout » alors que la page servie était identique à celle qu'une passe précédente
    avait mesurée verte. Deux pistes, aucune prouvée. `ps` montre qu'une AUTRE session
    Claude faisait tourner au même moment la suite Playwright de MCONFID, donc plusieurs
    navigateurs sans fenêtre se partageaient la machine. Et le serveur ci-dessus parlait
    en HTTP/1.0 avec une file de cinq connexions ; il a été aligné sur
    `planet-v2/serveur.py`, MAIS la contre-épreuve (remettre l'un puis l'autre, machine
    toujours chargée) passe au vert : ni l'un ni l'autre ne reproduit la panne.
    La cause reste INCONNUE. Ce qui est sûr, c'est que la page mesurée, elle, était
    saine — et qu'un banc qui s'écroule au hasard ne mesure plus rien.

    Aucun RÉSULTAT n'est réessayé : un rouge reste rouge du premier coup. Seule l'absence
    de mesure l'est."""
    js = tmp / "mesure.mjs"
    js.write_text(MESURE % {"pw": pw, "port": port}, encoding="utf-8")
    for n in range(essais):
        r = subprocess.run(["node", str(js)], capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return json.loads(r.stdout.strip().splitlines()[-1])
        if n + 1 == essais or "TimeoutError" not in r.stderr:
            raise RuntimeError(f"la mesure a échoué : {r.stderr.strip()[:400]}")
        print(f"  (le navigateur n'a pas ouvert la page — tentative {n + 2} sur {essais})", file=sys.stderr)
        time.sleep(5 * (n + 1))


def verdict(vues):
    """Rend la liste des fautes trouvées — vide si tout est propre."""
    fautes = []
    for v in vues:
        if v["superposees"]:
            fautes.append(f"{v['largeur']}px : {len(v['superposees'])} cases superposées — {v['superposees'][0]}")
        if v["hors_case"]:
            fautes.append(f"{v['largeur']}px : {len(v['hors_case'])} texte(s) hors de sa case — {v['hors_case'][0]}")
        if v["chevauchements"]:
            fautes.append(f"{v['largeur']}px : {len(v['chevauchements'])} textes superposés — {v['chevauchements'][0]}")
        if v["sans_mot"]:
            fautes.append(f"{v['largeur']}px : {v['sans_mot']} case(s) sans mot d'état — la couleur resterait seule")
        if v["deborde"]:
            fautes.append(f"{v['largeur']}px : la page déborde en largeur")
        # La rosace doit tenir SANS ascenseur : c'est exactement le défaut du 20/09 —
        # la fenêtre de l'auteur (915 px) basculait en liste au lieu de montrer la rosace.
        if v["rosace"] and v["deborde_bas"]:
            fautes.append(f"{v['largeur']}px : la rosace déborde en hauteur")
        if v["largeur"] == 915 and not v["rosace"]:
            fautes.append("915px : la fenêtre de l'auteur retombe sur la liste, pas sur la rosace")
        if v["erreurs"]:
            fautes.append(f"{v['largeur']}px : erreur de script — {v['erreurs'][0][:120]}")
    return fautes


def main():
    pw = next((p for p in PISTES if p.is_file()), None)
    if not pw or not shutil.which("node"):
        print("banc IGNORÉ — pas de navigateur Playwright ni de node sur cette machine.", file=sys.stderr)
        print("  (le panneau n'est donc PAS mesuré : ce n'est pas un vert)", file=sys.stderr)
        return 3

    tmp = Path(tempfile.mkdtemp(prefix="banc-panneau-"))
    jrn = tmp / "agents-demo.jsonl"
    journal(jrn)
    srv_py = tmp / "serveur_banc.py"
    srv_py.write_text(SERVEUR % {"ici": str(BRAIN / "planet-v2")}, encoding="utf-8")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, str(srv_py), str(port), str(jrn)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origine = CSS.read_text(encoding="utf-8")
    ok = True
    try:
        time.sleep(1.5)
        fautes = verdict(mesurer(pw, port, tmp))
        if fautes:
            ok = False
            print("ROUGE — le panneau tel qu'il est :")
            for f in fautes:
                print("  ·", f)
        else:
            print("vert — 1440 et 915 px (rosace), 400 px (liste) : aucune case sur une autre, chaque")
            print("       texte dans sa gélule, aucun texte superposé, huit mots d'état, rien ne déborde.")

        # ── les deux sabotages : chacun remet une faute RÉELLE, déjà vue le 20/09 ──
        for nom, avant, apres, attendu in [
            ("le rayon de la rosace raccourci",
             "--rayon:calc(var(--rosace) * .374);", "--rayon:calc(var(--rosace) * .20);", "cases superposées"),
            ("la gélule aplatie",
             "--gelule-c:calc(var(--rosace) * .125);", "--gelule-c:calc(var(--rosace) * .04);", "hors de sa case"),
            # la faute du 20/09 elle-même : le texte centré sur toute la gélule, donc
            # posé sous le numéro. Le capteur l'a trouvée avant qu'on la corrige ; ce
            # sabotage-là est ce qui l'empêche de repartir sans qu'on le sache.
            ("la place du numéro reprise au texte",
             "padding-right:calc(var(--rosace) * .058);", "padding-right:calc(var(--rosace) * .018);",
             "textes superposés"),
        ]:
            if avant not in origine:
                print(f"ROUGE — sabotage impossible : « {avant.strip()[:40]}… » a disparu de la feuille de style.")
                ok = False
                continue
            CSS.write_text(origine.replace(avant, apres, 1), encoding="utf-8")
            try:
                f2 = verdict(mesurer(pw, port, tmp))
            finally:
                CSS.write_text(origine, encoding="utf-8")
            if any(attendu in x for x in f2):
                print(f"sabotage « {nom} » → le capteur ROUGIT ✓")
            else:
                print(f"ROUGE — sabotage « {nom} » : le capteur est resté VERT, il ne protège de rien.")
                ok = False
    finally:
        CSS.write_text(origine, encoding="utf-8")   # la feuille repart toujours intacte
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
