// ── L'ACTIVITÉ EN DIRECT, DANS LA BARRE DE MENUS ──────────────────────────
// l'auteur, 24/09 soir : l'orbe dans l'encoche est « peut-être une mauvaise idée » ;
// ce qu'il veut, c'est la mise en page des Activités en direct d'Apple sur Mac
// (pastille à droite de l'encoche, panneau qui tombe au clic) — « c'est
// précisément ce que je veux avec un format différent ». Puis : « sans passer
// par l'iPhone on garde ça sur Mac et on fera le Swift à la construction de la
// version Apple ».
//
// Pourquoi une construction maison : une app Mac ne PEUT PAS créer d'Activité en
// direct. macOS ne fait que refléter celles de l'iPhone (ActivityKit est iOS
// seulement). Donc ici tout est dessiné par nous, avec deux fenêtres ordinaires :
//   · la PASTILLE, posée sur une place réservée dans la barre de menus ;
//   · le PANNEAU, qui tombe dessous au clic.
//
// ⚠ LA PLACE DANS LA BARRE SE RÉSERVE AVEC UNE ICÔNE DE MENU VIDE. Une fenêtre
//   posée « à droite de l'encoche » au jugé recouvrirait les icônes de l'auteur.
//   Une icône de menu transparente de la largeur de la pastille oblige macOS à
//   faire la place, à l'endroit où il range les icônes ; la pastille se pose
//   ensuite exactement sur ses bornes.
//
// Lancer : electron ilot.js — c'est ce que lance hooks/auto_maintain.py depuis le 24/09
// (L'utilisateur : « retire l'orbe de l'encoche, on garde la pastille »).
// ⚠ l'auteur, 24/09 : « même si au repos la mini capsule reste ». La pastille est
// PERMANENTE : au premier « busy » elle passe au travail, dit « terminé »
// quelques secondes, puis revient au repos — elle ne disparaît plus.
const { app, BrowserWindow, Tray, nativeImage, screen, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');
// Le VRAI verre liquide de macOS (NSGlassEffectView, macOS 26+) : Electron 33
// n'en a pas, ce module natif le pose derrière la page. l'auteur, 24/09 : « rends
// les plus transparentes, liquid glass ». Sans lui (autre macOS), repli CSS.
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
// Pastille : relevée sur la référence de l'auteur (captures inDrive, 24/09), 85 × 26 pt.
// Panneau : les dimensions d'Apple, que macOS reprend de l'iPhone (HIG Live
// Activities, « macOS dimensions — use the provided iOS dimensions ») : 408 de
// large, 84 à 160 de haut. La HAUTEUR SUIT LE CONTENU (« only use the space
// needed ») : la page la mesure et l'envoie, voir 'ilot-hauteur'.
const PILULE = { w: 86, h: 26 };
// ⚠ l'auteur, 24/09 : « la capsule ouverte coupe environ 1/4 de sa taille ». Le
//   panneau partait à 84 pt alors que son contenu (#panneau, min-height 124 px)
//   n'en fait jamais moins : caché, la page ne se remesure pas (pas d'image
//   dessinée), et la première ouverture rognait le bas de l'orbe.
// ⚠ l'auteur, 24/09 : « elle est encore trop large » — il voulait le panneau
//   réduit d'un quart, mêmes proportions. Tout le panneau (texte, orbe, piste)
//   est rendu à 75 % par le zoom de la page : sa mise en page reste celle de
//   408 px, rien n'y bouge. Les hauteurs mesurées dans la page sont en px de
//   page, converties ici en points d'écran.
const ECHELLE = 0.75;
const PANNEAU = { w: Math.round(408 * ECHELLE), h: Math.round(138 * ECHELLE), hMin: 138, hMax: 160 };
// Tournage de la pastille seule (l'auteur, 25/09 : « quand seule la petite pastille est visible ») : le panneau ne s'ouvre pas tout seul.
const PANNEAU_REPLIE = process.env.CAPSULE_PASTILLE_SEULE === '1';
const REPOS_AVANT_FIN = 4000;     // même attente que la rentrée de l'orbe : pas d'aller-retour entre deux outils
const TERMINE_VISIBLE = 6000;     // « terminé » reste lisible, puis retour au repos

// Même table que orbe.html (VAISSEAUX) — la session est TORRENS.
const VAISSEAUX = { auditing:'NOSTROMO',
  mapping:'NARCISSUS', filing:'NARCISSUS', gardening:'NARCISSUS', distilling:'NARCISSUS',
  challenging:'SULACO', architecting:'SULACO', archiving:'SULACO',
  synthesizing:'ANESIDORA',
  working:'TORRENS', committing:'TORRENS', correcting:'TORRENS' };

let tray = null, pilule = null, panneau = null;
let course = null;          // le travail en cours : { t0, fin, stations:[{vaisseau, etat, t}], detail }
let attenteFin = null, attenteEfface = null;

function barreDeMenus() {
  const d = screen.getPrimaryDisplay();
  return Math.max(24, d.workArea.y - d.bounds.y);
}

// ── LA PLACE RÉSERVÉE ─────────────────────────────────────────────────────
function reserverPlace() {
  if (tray) return;
  // Une image transparente de la largeur de la pastille, à 2× : macOS la mesure
  // en points et décale les autres icônes d'autant.
  tray = new Tray(imageVide());
  tray.on('click', basculerPanneau);
}
function imageVide() {
  const W = PILULE.w * 2, H = 36;
  return nativeImage.createFromBitmap(Buffer.alloc(W * H * 4), { width: W, height: H, scaleFactor: 2 });
}
function libererPlace() { if (tray) { tray.destroy(); tray = null; } }

// ⚠ Glissement fait main, image par image. Le glissement natif de macOS
//   (setBounds(…, true)) a été essayé le 24/09 : la pastille arrivait décalée
//   de plusieurs dizaines de points et son bout droit restait carré pendant
//   le trajet. Ici, 16 pas en 260 ms, au rythme où macOS fait glisser les icônes voisines avec une courbe douce ; le verre natif suit
//   la fenêtre à chaque pas.
const glissements = new Map();
const cibles = new Map();   // la cible en cours : une hauteur neuve s'y inscrit au lieu d'être écrasée
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
// La place réservée bouge aussi quand une icône à SA DROITE change de largeur
// (horloge, voyant d'enregistrement de macOS…) : sans ce guet, la pastille
// restait en arrière et mordait l'icône voisine (vu le 24/09).
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
  if (!t.width) return setTimeout(() => poserPilule(anime), 100);   // l'icône n'est pas encore rangée
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
    // ⚠ Sans ce drapeau, macOS repousse une fenêtre demandée à y < barre sous la
    //   barre de menus (mesuré le 24/09 pour l'encoche : demandée à 0, posée à 33).
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
  // ⚠ roundedCorners:false — cause des « bouts pointus » (l'auteur, 3 fois),
  //   mesurée le 24/09 sur une fenêtre témoin de 26 pt : macOS rogne toute
  //   fenêtre avec son propre arrondi, qui mord dans le demi-cercle et le rend
  //   pointu, que le dessin soit en CSS, en SVG ou en verre. Sans ce rognage,
  //   le bord suit le cercle au pixel près.
  pilule = fenetre({ width: PILULE.w, height: PILULE.h, focusable: false, acceptFirstMouse: true,
                     roundedCorners: false }, 'pilule');
  pilule.webContents.on('did-finish-load', () => {
    if (poserVerre(pilule, PILULE.h / 2, '#00000026')) pilule.webContents.send('ilot-verre');
    envoyer(); poserPilule(); pilule.showInactive();
    // ouvert d'office avant que la page ait fini de charger : elle a raté le message
    pilule.webContents.send('ilot-ouvert', !!(panneau && panneau.isVisible())); });
}

function creerPanneau() {
  // Le verre est celui de macOS (vibrancy), pas un flou CSS : `backdrop-filter`
  // ne floute que le contenu de la page, jamais le bureau derrière la fenêtre.
  // Verre liquide si le module est là ; sinon le matériau `hud` d'avant.
  // ⚠ 25/09, mesuré : sur le verre, l'ombre de fenêtre coûtait ~11 % d'un cœur
  //   à WindowServer tant que le panneau est ouvert (recalculée à chaque image
  //   de ce qui passe dessous : vidéo, terminal). Elle ne se voyait qu'en un
  //   liseré clair au bord ; la page le dessine elle-même (html[data-verre]).
  const avecVerre = !!verre;
  panneau = fenetre(Object.assign({ width: PANNEAU.w, height: PANNEAU.h, hasShadow: !avecVerre,
    webPreferences: { zoomFactor: ECHELLE },
    backgroundColor: '#00000000' }, avecVerre ? { roundedCorners: false }
    : { vibrancy: 'hud', visualEffectState: 'active', roundedCorners: true }), 'panneau');
  panneau.webContents.on('did-finish-load', () => {
    if (avecVerre && poserVerre(panneau, Math.round(24 * ECHELLE), '#0000001a')) panneau.webContents.send('ilot-verre');
    envoyer();
  });
  // ⚠ l'auteur, 24/09 : « déplié et persistant, seulement si on clique dans la mini
  //   pastille il se replie ». Un clic ailleurs ne le referme donc PLUS (le
  //   panneau d'Apple, lui, se referme au blur) : seule la pastille le replie.
}

function basculerPanneau() {
  if (!panneau) return;
  if (panneau.isVisible()) return fermerPanneau();
  ouvrirPanneau(false);
}
// l'auteur, 24/09 : « la pastille doit toujours être dépliée au lancement des
// agents ». Ouverture d'office à chaque nouveau vaisseau, SANS prendre le focus :
// le terminal où il tape garde la main. Sans focus, pas de blur : le panneau
// reste déplié jusqu'à un clic sur la pastille ou la fin du travail.
function ouvrirPanneau(focus) {
  if (!panneau || !pilule) return;
  if (panneau.isVisible()) return;
  if (!pilule.isVisible()) return setTimeout(() => ouvrirPanneau(focus), 150);
  // ⚠ l'auteur, 24/09 : « quand le nom change […] la grande capsule bouge avec le
  //   mouvement de la petite alors qu'elle devrait rester statique ». Le panneau
  //   s'aligne donc sur le bord DROIT de la place réservée, le seul qui ne bouge
  //   pas quand la pastille change de largeur (mesuré, voir ilot-largeur).
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
// La pastille porte le nom et l'action : sa largeur suit le texte. La place
// réservée est refaite à la nouvelle largeur, puis la pastille s'y repose.
ipcMain.on('ilot-largeur', (_e, w) => {
  w = Math.max(60, Math.min(240, Math.ceil(w)));
  if (w === PILULE.w) return;
  if (!tray) { PILULE.w = w; return; }
  // ⚠ Mesuré le 24/09 : le bord DROIT de la place réservée ne bouge pas quand
  //   elle change de largeur (1277 pour 156, 208 et 180 pt), mais juste après
  //   setImage, getBounds rend parfois l'ancien x avec la nouvelle largeur. La
  //   pastille s'élargissait alors vers la droite, par-dessus l'icône voisine,
  //   puis sautait à gauche 250 ms plus tard — l'à-coup vu par l'auteur (« à chaque
  //   changement d'agent le tout prend des à-coups juste avant de changer »).
  //   On calcule donc la place finale depuis le bord droit, avant setImage, et
  //   on y glisse en même temps que macOS fait glisser les autres icônes.
  const t = tray.getBounds(), droite = t.x + t.width, marge = Math.max(0, t.width - PILULE.w);
  PILULE.w = w;
  const place = { x: droite - (w + marge), width: w + marge };
  placeVue = place.x + ',' + place.width;              // le guet ne doit pas corriger une seconde fois
  tray.setImage(imageVide());
  glisser(pilule, { x: Math.round(place.x + marge / 2), y: pilule.getBounds().y, width: w, height: PILULE.h }, 260);
  // Le texte ne revient qu'une fois la pastille arrivée.
  setTimeout(() => { if (pilule && PILULE.w === w) pilule.webContents.send('ilot-pose'); }, 280);
});
// Si macOS déplace la place réservée (une icône voisine apparaît), le panneau
// suit, toujours calé sur le bord droit de la place.
function suivrePanneau(t) {
  if (panneau && panneau.isVisible()) {
    const d = screen.getPrimaryDisplay().bounds, b = panneau.getBounds();
    const x = Math.max(d.x + 8, Math.min(Math.round(t.x + t.width - PANNEAU.w), d.x + d.width - PANNEAU.w - 8));
    if (x !== b.x) glisser(panneau, { x, y: b.y, width: PANNEAU.w, height: PANNEAU.h });
  }
}
ipcMain.on('ilot-hauteur', (_e, h) => {
  PANNEAU.h = Math.ceil(Math.max(PANNEAU.hMin, Math.min(PANNEAU.hMax, h)) * ECHELLE);
  if (panneau && glissements.has(panneau)) cibles.get(panneau).height = PANNEAU.h;   // en plein glissé
  else if (panneau && panneau.isVisible()) { const b = panneau.getBounds(); panneau.setBounds({ x: b.x, y: b.y, width: PANNEAU.w, height: PANNEAU.h }); }
  else if (panneau) panneau.setSize(PANNEAU.w, PANNEAU.h);
});

// ── LE TRAVAIL EN COURS ───────────────────────────────────────────────────
function lireStatut() {
  let st = { state: 'idle' };
  try { st = JSON.parse(fs.readFileSync(STATUT, 'utf8')); } catch (e) {}
  const frais = (Date.now() / 1000 - (st.ts || 0)) < 180;
  const etat = (st.state === 'busy' && frais) ? (st.activity || 'working') : 'idle';
  return { etat, detail: st.detail || '' };
}

function envoyer() {
  // `ouvert` redit à chaque tour si le panneau est à l'écran : le premier
  // 'ilot-ouvert' part avant que la page du panneau soit chargée, et se perd.
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

// Le repos : la pastille reste, le panneau se replie, et le dernier travail est
// gardé en une ligne pour qui ouvre le panneau.
function auRepos() {
  fermerPanneau();
  const d = course && course.stations.length
    ? { n: course.stations.length, duree: (course.fin || Date.now()) - course.t0 } : (course && course.dernier) || null;
  course = { repos: true, t0: Date.now(), fin: Date.now(), stations: [], detail: '', dernier: d };
  envoyer();
}

// l'auteur, 24/09 : « on ne voit pas sur quoi travaille l'orbe, juste le topic
// ou grand thème est suffisant ». Le code qui défile dans l'orbe reste (sa
// texture), mais le panneau DIT le thème en clair : le projet du dernier fichier
// écrit, pris dans le flux des diffs que l'orbe lit déjà. Seule la fin du flux
// est lue, et seulement quand il a bougé.
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

// ── BATTEMENT DE VIE ─────────────────────────────────────────────────────
// hooks/auto_maintain.py (ensure_capsule) cherche le process par son chemin
// `capsule/node_modules/electron` : la pastille y répond comme l'orbe. Sans
// battement, passé 90 s, il la prendrait pour une capsule ZOMBIE et la tuerait
// pour relancer. Ici il n'y a pas de fenêtre permanente à prouver — entre deux
// travaux, ne rien montrer est le comportement voulu — donc le battement prouve
// que la boucle de lecture tourne.
// Dérivé de $HOME, pas de __dirname : le hook lit le state du TRONC, la pastille vit dans le moteur.
const ALIVE = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'capsule-alive');
function battement() { try { fs.writeFileSync(ALIVE, String(Date.now())); } catch (e) {} }

// ⚠ UNE SEULE PASTILLE. l'auteur, 24/09 : « il y a 2 capsules ouvertes » — une
//   relance à la main et celle du hook (ensure_capsule) sont parties à 7 s
//   d'écart, chacune a réservé sa place et posé sa pastille. Le verrou d'app
//   fait que la seconde s'arrête aussitôt, quel que soit celui qui l'a lancée.
if (!app.requestSingleInstanceLock()) { app.quit(); process.exit(0); }

app.whenReady().then(() => {
  if (app.dock) app.dock.hide();
  battement(); setInterval(battement, 5000);
  commencer(); auRepos();
  ['display-metrics-changed', 'display-added', 'display-removed'].forEach((e) => screen.on(e, poserPilule));
  tic(); setInterval(tic, 700);
  if (process.env.CAPSULE_ILOT_OUVRIR === '1') setTimeout(basculerPanneau, 2500);   // banc : panneau ouvert d'office
});
app.on('window-all-closed', (e) => e.preventDefault());   // la place se libère, l'app reste à l'écoute
