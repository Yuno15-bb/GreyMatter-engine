// ── LIVE ACTIVITY, IN THE MENU BAR ────────────────────────────────────────
// the author, 24/09 evening: the orb in the notch is "maybe a bad idea";
// what they want is the layout of Apple's Live Activities on Mac
// (pill to the right of the notch, panel that drops on click) — "it is
// precisely what I want with a different format". Then: "without going
// through the iPhone we keep this on Mac and we'll do the Swift when building the
// Apple version".
//
// Why a home-made build: a Mac app CANNOT create a Live
// Activity. macOS only mirrors the iPhone's (ActivityKit is iOS
// only). So here everything is drawn by us, with two ordinary windows:
//   · the PILL, set on a space reserved in the menu bar;
//   · the PANEL, which drops below it on click.
//
// ⚠ THE SPACE IN THE BAR IS RESERVED WITH AN EMPTY MENU ICON. A window
//   set "to the right of the notch" by eye would cover the author's icons.
//   A transparent menu icon the width of the pill forces macOS to
//   make room, where it arranges the icons; the pill then sits
//   exactly on its bounds.
//
// Launch: electron ilot.js — this is what hooks/auto_maintain.py launches since 24/09
// (the user: "remove the orb from the notch, we keep the pill").
// ⚠ the author, 24/09: "even at rest the mini capsule stays". The pill is
// PERMANENT: at the first "busy" it switches to work, says "done" for
// a few seconds, then goes back to rest — it no longer disappears.
const { app, BrowserWindow, Tray, nativeImage, screen, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');
// macOS's REAL liquid glass (NSGlassEffectView, macOS 26+): Electron 33
// does not have it, this native module sets it behind the page. the author, 24/09: "make
// them more transparent, liquid glass". Without it (other macOS), CSS fallback.
let verre = null;
if (!process.env.CAPSULE_SANS_VERRE) try { verre = require('electron-liquid-glass'); } catch (e) {}
function poserVerre(w, rayon, teinte) {
  if (!verre) return false;
  try {
    const id = verre.addView(w.getNativeWindowHandle(), { cornerRadius: rayon, tintColor: teinte });
    return id >= 0;
  } catch (e) { return false; }
}

const STATUT = path.join(process.env.CAPSULE_STATUT_HOME || os.homedir(), '.c-brain', 'trunk', 'state', 'status.json');
// Pill: measured on the author's reference (inDrive captures, 24/09), 85 × 26 pt.
// Panel: Apple's dimensions, which macOS takes from the iPhone (HIG Live
// Activities, "macOS dimensions — use the provided iOS dimensions"): 408
// wide, 84 to 160 high. The HEIGHT FOLLOWS THE CONTENT ("only use the space
// needed"): the page measures it and sends it, see 'ilot-hauteur'.
const PILULE = { w: 86, h: 26 };
// ⚠ the author, 24/09: "the open capsule cuts about 1/4 of its size". The
//   panel started at 84 pt whereas its content (#panneau, min-height 124 px)
//   is never less than that: hidden, the page does not re-measure (no frame
//   drawn), and the first opening cropped the bottom of the orb.
// ⚠ the author, 24/09: "it is still too wide" — they wanted the panel
//   reduced by a quarter, same proportions. The whole panel (text, orb, track)
//   is rendered at 75 % by the page zoom: its layout stays that of
//   408 px, nothing moves in it. Heights measured in the page are in page
//   px, converted here to screen points.
const ECHELLE = 0.75;
const PANNEAU = { w: Math.round(408 * ECHELLE), h: Math.round(138 * ECHELLE), hMin: 138, hMax: 160 };
// Filming the pill alone (the author, 25/09: "when only the little pill is visible"): the panel does not open by itself.
const PANNEAU_REPLIE = process.env.CAPSULE_PASTILLE_SEULE === '1';
const REPOS_AVANT_FIN = 4000;     // same wait as the orb tucking in: no back-and-forth between two tools
const TERMINE_VISIBLE = 6000;     // "done" stays readable, then back to rest

// Same table as orbe.html (VAISSEAUX) — the session is TORRENS.
const VAISSEAUX = { auditing:'NOSTROMO',
  mapping:'NARCISSUS', filing:'NARCISSUS', gardening:'NARCISSUS', distilling:'NARCISSUS',
  challenging:'SULACO', architecting:'SULACO', archiving:'SULACO',
  synthesizing:'ANESIDORA',
  working:'TORRENS', committing:'TORRENS', correcting:'TORRENS' };

let tray = null, pilule = null, panneau = null;
let course = null;          // the work in progress: { t0, fin, stations:[{vaisseau, etat, t}], detail }
let attenteFin = null, attenteEfface = null;

function barreDeMenus() {
  const d = screen.getPrimaryDisplay();
  return Math.max(24, d.workArea.y - d.bounds.y);
}

// ── THE RESERVED SPACE ────────────────────────────────────────────────────
function reserverPlace() {
  if (tray) return;
  // A transparent image the width of the pill, at 2×: macOS measures it
  // in points and shifts the other icons by as much.
  tray = new Tray(imageVide());
  tray.on('click', basculerPanneau);
}
function imageVide() {
  const W = PILULE.w * 2, H = 36;
  return nativeImage.createFromBitmap(Buffer.alloc(W * H * 4), { width: W, height: H, scaleFactor: 2 });
}
function libererPlace() { if (tray) { tray.destroy(); tray = null; } }

// ⚠ Hand-made slide, frame by frame. macOS's native slide
//   (setBounds(…, true)) was tried on 24/09: the pill arrived offset
//   by several tens of points and its right end stayed square during
//   the trip. Here, 16 steps in 260 ms, at the pace at which macOS slides the neighbouring icons, with a soft curve; the native glass follows
//   the window at each step.
const glissements = new Map();
const cibles = new Map();   // the current target: a new height is written into it instead of being overwritten
function glisser(w, cible, duree = 260) {
  clearInterval(glissements.get(w));
  cibles.set(w, cible);
  const de = w.getBounds(), t0 = Date.now();
  const doux = (k) => 1 - Math.pow(1 - k, 3);
  const pas = () => {
    const k = Math.min(1, (Date.now() - t0) / duree), e = doux(k);
    const m = (a, b) => Math.round(a + (b - a) * e);
    w.setBounds({ x: m(de.x, cible.x), y: m(de.y, cible.y), width: m(de.width, cible.width), height: m(de.height, cible.height) });
    if (k === 1) { clearInterval(glissements.get(w)); glissements.delete(w); }
  };
  glissements.set(w, setInterval(pas, 16));
  pas();
}
// The reserved space also moves when an icon on ITS RIGHT changes width
// (clock, macOS's recording indicator…): without this watch, the pill
// lagged behind and bit into the neighbouring icon (seen on 24/09).
let placeVue = '';
setInterval(() => {
  if (!tray || !pilule) return;
  const t = tray.getBounds(), cle = t.x + ',' + t.width;
  if (cle === placeVue) return;
  const premier = !placeVue;
  placeVue = cle;
  if (!premier) { poserPilule(true); suivrePanneau(t); }
}, 250);
function poserPilule(anime) {
  if (!tray || !pilule) return;
  const t = tray.getBounds();
  if (!t.width) return setTimeout(() => poserPilule(anime), 100);   // the icon is not placed yet
  const barre = barreDeMenus();
  const cible = { x: Math.round(t.x + (t.width - PILULE.w) / 2),
                  y: Math.round((barre - PILULE.h) / 2), width: PILULE.w, height: PILULE.h };
  if (anime) glisser(pilule, cible); else pilule.setBounds(cible);
  pilule.setAlwaysOnTop(true, 'screen-saver', 4);
}

function fenetre(opts, requete) {
  const w = new BrowserWindow(Object.assign({
    frame: false, transparent: true, resizable: false, movable: false,
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false, fullscreenable: false, show: false,
    // ⚠ Without this flag, macOS pushes a window requested at y < bar below the
    //   menu bar (measured on 24/09 for the notch: requested at 0, placed at 33).
    enableLargerThanScreen: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false,
                      nodeIntegrationInSubFrames: true },
  }, opts, { webPreferences: Object.assign({ nodeIntegration: true, contextIsolation: false,
    backgroundThrottling: false, nodeIntegrationInSubFrames: true }, opts.webPreferences) }));
  w.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  w.setHiddenInMissionControl(true);
  w.loadFile('ilot.html', { search: requete });
  return w;
}

function creerPilule() {
  // ⚠ roundedCorners:false — cause of the "pointy ends" (the author, 3 times),
  //   measured on 24/09 on a 26 pt test window: macOS crops every
  //   window with its own rounding, which bites into the half-circle and makes it
  //   pointy, whether the drawing is CSS, SVG or glass. Without this cropping,
  //   the edge follows the circle to the pixel.
  pilule = fenetre({ width: PILULE.w, height: PILULE.h, focusable: false, acceptFirstMouse: true,
                     roundedCorners: false }, 'pilule');
  pilule.webContents.on('did-finish-load', () => {
    if (poserVerre(pilule, PILULE.h / 2, '#00000026')) pilule.webContents.send('ilot-verre');
    envoyer(); poserPilule(); pilule.showInactive();
    // opened by default before the page finished loading: it missed the message
    pilule.webContents.send('ilot-ouvert', !!(panneau && panneau.isVisible())); });
}

function creerPanneau() {
  // The glass is macOS's (vibrancy), not a CSS blur: `backdrop-filter`
  // only blurs the page's content, never the desktop behind the window.
  // Liquid glass if the module is there; otherwise the former `hud` material.
  // ⚠ 25/09, measured: on the glass, the window shadow cost ~11 % of a core
  //   to WindowServer while the panel is open (recomputed at every frame
  //   of what passes beneath: video, terminal). It could only be seen as a
  //   light rim at the edge; the page draws it itself (html[data-verre]).
  const avecVerre = !!verre;
  panneau = fenetre(Object.assign({ width: PANNEAU.w, height: PANNEAU.h, hasShadow: !avecVerre,
    webPreferences: { zoomFactor: ECHELLE },
    backgroundColor: '#00000000' }, avecVerre ? { roundedCorners: false }
    : { vibrancy: 'hud', visualEffectState: 'active', roundedCorners: true }), 'panneau');
  panneau.webContents.on('did-finish-load', () => {
    if (avecVerre && poserVerre(panneau, Math.round(24 * ECHELLE), '#0000001a')) panneau.webContents.send('ilot-verre');
    envoyer();
  });
  // ⚠ the author, 24/09: "expanded and persistent, only if you click in the mini
  //   pill does it fold". A click elsewhere therefore NO LONGER closes it (Apple's
  //   panel, for its part, closes on blur): only the pill folds it.
}

function basculerPanneau() {
  if (!panneau) return;
  if (panneau.isVisible()) return fermerPanneau();
  ouvrirPanneau(false);
}
// the author, 24/09: "the pill must always be expanded when the agents
// launch". Opened by default at each new ship, WITHOUT taking focus:
// the terminal they type in keeps control. Without focus, no blur: the panel
// stays expanded until a click on the pill or the end of the work.
function ouvrirPanneau(focus) {
  if (!panneau || !pilule) return;
  if (panneau.isVisible()) return;
  if (!pilule.isVisible()) return setTimeout(() => ouvrirPanneau(focus), 150);
  // ⚠ the author, 24/09: "when the name changes […] the big capsule moves with the
  //   movement of the small one whereas it should stay static". So the panel
  //   aligns on the RIGHT edge of the reserved space, the only one that does not move
  //   when the pill changes width (measured, see ilot-largeur).
  const p = tray ? tray.getBounds() : pilule.getBounds(), barre = barreDeMenus(), d = screen.getPrimaryDisplay().bounds;
  let x = Math.round(p.x + p.width - PANNEAU.w);
  x = Math.max(d.x + 8, Math.min(x, d.x + d.width - PANNEAU.w - 8));
  panneau.setBounds({ x, y: barre + 3, width: PANNEAU.w, height: PANNEAU.h });
  panneau.setAlwaysOnTop(true, 'screen-saver', 4);
  if (focus) { panneau.show(); panneau.focus(); } else panneau.showInactive();
  panneau.webContents.send('ilot-ouvert', true);
  pilule.webContents.send('ilot-ouvert', true);
}
function fermerPanneau() {
  if (!panneau || !panneau.isVisible()) return;
  panneau.hide();
  panneau.webContents.send('ilot-ouvert', false);
  if (pilule) pilule.webContents.send('ilot-ouvert', false);
}
ipcMain.on('ilot-clic', basculerPanneau);
// The pill carries the name and the action: its width follows the text. The reserved
// space is redone at the new width, then the pill settles on it again.
ipcMain.on('ilot-largeur', (_e, w) => {
  w = Math.max(60, Math.min(240, Math.ceil(w)));
  if (w === PILULE.w) return;
  if (!tray) { PILULE.w = w; return; }
  // ⚠ Measured on 24/09: the RIGHT edge of the reserved space does not move when
  //   it changes width (1277 for 156, 208 and 180 pt), but right after
  //   setImage, getBounds sometimes returns the old x with the new width. The
  //   pill then widened to the right, over the neighbouring icon,
  //   then jumped left 250 ms later — the jolt seen by the author ("at each
  //   change of agent the whole thing jolts just before changing").
  //   So we compute the final place from the right edge, before setImage, and
  //   slide there at the same time as macOS slides the other icons.
  const t = tray.getBounds(), droite = t.x + t.width, marge = Math.max(0, t.width - PILULE.w);
  PILULE.w = w;
  const place = { x: droite - (w + marge), width: w + marge };
  placeVue = place.x + ',' + place.width;              // the watch must not correct a second time
  tray.setImage(imageVide());
  glisser(pilule, { x: Math.round(place.x + marge / 2), y: pilule.getBounds().y, width: w, height: PILULE.h }, 260);
  // The text only comes back once the pill has arrived.
  setTimeout(() => { if (pilule && PILULE.w === w) pilule.webContents.send('ilot-pose'); }, 280);
});
// If macOS moves the reserved space (a neighbouring icon appears), the panel
// follows, always pinned to the right edge of the space.
function suivrePanneau(t) {
  if (panneau && panneau.isVisible()) {
    const d = screen.getPrimaryDisplay().bounds, b = panneau.getBounds();
    const x = Math.max(d.x + 8, Math.min(Math.round(t.x + t.width - PANNEAU.w), d.x + d.width - PANNEAU.w - 8));
    if (x !== b.x) glisser(panneau, { x, y: b.y, width: PANNEAU.w, height: PANNEAU.h });
  }
}
ipcMain.on('ilot-hauteur', (_e, h) => {
  PANNEAU.h = Math.ceil(Math.max(PANNEAU.hMin, Math.min(PANNEAU.hMax, h)) * ECHELLE);
  if (panneau && glissements.has(panneau)) cibles.get(panneau).height = PANNEAU.h;   // mid-slide
  else if (panneau && panneau.isVisible()) { const b = panneau.getBounds(); panneau.setBounds({ x: b.x, y: b.y, width: PANNEAU.w, height: PANNEAU.h }); }
  else if (panneau) panneau.setSize(PANNEAU.w, PANNEAU.h);
});

// ── THE WORK IN PROGRESS ──────────────────────────────────────────────────
function lireStatut() {
  let st = { state: 'idle' };
  try { st = JSON.parse(fs.readFileSync(STATUT, 'utf8')); } catch (e) {}
  const frais = (Date.now() / 1000 - (st.ts || 0)) < 180;
  const etat = (st.state === 'busy' && frais) ? (st.activity || 'working') : 'idle';
  return { etat, detail: st.detail || '' };
}

function envoyer() {
  // `ouvert` says again on each turn whether the panel is on screen: the first
  // 'ilot-ouvert' leaves before the panel's page has loaded, and gets lost.
  const ouvert = !!(panneau && !panneau.isDestroyed() && panneau.isVisible());
  const donnees = course ? Object.assign({}, course, { maintenant: Date.now(), vocabulaire: VAISSEAUX, ouvert }) : null;
  for (const w of [pilule, panneau]) if (w && !w.isDestroyed()) w.webContents.send('ilot', donnees);
}

function commencer() {
  course = { t0: Date.now(), fin: null, stations: [], detail: '' };
  reserverPlace();
  if (!pilule) creerPilule(); else { poserPilule(); pilule.showInactive(); }
  if (!panneau) creerPanneau();
}

// Rest: the pill stays, the panel folds, and the last work is
// kept on one line for whoever opens the panel.
function auRepos() {
  fermerPanneau();
  const d = course && course.stations.length
    ? { n: course.stations.length, duree: (course.fin || Date.now()) - course.t0 } : (course && course.dernier) || null;
  course = { repos: true, t0: Date.now(), fin: Date.now(), stations: [], detail: '', dernier: d };
  envoyer();
}

// the author, 24/09: "we can't see what the orb is working on, just the topic
// or broad theme is enough". The code scrolling in the orb stays (its
// texture), but the panel SAYS the theme plainly: the project of the last file
// written, taken from the diff stream the orb already reads. Only the end of the stream
// is read, and only when it has moved.
const FLUX = path.join(os.homedir(), '.claude', 'companion', 'sessions');
let themeVu = { f: '', t: 0, theme: '' };
function themeEnCours() {
  try {
    let f = '', t = 0;
    for (const n of fs.readdirSync(FLUX)) {
      if (!n.endsWith('.jsonl')) continue;
      const m = fs.statSync(path.join(FLUX, n)).mtimeMs;
      if (m > t) { t = m; f = path.join(FLUX, n); }
    }
    if (!f) return '';
    if (f === themeVu.f && t === themeVu.t) return themeVu.theme;
    const taille = fs.statSync(f).size, lu = Math.min(taille, 65536);
    const tampon = Buffer.alloc(lu), fd = fs.openSync(f, 'r');
    fs.readSync(fd, tampon, 0, lu, taille - lu); fs.closeSync(fd);
    let theme = '';
    for (const l of tampon.toString('utf8').split('\n').reverse()) {
      try { const j = JSON.parse(l); if (j.type === 'diff' && j.project) { theme = j.project.replace(/[-_]+/g, ' '); break; } } catch (e) {}
    }
    themeVu = { f, t, theme };
    return theme;
  } catch (e) { return ''; }
}

function tic() {
  const { etat, detail } = lireStatut();
  if (etat !== 'idle') {
    clearTimeout(attenteFin); attenteFin = null;
    clearTimeout(attenteEfface); attenteEfface = null;
    if (!course || course.fin) { if (course && course.fin) course = null; commencer(); }
    const vaisseau = VAISSEAUX[etat] || 'TORRENS';
    const der = course.stations[course.stations.length - 1];
    if (!der || der.vaisseau !== vaisseau) { course.stations.push({ vaisseau, etat, t: Date.now() }); if (!PANNEAU_REPLIE) ouvrirPanneau(false); }
    else der.etat = etat;
    course.detail = detail;
    course.theme = themeEnCours();
  } else if (course && !course.fin && !attenteFin) {
    attenteFin = setTimeout(() => {
      attenteFin = null;
      if (!course) return;
      course.fin = Date.now();
      envoyer();
      attenteEfface = setTimeout(auRepos, TERMINE_VISIBLE);
    }, REPOS_AVANT_FIN);
  }
  envoyer();
}

// ── HEARTBEAT ────────────────────────────────────────────────────────────
// hooks/auto_maintain.py (ensure_capsule) looks for the process by its path
// `capsule/node_modules/electron`: the pill answers there like the orb. Without a
// heartbeat, after 90 s, it would take it for a ZOMBIE capsule and kill it
// to relaunch. Here there is no permanent window to prove — between two
// jobs, showing nothing is the intended behaviour — so the heartbeat proves
// that the reading loop is running.
// Derived from $HOME, not __dirname: the hook reads the TRUNK's state, the pill lives in the engine.
const ALIVE = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'capsule-alive');
function battement() { try { fs.writeFileSync(ALIVE, String(Date.now())); } catch (e) {} }

// ⚠ A SINGLE PILL. the author, 24/09: "there are 2 capsules open" — a
//   manual relaunch and the hook's (ensure_capsule) started 7 s
//   apart, each reserved its space and set its pill. The app lock
//   makes the second stop at once, whoever launched it.
if (!app.requestSingleInstanceLock()) { app.quit(); process.exit(0); }

app.whenReady().then(() => {
  if (app.dock) app.dock.hide();
  battement(); setInterval(battement, 5000);
  commencer(); auRepos();
  ['display-metrics-changed', 'display-added', 'display-removed'].forEach((e) => screen.on(e, poserPilule));
  tic(); setInterval(tic, 700);
  if (process.env.CAPSULE_ILOT_OUVRIR === '1') setTimeout(basculerPanneau, 2500);   // bench: panel opened by default
});
app.on('window-all-closed', (e) => e.preventDefault());   // the space is freed, the app keeps listening
