/* Exercise dragging without moving a physical mouse.

   An earlier check compared window positions before and during the drag. It
   passed only when a person happened to move the mouse: a stationary cursor
   correctly leaves the window still. Check the computed cursor minus grip
   position instead. A centre press must start tracking, release must stop it,
   and a corner press must leave the desktop clickable. The corner case catches
   a hit test that always returns true. */
'use strict';
const { app, BrowserWindow, screen, ipcMain } = require('electron');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
app.setPath('userData', '/private/tmp/orb-bench-drag');

let win, dragTimer = null, tours = 0, prise = null;
ipcMain.on('cap-interactive', () => {});
ipcMain.on('cap-drag-begin', () => {
  if (!win || dragTimer) return;
  const c0 = screen.getCursorScreenPoint(), b0 = win.getBounds();
  prise = { dx: c0.x - b0.x, dy: c0.y - b0.y };
  tours = 0;
  dragTimer = setInterval(() => {
    const c = screen.getCursorScreenPoint();
    win.setPosition(Math.round(c.x - prise.dx), Math.round(c.y - prise.dy));
    tours++;
  }, 16);
});
ipcMain.on('cap-drag-end', () => { clearInterval(dragTimer); dragTimer = null; });

const dire = (ok, texte) => console.log(`${ok ? 'OK    ' : 'FAIL  '} ${texte}`);

const clic = async (x, y, ms = 400) => {
  win.webContents.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 });
  await new Promise(r => setTimeout(r, ms));
  const etat = { bounds: win.getBounds(), tours, arme: dragTimer !== null, prise };
  win.webContents.sendInputEvent({ type: 'mouseUp', x, y, button: 'left', clickCount: 1 });
  await new Promise(r => setTimeout(r, 200));
  return etat;
};

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  win = new BrowserWindow({
    width: 150, height: 150, x: 400, y: 400, show: true, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  await win.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  // Centre: inside the disk.
  const c = await clic(75, 75);
  dire(c.arme, 'centre  : tracking started');
  dire(c.tours > 10, `centre  : tracking ran (${c.tours} ticks in 400 ms)`);
  // Compare with the computed target, not with the previous window position.
  const cur = screen.getCursorScreenPoint();
  const visee = { x: Math.round(cur.x - c.prise.dx), y: Math.round(cur.y - c.prise.dy) };
  const colle = Math.abs(c.bounds.x - visee.x) <= 2 && Math.abs(c.bounds.y - visee.y) <= 2;
  dire(colle, `centre  : window follows cursor minus grip (${c.bounds.x},${c.bounds.y} vs ${visee.x},${visee.y})`);
  dire(dragTimer === null, 'release : tracking stopped');

  // Corner: outside the disk; tracking must stay off.
  const b2 = win.getBounds();
  const k = await clic(6, 6);
  dire(!k.arme, 'corner  : tracking stayed off; desktop remains clickable');
  dire(k.bounds.x === b2.x && k.bounds.y === b2.y, 'corner  : window stayed still');
  app.quit();
});
app.on('window-all-closed', () => app.quit());
