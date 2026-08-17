// C Brain — the capsule: the ORB.
//
// A pane of living glass in the bottom-right corner of the screen. Its fluid
// mechanic says WHAT KIND of work is happening, its speed the INTENSITY, its
// hue the AGENT FAMILY — and the code actually being written scrolls inside it.
//
// ⚠ THIS FILE IS NOT SYNCED from the author's trunk (see sync.sh). The private
//   version carries Dock geometry specific to that machine: sitting on the
//   Dock, the ripple on hover, magnification. None of that means anything on
//   someone else's machine. Here the orb simply lives in the bottom-right
//   corner and can be dragged with the mouse. Any fix made over there has to
//   be PORTED here by hand.
const { app, BrowserWindow, screen, globalShortcut, ipcMain, powerMonitor } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

let win;

// --- Single instance: one capsule, never a zombie window ------------------
// ⚠ KNOWN FRICTION, observed 2026-08-17, NOT fixed here on purpose. A second
//   capsule quits INSTANTLY and SILENTLY: no message, no exit code anyone sees,
//   nothing in any log. It cost half an hour of chasing a capsule that "would
//   not start" before the lock turned out to be the reason. It bites whoever
//   runs two trunks on one machine — a private install and a package checkout,
//   which is exactly the author's setup — and anyone debugging the orb, since
//   the fix is invisible while an older instance still holds the lock.
//   Worse for observation: on macOS the window server keeps ghost layers of
//   these transparent always-on-top windows, so a killed instance can still be
//   on screen. Screenshots of the orb are not a reliable sensor.
//   Left as is because it is not what stops a fresh install from working; the
//   sensible fix is a line on stderr saying which instance already holds it.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {       // a 2nd launch → re-show the existing one
    if (win) { win.showInactive(); }
  });
}

// The orb fills a square. 150 px: enough for the material to read and for the
// code scrolling inside to still be text, small enough not to eat the corner
// of the screen.
const SIZE = 150;
const EDGE = 26;

// DERIVED FROM $HOME, never from __dirname: the engine may live somewhere other
// than the trunk (symlink install), and it is the USER's state we watch. Same
// path orbe.html uses.
const STATUS = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'status.json');

// PROOF OF LIFE of the window, ported by hand on 2026-08-13.
//
// auto_maintain replaces a capsule process that no longer has a window (a
// zombie). It reads this file to tell a live capsule from a dead one — and
// until now the package shipped that CHECK WITHOUT ITS EMITTER, because this
// file is not synced. What kept it harmless is the guard on the other side:
// "never beaten != zombie". So the check could never repair anything either.
// Now it can.
//
// ⚠ Written by the MAIN process, never by the renderer: the renderer pauses on
//   purpose when the orb is hidden (asleep screen, idle), so a heartbeat placed
//   there would stop at rest and cry zombie over a perfectly healthy capsule.
// ⚠ Only while the window exists — that is the entire point: a process without
//   a window stops beating, and becomes visible from the outside.
// Same $HOME-derived path as STATUS: it is the TRUNK's state, not the engine's.
const ALIVE = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'capsule-alive');
const HEARTBEAT = 5000;
function heartbeat() {
  try {
    if (win && !win.isDestroyed()) fs.writeFileSync(ALIVE, String(Date.now()));
  } catch (e) {}
}

// The orb clears itself off the screen once nothing is working: an indicator
// that says nothing should not occupy the desktop. It comes back on the first
// agent. One minute of presence after the work ends — long enough to read what
// just happened.
const IDLE_BEFORE_HIDE = 60000;
// Same freshness guard as the renderer: status.json can stay on "busy" with a
// stale timestamp if an agent dies abruptly.
// THE WINDOW IS NOT DECIDED HERE. It used to be, as a literal — and the renderer
// held a second literal, and `brain status` a third at 120 s. Three copies of one
// question, already 4x apart. The number now comes from the file the Python side
// reads too; the literal below is a fallback for a broken install, not a rival.
const FRESHNESS = path.join(os.homedir(), '.c-brain', 'trunk', 'hooks', 'status_freshness.json');
function freshnessWindows() {
  try {
    const j = JSON.parse(fs.readFileSync(FRESHNESS, 'utf8'));
    return { live: (j.liveness_stale_seconds || 30) * 1000,
             activity: (j.activity_stale_seconds || 120) * 1000 };
  } catch (e) { return { live: 30000, activity: 120000 }; }
}
const STALE = freshnessWindows().live;
let idleSince = null;

function watchStatus() {
  const poll = () => {
    let s = 'idle', ts = 0;
    try {
      const j = JSON.parse(fs.readFileSync(STATUS, 'utf8'));
      s = j.state || 'idle'; ts = j.ts || 0;
    } catch (e) {}
    const fresh = (Date.now() / 1000 - ts) * 1000 < STALE;
    const busy = s === 'busy' && fresh;

    if (busy) {
      idleSince = null;
      if (win && !win.isVisible()) win.showInactive();   // without stealing focus
    } else if (win) {
      if (idleSince === null) idleSince = Date.now();
      if (Date.now() - idleSince > IDLE_BEFORE_HIDE && win.isVisible()) win.hide();
    }
  };
  // ⚠ fs.watchFile only fires when the file CHANGES. The idle delay, though,
  //   has to be re-evaluated even when nothing moves — otherwise the orb never
  //   hides. So a real timer is needed as well.
  fs.watchFile(STATUS, { interval: 2000 }, poll);   // instant reaction on wake-up
  setInterval(poll, 1500);                          // the passing of idle time
  poll();
}

// --- Sleep: screen off / session locked → the orb really hides. Without this
//     it keeps animating and forcing the desktop to recomposite in front of a
//     black screen.
let _hiddenBySleep = false;
function powerSleep() {
  if (win && win.isVisible()) { _hiddenBySleep = true; win.hide(); }
}
function powerWake() {
  if (win && _hiddenBySleep) { _hiddenBySleep = false; win.showInactive(); }
}
function watchPower() {
  ['suspend', 'lock-screen'].forEach(e => powerMonitor.on(e, powerSleep));
  ['resume', 'unlock-screen'].forEach(e => powerMonitor.on(e, powerWake));
  if (powerMonitor.on) {
    powerMonitor.on('screen-locked', powerSleep);
    powerMonitor.on('screen-unlocked', powerWake);
  }
}

// --- Clicks pass through, EXCEPT on the orb -------------------------------
// A 150 px square swallowing clicks on the desktop would be unbearable.
// `forward: true` still lets mouse moves through: the page can therefore say
// "that one is me" and only becomes clickable over the disc.
function setClickThrough(on) {
  if (!win) return;
  try { win.setIgnoreMouseEvents(on, { forward: true }); } catch (e) {}
}
ipcMain.on('cap-interactive', (_e, interactive) => setClickThrough(!interactive));

// --- Grabbing the orb and moving it ---------------------------------------
// ⚠ The cursor is tracked HERE, in the main process, not in the page. On a fast
//   drag the pointer leaves the window: the renderer stops receiving moves and
//   the orb would lag behind the gesture. screen.getCursorScreenPoint() stays
//   correct wherever the cursor is.
let freePos = false;      // the user moved it: we stop putting it back
let follow = null;

ipcMain.on('cap-drag-begin', () => {
  if (!win || follow) return;
  freePos = true;
  const c0 = screen.getCursorScreenPoint();
  const b0 = win.getBounds();
  // Offset between the window corner and the grabbed point: without it, the orb
  // would jump to centre itself under the cursor on the first pixel of movement.
  const dx = c0.x - b0.x, dy = c0.y - b0.y;
  follow = setInterval(() => {
    if (!win) return;
    const c = screen.getCursorScreenPoint();
    win.setPosition(Math.round(c.x - dx), Math.round(c.y - dy));
  }, 16);
});

ipcMain.on('cap-drag-end', () => {
  if (follow) { clearInterval(follow); follow = null; }
  keepInView();
});

// On release, and on every display change: bring the window back into the
// visible area. Without this, an orb dropped on a screen you then unplug stays
// parked in the void — it exists, it costs, and it cannot be found.
function keepInView() {
  if (!win) return;
  const b = win.getBounds();
  const wa = screen.getDisplayMatching(b).workArea;
  const KEEP = 24;                      // this much orb always stays on screen
  const x = Math.min(Math.max(b.x, wa.x - b.width + KEEP), wa.x + wa.width - KEEP);
  const y = Math.min(Math.max(b.y, wa.y), wa.y + wa.height - KEEP);
  if (x !== b.x || y !== b.y) win.setPosition(Math.round(x), Math.round(y));
}

function place() {
  if (!win) return;
  if (freePos) return keepInView();      // the user picked their spot
  const b = screen.getPrimaryDisplay().bounds;
  win.setPosition(b.x + b.width - SIZE - EDGE, b.y + b.height - SIZE - EDGE);
}

function createWindow() {
  const b = screen.getPrimaryDisplay().bounds;
  win = new BrowserWindow({
    width: SIZE,
    height: SIZE,
    x: b.x + b.width - SIZE - EDGE,
    y: b.y + b.height - SIZE - EDGE,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    fullscreenable: false,
    // backgroundThrottling:false → the capsule is a HUD that NEVER holds focus
    //   (showInactive); without this Electron throttles rendering to a few
    //   frames per second as soon as it is not frontmost, and the animation
    //   stutters.
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false },
  });
  win.webContents.setBackgroundThrottling(false);
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile('orbe.html');
  // Clicks pass through FROM THE START: between the first paint and the first
  // hover, the window is a transparent rectangle sitting on the desktop.
  // Waiting for the first mouse move would leave a dead zone at the exact
  // moment the user discovers the thing.
  setClickThrough(true);
  // The page pauses its animation when nobody is looking: painting for a dark
  // screen makes the desktop recomposite for nothing.
  const tellVisible = (v) => { try { win.webContents.send('cap-visible', v); } catch (e) {} };
  win.on('show', () => tellVisible(true));
  win.on('hide', () => tellVisible(false));
}

app.whenReady().then(() => {
  createWindow();
  ['display-metrics-changed', 'display-added', 'display-removed']
    .forEach(e => screen.on(e, place));
  watchStatus();   // re-shows the orb as soon as an agent turns 'busy'
  watchPower();    // real pause when the screen sleeps or the session locks
  heartbeat(); setInterval(heartbeat, HEARTBEAT);   // proof of life of the WINDOW

  // ─── THE DIAGNOSTIC CHANNEL ────────────────────────────────────────────────
  //
  // WHY IT EXISTS. `docs/verification-recipe.md` told the reader to `touch
  // /tmp/cap_shot_req` and read `/tmp/cap.png`. No such mechanism was ever in
  // this repository — the documented way to verify the capsule could not be run,
  // and nobody noticed because nobody ran it. Found on 2026-08-17 by grepping the
  // whole tree for the string the recipe prescribes.
  //
  // WHAT IT IS, AND WHAT IT IS NOT. It reports what the RENDERER believes it is
  // displaying: the state label, whether that label is visible, the detail, the
  // code pad, and whether the orb object exists. That is one observable.
  //
  // ⚠ IT IS NOT A SUBSTITUTE FOR THE PIXEL. A renderer can be certain it is
  // drawing an orb that no one can see — the window may be off-screen, occluded,
  // or fully transparent. And the converse trap is the one this whole verification
  // exists for: macOS keeps GHOST LAYERS of these windows, so a screenshot can
  // show an orb that no renderer is drawing. Neither observable can stand in for
  // the other, which is exactly why both are collected.
  //
  // Opt-in by environment variable, so nothing is written in normal use.
  if (process.env.CBRAIN_PROBE_OUT) {
    const OUT = process.env.CBRAIN_PROBE_OUT;
    const probe = () => {
      if (!win || win.isDestroyed()) return;
      // Read from the DOM, in the renderer. Not from main's own idea of the
      // state: main's idea is the INPUT. Asking it what it displays would be
      // asking the question to the answer.
      win.webContents.executeJavaScript(`(() => {
        const el = (id) => document.getElementById(id);
        const seen = (id) => { const e = el(id); return !!e && e.classList.contains('vu'); };
        const c = el('c');
        return {
          renderer_ready: document.readyState,
          state_text: (el('dit') || {}).textContent || "",
          state_visible: seen('dit'),
          detail_text: (el('fiche') || {}).textContent || "",
          detail_visible: seen('fiche'),
          pad_visible: seen('pave'),
          orb_object: typeof window.__orbe,
          canvas_w: c ? c.width : 0,
          canvas_h: c ? c.height : 0
        };
      })()`, true).then((dom) => {
        const b = win.getBounds();
        const payload = Object.assign({
          ts: Date.now(),
          // The window as the SYSTEM sees it. A renderer drawing perfectly into
          // a hidden window is the failure this pair of fields catches.
          window_visible: win.isVisible(),
          window_bounds: b,
          engine_dir: __dirname
        }, dom);
        try { fs.writeFileSync(OUT, JSON.stringify(payload, null, 2)); } catch (e) {}
      }).catch(() => {});
    };
    probe(); setInterval(probe, 1000);
  }

  // Hot reload — opt-in: this is a DEVELOPMENT comfort, not a feature of the
  // capsule. In normal use it would hit the disk every second, forever, for a
  // file that never changes.
  if (process.env.CAPSULE_DEV === '1') {
    const PAGE = path.join(__dirname, 'orbe.html');
    fs.watchFile(PAGE, { interval: 1000 }, () => { if (win) win.webContents.reloadIgnoringCache(); });
  }
  // ⌘⇧B: show / hide
  globalShortcut.register('CommandOrControl+Shift+B', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.showInactive();
  });
});

// driven from the page
ipcMain.on('cap-show', () => { if (win && !win.isVisible()) win.showInactive(); });
ipcMain.on('cap-hide', () => { if (win && win.isVisible()) win.hide(); });
ipcMain.on('cap-quit', () => app.quit());

app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => globalShortcut.unregisterAll());
