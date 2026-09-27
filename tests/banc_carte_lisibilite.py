#!/usr/bin/env python3
"""Measure GMTR map readability at six viewport sizes and exercise known regressions."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
MAP = ENGINE / "gmtr" / "carte"
SIZES = [(1440, 900), (1280, 720), (1100, 800), (1024, 800), (834, 1112), (440, 956)]


def playwright():
    configured = os.environ.get("GREYMATTER_PLAYWRIGHT")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"GREYMATTER_PLAYWRIGHT does not name a file: {path}")
        return path
    for path in (ENGINE / "node_modules/playwright/index.mjs",
                 ENGINE / "gmtr/node_modules/playwright/index.mjs"):
        if path.is_file():
            return path
    return None


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

NAMES_JS = r"""(() => {
  const P = window.__planete, cam = P.camera_objet, W = innerWidth, H = innerHeight;
  const V3 = cam.position.constructor;
  const droite = new V3().setFromMatrixColumn(cam.matrixWorld, 0);
  const vus = [];
  for (const b of P.regions) {
    const u = b.userData;
    if (!u.lab || !u.labMat || u.labMat.opacity <= 0.01) continue;
    u.lab.updateWorldMatrix(true, false);
    const p = new V3().setFromMatrixPosition(u.lab.matrixWorld);
    const q = p.clone().addScaledVector(droite, u.lab.scale.x * b.scale.x * 0.5);
    p.project(cam); q.project(cam);
    if (p.z > 1) continue;
    const cx = (p.x * .5 + .5) * W, cy = (-p.y * .5 + .5) * H;
    const demi = Math.abs((q.x * .5 + .5) * W - cx);
    const dl = demi * (u.labEncre ?? 1), dh = demi * (u.lab.scale.y / u.lab.scale.x);
    vus.push({ nom: u.region, x0: cx - dl, x1: cx + dl, y0: cy - dh, y1: cy + dh });
  }
  const coupes = vus.filter(e => e.x0 < 0 || e.x1 > W || e.y0 < 0 || e.y1 > H)
    .map(e => e.nom + ' (' + Math.round(Math.max(-e.x0, e.x1 - W, -e.y0, e.y1 - H)) + ' px outside)');
  const paires = [];
  for (let i = 0; i < vus.length; i++) for (let j = i + 1; j < vus.length; j++) {
    const a = vus[i], c = vus[j];
    if (Math.min(a.x1, c.x1) > Math.max(a.x0, c.x0) && Math.min(a.y1, c.y1) > Math.max(a.y0, c.y0))
      paires.push(a.nom + ' + ' + c.nom);
  }
  return { total: vus.length, coupes, paires };
})()"""
MEASURE_JS = r"""
import { chromium } from '__PW__';
const TAILLES = __TAILLES__;
const SABOTAGE = __SABOTAGE__;
const SABOTAGE_JS = __SABOTAGE_JS__;
const FICHE = __FICHE__;
const NOMS = __NOMS__;
const QUATRE = `window.__planete.regions.slice()
  .sort((a, b) => b.userData.n - a.userData.n).slice(0, 4).map(r => r.userData.region)`;

const CENTRES = `(() => {
  const P = window.__planete, cam = P.camera_objet, W = innerWidth, H = innerHeight;
  const V3 = cam.position.constructor, o = [];
  for (const b of P.regions) {
    const u = b.userData;
    if (!u.lab || !u.labMat || u.labMat.opacity <= 0.01) continue;
    u.lab.updateWorldMatrix(true, false);
    const p = new V3().setFromMatrixPosition(u.lab.matrixWorld).project(cam);
    o.push(u.region + ':' + Math.round((p.x * .5 + .5) * W) + ',' + Math.round((-p.y * .5 + .5) * H)
           + ',' + u.labMat.opacity.toFixed(2));
  }
  return o.sort().join('|');
})()`;
async function ecrit(p, max = 20000) {
  let prec = -1, val = 0;
  for (const t0 = Date.now(); Date.now() - t0 < max;) {
    await p.waitForTimeout(400);
    val = await p.evaluate(() => (document.querySelector('#g-fiche-texte').textContent || '').length);
    if (val > 0 && val === prec) return val;
    prec = val;
  }
  return val;
}
async function calme(p, max = 25000) {
  let prec = null;
  for (const t0 = Date.now(); Date.now() - t0 < max;) {
    await p.waitForTimeout(400);
    const c = await p.evaluate(CENTRES);
    // an EMPTY list that stops changing is still too: inside a region no label is left on the
    // cloud, and `c &&` made every region wait out the full 25 s (run killed at 600 s, 2026-09-27)
    if (prec !== null && c === prec) return true;
    prec = c;
  }
  return false;
}
const b = await chromium.launch();
const ctx = await b.newContext();
await ctx.addCookies([{ name: 'gmtr_session', value: '__JETON__',
                        url: 'http://127.0.0.1:__PORT__' }]);
const sorties = [];
for (const [w, h] of TAILLES) {
  const premier = sorties.length === 0;
  const p = await ctx.newPage();
  await p.setViewportSize({ width: w, height: h });
  const err = []; p.on('pageerror', e => err.push(String(e)));
  await p.goto('http://127.0.0.1:__PORT__/carte/', { waitUntil: 'domcontentloaded' });
  await p.waitForFunction(() => document.querySelectorAll('#g-liste .g-ligne').length > 0
    && document.querySelectorAll('#g-journal-liste .g-evt').length > 0, null, { timeout: 40000 });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(1200);
  if (SABOTAGE) await p.addStyleTag({ content: SABOTAGE });
  if (SABOTAGE_JS) await p.evaluate(SABOTAGE_JS);
  await p.waitForTimeout(500);

  await p.evaluate(() => { window.__planete.rotation = false; });
  const pose = [];
  pose.push(await calme(p));
  const noms = { region: 'at rest', ...(await p.evaluate(NOMS)) };
  // The "panel" view lays its regions out flat and apart: its labels never overlap, untangling on
  // or off (9 labels, 0 pairs, measured 2026-09-27). Labels compete only in the "graph" view.
  await p.evaluate(() => window.__planete.setMode('sens'));
  pose.push(await calme(p));
  const graphe = { region: 'graph view at rest', ...(await p.evaluate(NOMS)) };
  await p.evaluate(() => window.__planete.setMode('struct'));
  await calme(p);
  const dedans = [];
  for (const r of await p.evaluate(QUATRE)) {
    await p.evaluate((x) => window.__planete.entrerRegion(x), r);
    pose.push(await calme(p));
    // Inside a region the cloud drops every label on purpose; the header `#g-lieu` names the
    // open region ("principles · 402"). `#fil` still exists but the GMTR skin hides it.
    const fil = await p.evaluate(() => {
      const e = document.querySelector('#g-lieu');
      return e && e.checkVisibility({ opacityProperty: true, visibilityProperty: true })
        ? e.textContent.split(' · ')[0].trim() : '';
    });
    dedans.push({ region: r, fil, ...(await p.evaluate(NOMS)) });
  }
  await p.evaluate(() => window.__planete.sortirRegion());
  await calme(p);

  let fiche = null;
  if (premier && FICHE) {
    // At rest no note is clickable, by design: notes show only inside their open region. So the
    // largest region is opened first, and closed again after.
    await p.evaluate((x) => window.__planete.entrerRegion(x), (await p.evaluate(QUATRE))[0]);
    await calme(p);
    await p.waitForTimeout(800);
    const cible = await p.evaluate(() => {
      const P = window.__planete, cam = P.camera_objet, W = innerWidth, H = innerHeight;
      const V3 = cam.position.constructor;
      let best = null, dmin = Infinity;
      for (const o of P.noeuds) {
        if (!o.visible || (o.material && o.material.opacity <= 0.2)) continue;
        // The back half of an open region's sphere is not aimable, by design: `magnet()` skips notes
        // facing away from the camera (under 0.12). Aiming at the one nearest the screen centre
        // without this rule hit a back note (-0.74) on the synthetic trunk, 2026-09-27.
        if (P.vue.view < 0.5 && o.position.clone().normalize()
              .dot(cam.position.clone().normalize()) < 0.12) continue;
        const q = o.getWorldPosition(new V3()).project(cam);
        if (q.z > 1) continue;
        const x = Math.round((q.x * .5 + .5) * W), y = Math.round((-q.y * .5 + .5) * H);
        if (x < 8 || y < 8 || x > W - 8 || y > H - 8) continue;
        const e = document.elementFromPoint(x, y);
        if (!e || e.closest('#gmtr-shell')) continue;
        const d = (x - W / 2) ** 2 + (y - H / 2) ** 2;
        if (d < dmin) { dmin = d; best = { x, y }; }
      }
      return best;
    });
    fiche = { vise: !!cible, apercu: 0, grand: 0, titre: '', attendu: 0 };
    if (cible) {
      await p.mouse.move(cible.x, cible.y);
      await p.waitForTimeout(600);
      // what the preview has to show: the first plain-words paragraph, or the one-line description
      fiche.attendu = await p.evaluate(() => {
        const m = window.__vise = window.__planete.survol, n = m && m.userData.data;
        return n ? ((n.en_clair ? n.en_clair.split('\n\n')[0] : n.desc) || '').trim().length : 0;
      });
      await p.mouse.click(cible.x, cible.y);
      fiche.apercu = await ecrit(p);
      fiche.titre = await p.evaluate(() =>
        (document.querySelector('#g-fiche-titre').textContent || '').trim());
      // THE CLOUD SLIDES LEFT WHEN THE NOTE PANEL OPENS: the free zone gives the panel its room, so the
      // clicked note is no longer under the pointer — 245 px away on the synthetic trunk, 2026-09-27.
      // Double-clicking the old spot hit nothing on a sparse trunk and a NEIGHBOUR on a dense one. A
      // person double-clicks the note where it now stands: so does the bench.
      const la = await p.evaluate(() => {
        const m = window.__vise, cam = window.__planete.camera_objet;
        if (!m) return null;
        const q = m.userData.base.clone().project(cam);
        return { x: Math.round((q.x * .5 + .5) * innerWidth), y: Math.round((-q.y * .5 + .5) * innerHeight) };
      });
      const ici = la || cible;
      await p.mouse.move(ici.x, ici.y);
      await p.waitForTimeout(400);
      await p.mouse.dblclick(ici.x, ici.y);
      fiche.grand = await ecrit(p);
      await p.keyboard.press('Escape');
      await p.waitForTimeout(600);
    }
    await p.evaluate(() => window.__planete.sortirRegion());
    await calme(p);
  }

  const m = await p.evaluate(() => {
    const R = (e) => e.getBoundingClientRect();
    const rond = (v) => Math.round(v);

    const FEUILLES = ['#g-regions', '#g-fiche', '#g-ecrit', '#g-col-log', '.g-entete', '.g-pied'];
    const vus = [];
    for (const sel of FEUILLES) {
      const e = document.querySelector(sel); if (!e) continue;
      const st = getComputedStyle(e);
      if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05) continue;
      const q = R(e); if (q.width < 4 || q.height < 4) continue;
      vus.push({ sel, l: q.left, t: q.top, r: q.right, b: q.bottom });
    }
    const croises = [];
    for (let i = 0; i < vus.length; i++) for (let j = i + 1; j < vus.length; j++) {
      const x = vus[i], y = vus[j];
      const dx = Math.min(x.r, y.r) - Math.max(x.l, y.l);
      const dy = Math.min(x.b, y.b) - Math.max(x.t, y.t);
      if (dx > 0 && dy > 0) croises.push(x.sel + ' + ' + y.sel + ' (' + rond(dx) + 'x' + rond(dy) + ' px)');
    }

    const li = [...document.querySelectorAll('#g-liste .g-ligne:not(.cachee)')];
    const uniq = (a) => [...new Set(a)].sort((x, y) => x - y);
    const bords = uniq(li.map(l => l.querySelector('.part')).filter(Boolean).map(e => rond(R(e).left)));
    const fins = uniq(li.map(l => l.querySelector('.nb')).filter(Boolean).map(e => rond(R(e).right)));
    const rognes = li.map(l => l.querySelector('.nom')).filter(e => e && e.scrollWidth > e.clientWidth + 1)
                     .map(e => e.textContent.trim());

    const evts = [...document.querySelectorAll('#g-journal-liste .g-evt')];
    const queues = evts.filter(e => e.scrollWidth > e.clientWidth + 1)
                       .map(e => e.textContent.trim().slice(-30));

    const codes = [...document.querySelectorAll('#g-ecrit-corps > *')]
                    .filter(e => e.scrollWidth > e.clientWidth + 1).length;

    const f = document.querySelector('#g-fiche'), ec = document.querySelector('#g-ecrit');
    const P = window.__planete;
    const duCorpus = (P && P.noeuds ? P.noeuds.map(n => (n.userData && n.userData.texte) || '')
                       .sort((a, c) => c.length - a.length)[0] : '') || '';
    const secours = 'conflicting information measurement sensor sabotage note region '.repeat(60);
    const texte = duCorpus.length > secours.length ? duCorpus : secours;
    const corps = document.querySelector('#g-ecrit-corps');
    for (let i = 0; i < 60; i++) {
      const d = document.createElement('div');
      d.className = 'g-l'; d.textContent = '+    fill line ' + i;
      corps.appendChild(d);
    }
    f.hidden = false; f.classList.add('grand');
    document.querySelector('#g-fiche-titre').textContent =
      'A NOTE WITH A PARTICULARLY LONG TITLE THAT WRAPS TO ANOTHER LINE';
    document.querySelector('#g-fiche-texte').textContent = texte;
    const cache = getComputedStyle(ec).display === 'none';
    const jour = cache ? null : rond(R(ec).top - R(f).bottom);

    dispatchEvent(new Event('resize'));
    const tx = document.querySelector('#g-fiche-texte');
    const lh = parseFloat(getComputedStyle(tx).lineHeight);
    let hb = R(tx).top, bb = R(tx).bottom;
    for (let a = tx.parentElement; a; a = a.parentElement) {
      const sa = getComputedStyle(a);
      if (sa.overflow === 'visible' && sa.overflowY === 'visible') continue;
      const ra = R(a); hb = Math.max(hb, ra.top); bb = Math.min(bb, ra.bottom);
    }
    const vu = Math.max(0, bb - hb), reste = lh ? vu % lh : 0;
    const scie = (lh && tx.scrollHeight > vu + 1)
                   ? Math.round(Math.min(reste, lh - reste) * 100) / 100 : 0;

    return { lignes: li.length, bords, fins, rognes, queues, codes, signes: texte.length, jour, cache,
             croises, panneaux: vus.length, scie, vuFiche: Math.round(vu), lhFiche: Math.round(lh * 100) / 100 };
  });
  sorties.push({ largeur: w, hauteur: h, ...m, noms, graphe, dedans, pose, fiche, erreurs: err });
  await p.close();
}
await b.close();
console.log(JSON.stringify(sorties));
"""
SERVER_JS = r"""
import importlib.util, sys
from http.server import ThreadingHTTPServer
spec = importlib.util.spec_from_file_location("gmtr_server", sys.argv[3])
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
server.SESSIONS.add(sys.argv[2])
class LocalServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True
LocalServer(("127.0.0.1", int(sys.argv[1])), server.Guichet).serve_forever()
"""


def measure(pw, port, token, directory, css="", script="", sizes=SIZES, note=True):
    runner = directory / "measure.mjs"
    text = (MEASURE_JS.replace("__PW__", str(pw)).replace("__PORT__", str(port))
            .replace("__JETON__", token).replace("__TAILLES__", json.dumps(sizes))
            .replace("__NOMS__", json.dumps(NAMES_JS))
            .replace("__SABOTAGE__", json.dumps(css))
            .replace("__SABOTAGE_JS__", json.dumps(script))
            .replace("__FICHE__", "true" if note else "false"))
    runner.write_text(text, encoding="utf-8")
    try:
        result = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("RED — browser measurement timed out")
        return None
    if result.returncode or not result.stdout.strip():
        print("RED — browser measurement failed: " + (result.stderr or "")[-600:])
        return None
    return json.loads(result.stdout.strip().splitlines()[-1])


def faults(results):
    issues = []
    for item in results:
        where = f"{item['largeur']}x{item['hauteur']}"
        if item['erreurs']:
            issues.append(f"{where}: script error: {item['erreurs'][0][:120]}")
        if item['lignes'] < 5:
            issues.append(f"{where}: region list failed to load")
        if len(item['bords']) > 1 or len(item['fins']) > 1:
            issues.append(f"{where}: region bar or count edges do not align")
        if item['rognes']:
            issues.append(f"{where}: clipped region names: {item['rognes']}")
        if item['queues'] or item['codes']:
            issues.append(f"{where}: clipped journal or live-code lines")
        if item['croises']:
            issues.append(f"{where}: overlapping panels: {item['croises'][0]}")
        if item.get('scie', 0) > 0.6:
            issues.append(f"{where}: note text cut between lines")
        if not item['cache'] and item['jour'] is not None and item['jour'] < 0:
            issues.append(f"{where}: expanded note overlaps live code")
        note = item.get('fiche')
        # 40 characters, or the note's whole preview when it is shorter: a note without a plain-words
        # section previews its one-line description (30 characters on the synthetic trunk)
        if note and (not note['vise'] or note['apercu'] < min(40, max(1, note.get('attendu', 40)))
                     or note['grand'] < note['apercu']):
            issues.append(f"{where}: clicked note lacks text")
        states = [item['noms'], item['graphe']] + item['dedans']
        if not all(item.get('pose', [])):
            issues.append(f"{where}: map labels did not settle")
        for state in states:
            if 'fil' not in state:        # at rest: the cloud carries the labels
                # the load check stays on the panel view: the graph view shows fewer labels by
                # design (3 of 7 regions on the synthetic trunk at 1280), it is measured for overlap
                if state['region'] == 'at rest' and state['total'] < 5:
                    issues.append(f"{where}: map labels did not load")
            else:                         # in a region: the header names it, the cloud is silent
                if state['fil'] != state['region']:
                    issues.append(f"{where} ({state['region']}): header does not name the open region")
                if state['total']:
                    issues.append(f"{where} ({state['region']}): {state['total']} other region label(s) left on the cloud")
            if state['coupes']:
                issues.append(f"{where}: map labels clipped at viewport edge")
            if state['paires']:
                issues.append(f"{where}: map labels overlap")
    return issues

SABOTAGES = [
    ("unaligned counts", ".g-ligne{ grid-template-columns:1fr 30px auto !important }", "", "edges do not align"),
    ("narrow region list", ".g-regions{ width:150px !important }", "", "clipped region names"),
    ("narrow journal", ".g-journal{ width:380px !important }", "", "clipped journal"),
    ("journal overlaps code", ".g-journal{ width:min(900px, 66vw) !important }", "", "overlapping panels"),
    # The cap has three floors: the note box, the text's stylesheet cap, and an inline maxHeight
    # set by the script. Lifting only the first left the sabotage mute (2026-09-27).
    ("unbounded note", ".g-fiche.grand, .g-fiche.grand .g-fiche-texte{ max-height:none !important }", "", "expanded note overlaps"),
    ("disable label spacing", "", "window.__planete.demelage = false", "map labels overlap"),
    ("read hidden note text", "", "document.documentElement.dataset.ficheBrute = '1'", "clicked note lacks text"),
    ("open region missing from header", "#g-lieu{ visibility:hidden !important }", "", "header does not name"),
    ("cut a text line", ".g-fiche .g-fiche-texte{ max-height:101px !important; overflow:hidden !important }", "", "cut between lines"), # i18n-ok: inherited CSS and JS identifiers
]


def main():
    pw = playwright()
    if pw is None:
        print("SKIPPED — Playwright not found (set GREYMATTER_PLAYWRIGHT)")
        return 0
    if not (MAP / "index.html").is_file():
        print("RED — committed GMTR map missing at gmtr/carte/index.html")
        return 1
    port, token = free_port(), secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        runner = directory / "server.py"
        runner.write_text(SERVER_JS, encoding="utf-8")
        server = subprocess.Popen([sys.executable, str(runner), str(port), token,
                                   str(ENGINE / "gmtr" / "serveur.py")],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(80):
                try:
                    with socket.create_connection(("127.0.0.1", port), 0.3):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                print("RED — local test server did not start")
                return 1
            normal = measure(pw, port, token, directory)
            if normal is None:
                return 1
            issues = faults(normal)
            if issues:
                print("RED — " + "\nRED — ".join(issues))
                return 1
            for name, css, script, expected in SABOTAGES:
                result = measure(pw, port, token, directory, css=css, script=script,
                                 sizes=SIZES, note="ficheBrute" in script)
                seen = faults(result) if result is not None else []
                if not any(expected in fault for fault in seen):
                    print(f"RED — sabotage {name} did not trigger {expected}: {seen}")
                    return 1
        finally:
            server.terminate()
            server.wait(timeout=5)
    print(f"PASS — {len(SIZES)} viewport sizes and {len(SABOTAGES)} regression sabotages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
