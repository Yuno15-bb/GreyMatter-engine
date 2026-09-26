/* Measure actual frame intervals for each state.

   Requested cadence is not measured cadence. This bench observes the render
   loop and reports the median and worst interval, since stalls are visible.
   The capsule deliberately does not run at 60 fps everywhere: doing so used
   about 12% CPU continuously. Each state has its own target. */
'use strict';
const { app, BrowserWindow } = require('electron');
const cp = require('child_process');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const CAS = [['idle', 'idle', 12], ['gardening', 'busy', 30], ['synthesizing', 'busy', 30]];

app.setPath('userData', '/private/tmp/orb-bench-cadence');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  const w = new BrowserWindow({
    width: 150, height: 150, show: true, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  // Timestamp the actual render path at requestAnimationFrame.
  await w.webContents.executeJavaScript(`(() => {
    window.__t = [];
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (cb) => raf((ts) => { window.__t.push(performance.now()); cb(ts); });
    return true; })()`);

  console.log('state         target    actual    median    worst    frames');
  for (const [etat, st, voulu] of CAS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'cadence']
                    .filter(x => x !== ''));
    // Let the 1.4 s mechanic fade finish before measuring the steady state.
    await new Promise(r => setTimeout(r, 3000));
    await w.webContents.executeJavaScript('window.__t = []; true');
    const DUREE = 6000;
    await new Promise(r => setTimeout(r, DUREE));
    const t = await w.webContents.executeJavaScript('window.__t');
    const dts = t.slice(1).map((v, i) => v - t[i]).sort((a, b) => a - b);
    if (!dts.length) { console.log(`${etat.padEnd(13)} no frames`); continue; }
    const med = dts[Math.floor(dts.length / 2)];
    const pire = dts[dts.length - 1];
    const reel = (t.length - 1) / (DUREE / 1000);
    console.log(`${etat.padEnd(13)} ${String(voulu).padStart(4)} fps ` +
                `${reel.toFixed(1).padStart(6)} fps ${med.toFixed(1).padStart(7)} ms ` +
                `${pire.toFixed(1).padStart(7)} ms ${String(t.length).padStart(6)}`);
  }

  // The transition alone needs 60 fps so the mechanic fade stays smooth.
  cp.execFileSync('python3', [STATUS, 'busy', 'committing', 'cadence']);
  await w.webContents.executeJavaScript('window.__t = []; true');
  await new Promise(r => setTimeout(r, 1400));
  const tt = await w.webContents.executeJavaScript('window.__t');
  const d = tt.slice(1).map((v, i) => v - tt[i]).sort((a, b) => a - b);
  console.log(`transition      60 fps ${((tt.length - 1) / 1.4).toFixed(1).padStart(6)} fps ` +
              `${d.length ? d[Math.floor(d.length / 2)].toFixed(1).padStart(7) : '   —'} ms ` +
              `${d.length ? d[d.length - 1].toFixed(1).padStart(7) : '   —'} ms`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
