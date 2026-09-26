/* Measure the mesh bounds in each state to place overlays from evidence.
   Captured bounds use physical pixels. On a 2x retina display, a 150 px CSS
   window produces a 300 px bitmap; divide before using the bounds in CSS. */
'use strict';
const { app, BrowserWindow } = require('electron');
const cp = require('child_process');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const ETATS = [['idle', 'idle'], ['challenging', 'busy'], ['correcting', 'busy'],
               ['synthesizing', 'busy'], ['committing', 'busy']];

app.setPath('userData', '/private/tmp/orb-bench-silhouette');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  const w = new BrowserWindow({
    width: 150, height: 150, show: false, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));
  // Hide overlays so the bounds measure the mesh itself.
  await w.webContents.executeJavaScript(
    `document.getElementById('dit').style.display='none';
     document.getElementById('pave').style.display='none'; true`);

  /* Check layout before measuring the silhouette. A removed CSS rule once
     placed the 300 px retina canvas at its buffer size inside a 150 px window.
     The orb overflowed while centred overlays looked displaced. Nothing
     crashed; the error was visible only on the desktop. */
  const geo = await w.webContents.executeJavaScript(`(() => {
    const c = document.getElementById('c');
    return { css: [c.clientWidth, c.clientHeight], fen: [innerWidth, innerHeight] }; })()`);
  const carre = geo.css[0] === geo.css[1];
  const tient = geo.css[0] === geo.fen[0] && geo.css[1] === geo.fen[1];
  console.log((carre && tient ? 'OK    ' : 'FAIL  ') +
    `canvas ${geo.css[0]}x${geo.css[1]} in window ${geo.fen[0]}x${geo.fen[1]}`);

  for (const [etat, st] of ETATS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'banc']
                    .filter(x => x !== ''));
    // Wait through the 1.4 s mechanic fade before capturing a stable shape.
    await new Promise(r => setTimeout(r, 2600));
    const img = await w.webContents.capturePage();
    const { width, height } = img.getSize();
    const buf = img.getBitmap();                 // BGRA, four bytes per pixel
    let haut = height, bas = -1, gauche = width, droite = -1;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (buf[(y * width + x) * 4 + 3] > 24) {   // Ignore the faint halo.
          if (y < haut) haut = y;
          if (y > bas) bas = y;
          if (x < gauche) gauche = x;
          if (x > droite) droite = x;
        }
      }
    }
    const css = (v) => (v / (height / 150)).toFixed(0);
    console.log(`${etat.padEnd(14)} css → top=${css(haut)} bottom=${css(bas)} ` +
                `left=${css(gauche)} right=${css(droite)}`);
  }
  app.quit();
});
app.on('window-all-closed', () => app.quit());
