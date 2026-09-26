/* Compare orb states over a simulated desktop, one state per column.

   Glass cannot be judged on black: transparency and opacity look alike there.
   The gradient and text behind the orb reveal what a desktop would show.

   Usage: ./node_modules/.bin/electron banc/planche.cjs [opacity values]
   Example: banc/planche.cjs 1 0.55 0 produces three comparable rows. */
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path'), cp = require('child_process');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const SORTIE = process.env.BANC_SORTIE || '/tmp/orb-bench';
const DOSAGES = process.argv.slice(2).filter(a => !isNaN(parseFloat(a)))
                  .map(Number);
const VERRES = DOSAGES.length ? DOSAGES : [0.55];
const ETATS = [['idle', 'idle'], ['challenging', 'busy'], ['correcting', 'busy'],
               ['synthesizing', 'busy'], ['committing', 'busy']];

app.setPath('userData', '/private/tmp/orb-bench-sheet');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.mkdirSync(SORTIE, { recursive: true });
  const w = new BrowserWindow({
    width: 150, height: 150, show: false, frame: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  /* Use three backgrounds. A nearly white desktop can hide the glass rim and
     light labels; dark and colourful backgrounds alone cannot reveal that. */
  const FONDS = {
    desktop: ['linear-gradient(135deg,#1d4ed8,#7c3aed 45%,#f59e0b)', 'rgba(255,255,255,.9)'],
    light:   ['linear-gradient(135deg,#fdfdfd,#eef1f6 55%,#e7e2d8)', 'rgba(20,24,32,.75)'],
    dark:    ['linear-gradient(135deg,#0b0d12,#141922)',             'rgba(255,255,255,.55)'],
  };
  const poserFond = (nom) => w.webContents.executeJavaScript(`(() => {
    document.getElementById('fondBanc')?.remove();
    const bg = document.createElement('div');
    bg.id = 'fondBanc';
    bg.style.cssText = 'position:fixed;inset:0;z-index:-1;padding:6px;overflow:hidden;'
      + 'white-space:pre;font:9px/13px monospace;'
      + 'color:${FONDS[nom][1]};background:${FONDS[nom][0]}';
    bg.textContent = Array.from({length:12}, (_,i) => 'desktop ' + i + ' ~ text').join('\\n');
    document.body.prepend(bg);
    /* ⚠ THE BENCH WAS HIDING WHAT IT WAS MEANT TO SHOW (found 2026-08-04).
       This line raised #scene to z-index:1 — the canvas then sat IN FRONT of
       the code pad and the label, neither of which has a z-index. So every
       sheet made since 2026-08-03 shows a MUTE orb, and the pad was nearly
       "fixed" on the strength of that image. The background alone is enough
       (z-index:-1); the overlays are raised explicitly.
       ⚠ 2026-08-08: #fiche was missing from the list — so the "what on" line was
         ABSENT from every sheet, even though the bench takes care to give it a
         real slug right underneath. A sheet that does not show the very line
         whose legibility is being judged proves nothing. */
    document.getElementById('scene').style.zIndex = '0';
    document.getElementById('pave').style.zIndex = '2';
    document.getElementById('dit').style.zIndex = '2';
    document.getElementById('fiche').style.zIndex = '2';
    return true; })()`);

  const FONDS_DEMANDES = (process.env.BANC_FONDS || 'desktop,light,dark').split(',');
  const faits = [];
  for (const fond of FONDS_DEMANDES) {
   await poserFond(fond);
   for (const verre of VERRES) {
    for (const [etat, st] of ETATS) {
      /* ⚠ The 3rd argument of brain_status.py is the DETAIL, not a source: the
         bench was putting the word "banc" there, and ever since the "what on"
         line exists, the sheet displayed that word as the work landmark. A
         sheet must show what the user will see — so a real note slug, the kind
         `on_fiche_write` would write. */
      cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '',
                      st === 'busy' ? 'capsule-orbe-agents' : ''].filter(x => x !== ''));
      await w.webContents.executeJavaScript(`window.__orbe.setVerre(${verre})`);
      // Wait past the 1.4 s mechanic fade before capturing a stable state.
      await new Promise(r => setTimeout(r, 2600));
      const p = path.join(SORTIE, `${fond}-v${verre}-${etat}.png`);
      fs.writeFileSync(p, (await w.webContents.capturePage()).toPNG());
      faits.push(p);
    }
   }
  }
  console.log(`${faits.length} captures in ${SORTIE}`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
