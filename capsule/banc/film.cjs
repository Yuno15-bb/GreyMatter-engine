/* Films the orb for the README demo.

   ⚠ THREE TRAPS, each paid for once:
     · a HIDDEN window freezes the colours — `document.hidden` cuts the
       interpolation, the mechanic changes but never the hue;
     · a GRADIENT background draws a visible square around the thumbnail once
       it sits in the page — it needs the page's exact background colour, flat;
     · a step shorter than TWICE the cross-fade (1.4 s) never shows the
       stable object, only chained transitions.
   Encoding: img2webp -d 50 -lossy -q 88 -sharp_yuv -m 6. Below q≈88,
   the glass gradients and the 5 px text break back into macro-blocks.
*/
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path'), cp = require('child_process');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const OUT = process.env.FILM_OUT || '/tmp/film';
// ⚠ THE PAD IS FED THROUGH ITS INPUT, NOT THROUGH A HANDLE. First attempt:
//   a function exposed on `window` to set the lines. It overwrote
//   `window.__orbe`, already taken by the orb object (planche.cjs and silhouette.cjs
//   use it), then got repainted by the stream reader one second
//   later. So we write a REAL session file, in the format the page
//   already reads: the same code path as on a real desktop, nothing to
//   maintain in the page, and the shoot proves at the same time that this path
//   works. The file is deleted at the end.
//
//   Why it is needed: the pad shows the code REALLY written by the
//   current session. Perfect on someone's desktop, unpublishable in a
//   README — the online thumbnail showed for two weeks French text
//   pulled from the author's files.
const FLUX_DIR = path.join(require('os').homedir(), '.claude', 'companion', 'sessions');
const FLUX_FAUX = path.join(FLUX_DIR, 'zzz-film-demo.jsonl');
const DIFFS = [
  ['src/recall.py', ['+ def rank(q, notes):', '+   hits = bm25(q, notes)', '+   return hits[:5]',
                     '- # TODO: sort later', '+ log.debug("ranked")']],
  ['tests/test_recall.py', ['+ def test_empty():', '+   assert rank("", []) == []',
                            '+ def test_order():', '+   r = rank("cache", corpus)',
                            '+   assert r[0].id == "cache-lies"']],
  ['src/store.py', ['- notes = load_all()', '+ notes = load_page(offset)', '+ index.refresh()']],
  ['docs/recall.md', ['+ ## Ranking', '+ BM25 over title and tags.', '- Sorted by mtime.']],
  ['src/api.py', ['+ @route("/search")', '+ def search(q):', '+   return rank(q, store.all())']],
];
function poserFluxFictif() {
  fs.mkdirSync(FLUX_DIR, { recursive: true });
  fs.writeFileSync(FLUX_FAUX, DIFFS.map(([rel, diff]) =>
    JSON.stringify({ type: 'diff', rel, diff })).join('\n') + '\n');
}
const ETATS = [
  // ⚠ THE FILM'S RHYTHM IS NOT THE ORB'S RHYTHM. First version: twelve
  //   states at 1.4 s. But the mechanic CROSS-FADE alone lasts 1.4 s — so one
  //   never saw a stable state, only chained transitions.
  //   Rule: a step must last AT LEAST twice the cross-fade.
  //   The budget is taken from the NUMBER of states, never from their duration.
  // ⚠ `synthesizing` left out at the author's request.
  // The third field is the DETAIL shown under the state: it is a fictional
  // subject, not "demo". A debugging word under a README thumbnail reads
  // as an oversight, and that is what it is.
  // ⚠ DURATION IS PAID IN BYTES, AND QUALITY IS NOT NEGOTIABLE: the glass
  //   breaks into macro-blocks below q≈88 (see the header). At 45 f/s and q90, each
  //   second costs ~300 KB in the README — so we cut SECONDS, never
  //   quality. The floor stays "twice the cross-fade", i.e. 3 s.
  ['idle',        'idle', 2000, ''],
  ['gardening',   'busy', 3200, 'filing three new notes'],
  ['committing',  'busy', 3200, 'one zone per commit'],
  ['idle',        'idle', 2200, ''],
];
// ⚠ THE SHOOTING PLAN MOVES, THE FLOOR DOES NOT. `FILM_ETATS` replaces the
//   list above, in the format `state:milliseconds:detail|…` — it serves the
//   platform formats (15 s for LinkedIn/GitHub/portfolio, 20/09) without
//   touching the README demo, which stays the default. The 3 s floor is
//   REFUSED at run time, not commented: a step shorter than two cross-fades
//   never shows the stable object, and that is exactly the mistake the header
//   says was already paid for once.
if (process.env.FILM_ETATS) {
  ETATS.length = 0;
  for (const bloc of process.env.FILM_ETATS.split('|')) {
    const [etat, ms, ...reste] = bloc.split(':');
    const duree = Number(ms);
    if (!Number.isFinite(duree) || duree < 3000) {
      console.error(`⛔ ${etat}: ${ms} ms — below the 3000 ms floor (two cross-fades).`);
      process.exit(4);
    }
    ETATS.push([etat, etat === 'idle' ? 'idle' : 'busy', duree, reste.join(':')]);
  }
}
// ⚠ AND WE START FROM A SETTLED SHAPE. Without it, the film's first frame is a
//   cross-fade from the state the session left in status.json — on a
//   loop, that seam shows. `FILM_PRE` sets the opening state BEFORE
//   loading: the 4.3 s of waiting that follow exceed the 2.6 s of settling.
const PRE = process.env.FILM_PRE || '';

// ⚠ NEITHER `PAS` NOR `capturePage()`. A capture round trip costs ~50 ms: the
//   loop capped at 20 f/s, and the author saw it stutter next to the map,
//   filmed at 45. We go through the debugging protocol's SCREENCAST, which pushes
//   frames at the rendering pace instead of asking for them one by one.
// ⚠ AND WE SUPERSAMPLE: a window 3× larger + `setZoomFactor(3)`, so
//   the layout stays 150×150 in CSS pixels but is RENDERED at 450×450.
//   Scaled down to 336 px afterwards, it is smoothed. Without it, the glass edge
//   comes out as staircase steps — "pixelated on the edges", seen on the
//   published thumbnail, which was captured at display size.
// ⚠ ZOOM IS A SETTING, NOT A CONSTANT. Default 3: we supersample
//   so the glass edge stays smooth once the thumbnail is scaled down. But when
//   filming TO PLACE IT ON A REAL DESKTOP at real size, use `FILM_ZOOM=1`:
//   the orb is then rendered exactly as on the desktop (150 pt, 300 px on retina),
//   and the cut-out desktop background is used pixel for pixel, with no resampling.
const ZOOM = Number(process.env.FILM_ZOOM || 3);
const COTE = 150;

app.setPath('userData', '/private/tmp/claude-orbe-film');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  // ⚠ `show: false` FREEZES THE COLOURS. The page skips its interpolation when
  //   `document.hidden` is true — on purpose, we don't paint for nobody.
  //   But when filming that gives a grey orb: the mechanic changes, the hue
  //   never does. So filming needs a REALLY visible window.
  const w = new BrowserWindow({
    width: COTE * ZOOM, height: COTE * ZOOM, show: true, frame: false, x: 60, y: 120,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false, zoomFactor: ZOOM },
  });
  // ⚠ WE ALWAYS OPEN THE PAGE ON A BUSY STATE. The code pad only
  //   paints while the orb works (`if (occupe)` in orbe.html): opening on
  //   "idle" leaves it empty, and the guard below then refuses to film —
  //   seen on 20/09 when setting `FILM_PRE=idle` before loading. So we prime
  //   busy, check the pad, AND ONLY THEN set the wanted opening
  //   state. Without this explicit priming, the shoot depended on
  //   what the session had left in status.json — right by accident.
  cp.execFileSync('python3', [STATUS, 'busy', 'working', 'film']);
  poserFluxFictif();          // BEFORE loading: the page reads from its very first pass
  await w.loadFile(PAGE);
  w.webContents.setZoomFactor(ZOOM);
  await new Promise(r => setTimeout(r, 2500));

  await w.webContents.executeJavaScript(`(() => {
    const bg = document.createElement('div');
    bg.style.cssText = 'position:fixed;inset:0;z-index:-1;'
      // ⚠ A FLAT BACKGROUND, EXACTLY the page's. A gradient, even a subtle one,
      //   draws a visible SQUARE around the demo once placed in the
      //   README: the centre is lighter than the page, the edges are not. The
      //   seam shows, and that is what reads as "sloppy". #0d1117 = GitHub's
      //   dark-theme background, so the thumbnail disappears into the page.
      // ⚠ FILM_FOND sets an IMAGE instead of the flat background. It is the only
      //   honest way to film the glass over a real desktop: the glass is
      //   REALLY transparent, it refracts what is behind it. Compositing the
      //   background afterwards would give an opaque disc stuck on a photo.
      //   The image must be the exact cut-out of the area where the capsule lives,
      //   at the shooting resolution (COTE * ZOOM * 2 on retina).
      + (${JSON.stringify(process.env.FILM_FOND || '')}
          ? 'background:url("file://' + ${JSON.stringify(process.env.FILM_FOND || '')} + '") center/cover no-repeat'
          : 'background:#0d1117');
    document.body.prepend(bg);
    /* ⚠ SAME TRAP AS planche.cjs, found on 2026-08-04: raising #scene to
       z-index:1 puts the canvas IN FRONT OF the code pad and the label.
       The thumbnail published until then showed a MUTE orb — the
       scrolling code, half the point, had never been
       filmed. The background is enough with its z-index:-1; we explicitly raise
       both overlays. */
    document.getElementById('scene').style.zIndex = '0';
    document.getElementById('pave').style.zIndex = '2';
    document.getElementById('dit').style.zIndex = '2';
    return true; })()`);

  // ⚠ THE ORB SAVES FRAMES, AND IT SHOWS ON FILM. On the desktop it
  //   runs at 12 f/s at rest, 30 at work, 60 during a cross-fade (CADENCE in
  //   orbe.html, reset every 200 ms) — a permanent companion cannot
  //   pay 60 for life. Filmed as is, the 20/09 take counted 152 frames
  //   identical to the previous one out of 862, and 226 jumps: "a bit of stutter",
  //   word for word. So we freeze 60 f/s by making `setCadence` mute: the
  //   page's timer keeps calling, nothing moves any more.
  await w.webContents.executeJavaScript(
    `window.__orbe.setCadence(60); window.__orbe.setCadence = () => {}; true`);

  // ⚠ THE ONLY WITNESS THAT COUNTS IS THE TEXT ON SCREEN. The value returned by
  //   the injection was an inexplicable `NaN` for three attempts, while
  //   the real question — "what is written in the pad?" — had
  //   a simple, direct answer. We read the slots, look for French, and
  //   look for a word we just injected. Neither can be guessed.
  await new Promise(r => setTimeout(r, 1800));    // the scroll must have moved
  const lu = await w.webContents.executeJavaScript(
    `[...document.querySelectorAll('#pave .l')].map(e=>e.textContent).join(' ')`);
  if (/[àâçéèêëîïôùûœ]/i.test(lu)) {   // i18n-ok: this line LOOKS FOR French
    console.error(`⛔ French in the pad: "${lu.replace(/\s+/g,' ').trim().slice(0, 90)}"`);
    app.exit(5); return;
  }
  if (!/rank|bm25|recall|store|search/i.test(lu)) {
    console.error(`⛔ the bench lines are not on screen: "${lu.replace(/\s+/g,' ').trim().slice(0, 90)}"`);
    app.exit(6); return;
  }
  console.log(`  pad: in English, bench lines — "${lu.replace(/\s+/g,' ').trim().slice(0, 46)}…"`);

  // ⚠ THE OPENING STATE IS SET HERE, NOT BEFORE: the pad has just been
  //   checked, we can now come back down to idle. The 2.6 s are the
  //   bench's — below that, the film's first frame is an intermediate
  //   shape that exists in no state.
  if (PRE) {
    cp.execFileSync('python3',
      [STATUS, PRE === 'idle' ? 'idle' : 'busy', PRE === 'idle' ? '' : PRE].filter(x => x !== ''));
    await new Promise(r => setTimeout(r, 2600));
  }

  const dbg = w.webContents.debugger;
  dbg.attach('1.3');
  const images = [];
  const t0 = Date.now();
  if (process.env.FILM_PAS) {
    // ⚠ STEP BY STEP, ON A VIRTUAL CLOCK — the only shoot that CANNOT
    //   stutter. The screencast below films in real time: every
    //   rebuild of the pad on a state change (78–85 ms), every read
    //   of the status every 0.7 s (~28 ms) and every hiccup of the machine
    //   becomes a missing frame, hence a jolt — measured on 20/09 on
    //   take 4: 26 gaps over 25 ms out of 912 frames, one at each
    //   state change, right where the eye looks. Here we FREEZE the page's clock
    //   (Emulation.setVirtualTimePolicy), advance it by 16.667 ms, let
    //   the loop render a frame, capture it, and start again. Capture time
    //   no longer costs the animation anything: one frame = one sixtieth of a
    //   second of the orb, EXACTLY, whatever the machine's load.
    //   Speed on film is therefore the real speed of the states (the author, 20/09:
    //   "the animation speed must be the real speed of the states").
    // ⚠ BUT THE CSS ANIMATION CLOCK DOES NOT FOLLOW. Measured: under virtual
    //   time, performance.now, Date.now and timers advance by the requested
    //   budget; document.timeline advances by REAL elapsed time (983 ms
    //   real for 2,000 ms virtual). The three dots blinking under
    //   the label and the opacity fades of the pad and the label would
    //   therefore run three times too slowly on film. We take them over: each
    //   animation is paused as soon as it appears and its cursor advances
    //   in step with the virtual clock.
    await w.webContents.executeJavaScript(`(() => {
      const pris = new WeakMap();
      window.__pas = (ms) => {
        for (const a of document.getAnimations()) {
          let t = pris.get(a);
          if (t === undefined) { t = a.currentTime || 0; a.pause(); }
          t += ms; a.currentTime = t; pris.set(a, t);
        }
      };
      return true; })()`);
    const PAS = 1000 / 60;
    const expire = () => new Promise(res => {
      const h = (_e, m) => { if (m === 'Emulation.virtualTimeBudgetExpired') { dbg.off('message', h); res(); } };
      dbg.on('message', h);
    });
    await dbg.sendCommand('Emulation.setVirtualTimePolicy', { policy: 'pause' });
    // One step: the clock advances, the CSS animations follow, the render loop
    // (which runs on the screen's real rAF) paints once with that time.
    const pas = async () => {
      const p = expire();
      await dbg.sendCommand('Emulation.setVirtualTimePolicy', { policy: 'advance', budget: PAS });
      await p;
      await w.webContents.executeJavaScript(
        `window.__pas(${PAS}); new Promise(r => requestAnimationFrame(() => r()))`);
    };
    // The plan, played frame by frame. The state change is read by the page
    // immediately (`lire()`), not at the next turn of its 700 ms timer:
    // each state thus takes exactly the same number of frames.
    const jouer = async (capturer) => {
      for (const [etat, st, duree, detail] of ETATS) {
        cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', detail]
                        .filter(x => x !== ''));
        await w.webContents.executeJavaScript('window.__lire(); true');
        for (let n = Math.round(duree / PAS); n > 0; n--) {
          await pas();
          if (capturer) {
            const { data } = await dbg.sendCommand('Page.captureScreenshot', { format: 'png' });
            images.push({ d: data, t: images.length * PAS / 1000 });
          }
        }
      }
    };
    // ⚠ A DRY RUN BEFORE THE FILMED RUN, FOR THE LOOP SEAM. The
    //   colours travel by smoothing (4.5 % per tick at 30 Hz): three seconds
    //   after the last change, ~11 % of the way to the idle hue is still
    //   left. The first frame, though, starts from an idle set at 100 %. On a
    //   loop, that hue-to-hue seam shows. Played twice, the plan
    //   starts exactly in the state where it ends.
    if (process.env.FILM_BLANC) await jouer(false);
    // ⚠ SPEED ON FILM MUST BE THE ORB'S REAL SPEED (the author, 20/09).
    //   It is proven on the animation's own clock: `uTime` is the
    //   time the shader saw pass. If it advances by as many seconds as the
    //   film lasts, the orb runs at its speed — neither slowed nor sped up. We do
    //   not trust that "virtual time seems to work".
    const horloge = () => w.webContents.executeJavaScript('window.__orbe._u.uTime.value');
    const tA = await horloge();
    await jouer(true);
    const tB = await horloge();
    const duFilm = images.length / 60, deLOrbe = tB - tA;
    console.log(`  speed: ${deLOrbe.toFixed(3)} s of animation for ${duFilm.toFixed(3)} s of film ` +
                `(gap ${((deLOrbe / duFilm - 1) * 100).toFixed(2)} %)`);
    if (Math.abs(deLOrbe / duFilm - 1) > 0.02) {
      console.error(`⛔ the orb does not run at its real speed — the film would be ${deLOrbe < duFilm ? 'slowed' : 'sped up'}.`);
      app.exit(7); return;
    }
    await dbg.sendCommand('Emulation.setVirtualTimePolicy', { policy: 'advance', budget: 1e9 });
  } else {
  // The screencast: attach the debugger, listen, acknowledge every frame.
  // Without the acknowledgement, Chromium stops sending them after a few.
  dbg.on('message', (_e, methode, params) => {
    if (methode !== 'Page.screencastFrame') return;
    // The timestamp comes from the compositor: it says WHEN the frame
    // existed. Without it, we assign a constant rate to frames that are
    // not constant, and the film speeds up or slows down with the capture gaps.
    images.push({ d: params.data, t: params.metadata.timestamp });
    dbg.sendCommand('Page.screencastFrameAck', { sessionId: params.sessionId }).catch(() => {});
  });
  await dbg.sendCommand('Page.enable');
  await dbg.sendCommand('Page.startScreencast',
    { format: 'png', maxWidth: COTE * ZOOM, maxHeight: COTE * ZOOM, everyNthFrame: 1 });

  for (const [etat, st, duree, detail] of ETATS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', detail]
                    .filter(x => x !== ''));
    await new Promise(r => setTimeout(r, duree));
  }
  await dbg.sendCommand('Page.stopScreencast');
  }
  const secondes = (Date.now() - t0) / 1000;
  // List for ffmpeg's `concat` demuxer: each frame carries its
  // real duration, and `fps=60` then resyncs to a constant rate.
  const liste = [];
  images.forEach((img, i) => {
    const nom = String(i).padStart(4, '0') + '.png';
    fs.writeFileSync(path.join(OUT, nom), Buffer.from(img.d, 'base64'));
    const suiv = images[i + 1];
    const duree = suiv ? Math.max(0.001, suiv.t - img.t) : 1 / 60;
    liste.push(`file '${nom}'`, `duration ${duree.toFixed(5)}`);
  });
  liste.push(`file '${String(images.length - 1).padStart(4, '0')}.png'`);   // concat: the last one repeats
  fs.writeFileSync(path.join(OUT, 'liste.txt'), liste.join('\n') + '\n');
  // Regularity of the take: the only number that predicts stutter.
  const dts = images.slice(1).map((img, i) => (img.t - images[i].t) * 1000);
  const trous = dts.filter(x => x > 25).length;
  const doublons = images.slice(1).filter((img, i) => img.d === images[i].d).length;
  console.log(`  intervals: median ${dts.sort((a, b) => a - b)[dts.length >> 1].toFixed(1)} ms, ` +
              `max ${Math.max(...dts).toFixed(1)} ms, gaps > 25 ms: ${trous}, duplicate frames: ${doublons}`);
  fs.rmSync(FLUX_FAUX, { force: true });
  if (process.env.FILM_PAS) {
    console.log(`${images.length} frames step by step = ${(images.length / 60).toFixed(2)} s of orb at exactly 60 f/s ` +
                `(shot in ${secondes.toFixed(1)} real s), in ${OUT}`);
  } else {
    const ips = Math.round(images.length / secondes);
    console.log(`${images.length} frames in ${secondes.toFixed(1)} s → ${ips} f/s, ${COTE * ZOOM}px, in ${OUT}`);
    // A 20 f/s film next to a map at 45 shows immediately: we refuse.
    if (ips < 35) console.error(`⛔ ${ips} f/s — too slow. Is the window really visible?`);
  }
  app.quit();
});
app.on('window-all-closed', () => app.quit());
