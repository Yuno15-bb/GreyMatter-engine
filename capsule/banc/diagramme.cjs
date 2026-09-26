/* Renders an HTML diagram to a crisp (retina) PNG, cropped to its content.

   ⚠ THREE TRAPS, all paid for once on this very diagram:
     · Chromium REMEMBERS the zoom factor per origin, in the profile. An earlier
       run at zoom 2 was still applying to later renders: the layout doubled and
       the capture looked cut off. We reset the zoom to 1.
     · `scrollWidth` and `max-content` LIE about flexbox: boxes that compress let
       the text overflow without the box growing. Hence a FIXED-column grid in
       archi.html — a width verifiable by arithmetic, plus a check of the real
       right edge here.
     · Measuring the height over `document.querySelectorAll('*')` includes `html`,
       whose rectangle is the height of the WINDOW, not of the content: so we
       measure under `document.body`.

   Usage: SRC=... OUT=... W=1700 electron banc/diagramme.cjs
*/
const { app, BrowserWindow } = require('electron'); const fs=require('fs');
app.setPath('userData','/private/tmp/claude-diag-'+Date.now());
const SRC=process.env.SRC, OUT=process.env.OUT, W=Number(process.env.W||1760);
app.whenReady().then(async()=>{ if(app.dock)app.dock.hide();
  const w=new BrowserWindow({width:W,height:1200,show:false,frame:false,backgroundColor:'#0d1117'});
  await w.loadFile(SRC);
  // ⚠ Chromium REMEMBERS the zoom factor per origin, in the profile. An earlier
  //   run at zoom 2 kept applying to every later render: the layout doubled, so
  //   the capture looked cut off while the right-edge measurement said "it
  //   fits". We reset it to 1.
  w.webContents.setZoomFactor(1);
  await new Promise(r=>setTimeout(r,900));
  // ⚠ We do not trust scrollWidth: we read the real RIGHT edge of every element.
  //   A flexbox overflow does not make scrollWidth grow.
  const m = await w.webContents.executeJavaScript(`(()=>{
    // ⚠ We EXCLUDE html and body: their rectangle is the height of the WINDOW,
    //   not of the content. Including them always returned the starting size.
    let r=0,b=0; for (const e of document.body.querySelectorAll('*')) {
      const k=e.getBoundingClientRect(); if(k.width){ r=Math.max(r,k.right); b=Math.max(b,k.bottom); } }
    return [Math.ceil(r), Math.ceil(b)]; })()`);
  console.log('right edge', m[0], '· bottom', m[1], '· window', W, m[0] > W ? '-> OVERFLOWS' : '-> fits');
  w.setContentSize(W, m[1]+38);
  await new Promise(r=>setTimeout(r,600));
  fs.writeFileSync(OUT,(await w.webContents.capturePage()).toPNG());
  console.log('OK'); app.quit(); });
app.on('window-all-closed',()=>app.quit());
