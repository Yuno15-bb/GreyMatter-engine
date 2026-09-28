(function () {
  const C = window.GMTRCotes, K = window.GMTRCourbes;
  if (!C || !K) { console.error('gmtr-marque : load marque-cotes.js first.'); return; }

  const PENTES = new Map();
  function pentes(table) {
    let p = PENTES.get(table);
    if (p) return p;
    const xs = table.map((q) => q[0]), ys = table.map((q) => q[1]), n = xs.length;
    const d = [], m = [];
    for (let i = 0; i < n - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
    m.push(d[0]);
    for (let i = 1; i < n - 1; i++) m.push((d[i - 1] + d[i]) / 2);
    m.push(d[n - 2]);
    for (let i = 0; i < n - 1; i++) {
      if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
      const a = m[i] / d[i], b = m[i + 1] / d[i];
      if (a * a + b * b > 9) { const k = 3 / Math.sqrt(a * a + b * b); m[i] = k * a * d[i]; m[i + 1] = k * b * d[i]; }
    }
    p = { xs, ys, m }; PENTES.set(table, p); return p;
  }
  function lire(table, t) {
    const { xs, ys, m } = pentes(table);
    if (t <= xs[0]) return ys[0];
    if (t >= xs[xs.length - 1]) return ys[ys.length - 1];
    let i = 0;
    while (i < xs.length - 2 && t > xs[i + 1]) i++;
    const h = xs[i + 1] - xs[i], u = (t - xs[i]) / h, u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * ys[i] + (u3 - 2 * u2 + u) * h * m[i]
         + (-2 * u3 + 3 * u2) * ys[i + 1] + (u3 - u2) * h * m[i + 1];
  }

  const base = ((document.currentScript && document.currentScript.src) || '').replace(/[^/]*$/, '');
  function charger(nom) { const im = new Image(); im.src = base + nom; return im; }
  const IMG = { carre: charger('marque-carre.png'), mot: charger('marque-mot.png') };
  const pret = Promise.all(Object.keys(IMG).map((k) => (IMG[k].decode ? IMG[k].decode().catch(() => {})
    : new Promise((r) => { IMG[k].onload = IMG[k].onerror = r; }))));

  const cache = new Map();
  function planche(img, larg, haut, encre) {
    if (!img.naturalWidth) return null;
    const cle = img.src + '|' + Math.round(larg) + '|' + Math.round(haut) + '|' + encre;
    let c = cache.get(cle);
    if (c) return c;
    let src = img, sw = img.naturalWidth || img.width, sh = img.naturalHeight || img.height;
    while (sw > larg * 2 && sw > 2) {
      const n = document.createElement('canvas');
      n.width = sw >> 1; n.height = Math.max(1, sh >> 1);
      n.getContext('2d').drawImage(src, 0, 0, n.width, n.height);
      src = n; sw = n.width; sh = n.height;
    }
    c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(larg)); c.height = Math.max(1, Math.round(haut));
    const g = c.getContext('2d');
    g.drawImage(src, 0, 0, c.width, c.height);
    g.globalCompositeOperation = 'source-in';
    g.fillStyle = encre; g.fillRect(0, 0, c.width, c.height);
    if (cache.size > 8) cache.clear();
    cache.set(cle, c);
    return c;
  }

  let COULEURS = null;
  function jeton(nom, defaut) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
    return v || defaut;
  }
  function couleurs() {
    if (!COULEURS) COULEURS = {
      encre: jeton('--marque-encre', '#f2f2ee'),
      bandes: [jeton('--marque-b1', '#f2f2ee'), jeton('--marque-b2', '#a9a6ad'), jeton('--marque-b3', '#5e5b62')],
    };
    return COULEURS;
  }

  function rubans(ctx, xg, xd, y, ep, filet, couleurs, net) {
    if (!(xd - xg > 0.25) || ep < 0.25) return;
    for (let i = 0; i < couleurs.length; i++) {
      const yi = y + i * (ep + filet);
      ctx.fillStyle = couleurs[i];
      if (net) ctx.fillRect(net(xg), net(yi), Math.max(net(1 / net.d), net(xd) - net(xg)), Math.max(net(1 / net.d), net(yi + ep) - net(yi)));
      else ctx.fillRect(xg, yi, xd - xg, ep);
    }
  }
  function arrondi(dpr) { const f = (v) => Math.round(v * dpr) / dpr; f.d = dpr; return f; }

  function echelleDe(ctx) { const t = ctx.getTransform ? ctx.getTransform() : null; return t && t.a ? t.a : 1; }

  function carre(ctx, o) {
    const c = C.carre, MV = C.MV, dpr = echelleDe(ctx);
    const larg = o.larg, haut = o.haut;
    const ech = (o.hbloc != null ? o.hbloc : haut * (o.part == null ? 0.62 : o.part)) / c.hb;
    const u = (v) => v * ech;
    const x0f = o.ox != null ? o.ox : (larg - u(c.bloc)) / 2;
    const oy = o.oy != null ? o.oy : (haut - u(c.hb)) / 2;
    const anime = o.tr != null && o.tr < K.ARRIVEE;
    const tr = anime ? o.tr : K.ARRIVEE;
    const net = anime ? null : arrondi(dpr);
    const col = o.couleurs || couleurs();
    const f = tr < K.T_MOT ? 0 : lire(K.ETIRE, tr);
    const fuite = K.FUITE * larg;
    const x = fuite + f * (x0f - fuite);
    ctx.clearRect(0, 0, larg, haut);
    if (f > 0) {
      const xd = x + u(c.bloc) * f;
      rubans(ctx, xd - (xd - x) * lire(K.OUVRE, tr), xd, oy + u(c.bandes_y),
             u((c.bandes_h - 2 * c.filet_b) / 3), u(c.filet_b), col.bandes, net);
    }
    let xg = larg * lire(K.SORTIE, tr);
    const xdr = larg * lire(ENTREE, tr);
    if (f > 0) xg = Math.max(xg, x + u(c.bloc) * f + u(c.bandes_h) * f);
    const epS = u((c.hb - 2 * c.filet_s) / 3), fil = u(c.filet_s);
    if (o.echo && tr > K.T_MOT) {
      const bord = (t) => { const ff = t < K.T_MOT ? 0 : lire(K.ETIRE, t), xx = fuite + ff * (x0f - fuite);
        let g = larg * lire(K.SORTIE, t); if (ff > 0) g = Math.max(g, xx + u(c.bloc) * ff + u(c.bandes_h) * ff); return g; };
      const A = [0.5, 0.32, 0.2, 0.11, 0.05];
      let droite = xg;
      for (let k = 1; k <= A.length; k++) {
        const g = Math.max(bord(tr - k * 0.04), x + u(c.bloc) * f + 2);
        if (g >= droite) break;
        ctx.globalAlpha = A[k - 1]; rubans(ctx, Math.floor(g / 4) * 4, droite, oy, epS, fil, col.bandes, null);
        droite = Math.floor(g / 4) * 4;
      }
      ctx.globalAlpha = 1;
    }
    rubans(ctx, xg, xdr, oy, epS, fil, col.bandes, null);
    if (f > 0) {
      const p = planche(IMG.carre, u(c.bloc) * dpr, u(c.ink + 2 * MV) * dpr, col.encre);
      if (p) ctx.drawImage(p, x, oy - u(MV), u(c.bloc) * f, u(c.ink + 2 * MV));
    }
    if (o.trame) { ctx.save(); ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = trame(ctx, dpr); ctx.fillRect(0, 0, larg, haut); ctx.restore(); }
  }

  const TRAMES = new WeakMap();
  function trame(ctx, dpr) {
    let t = TRAMES.get(ctx);
    if (t) return t;
    const pas = 3, c = document.createElement('canvas'); c.width = pas * 2; c.height = pas * 2; // i18n-ok
    const x = c.getContext('2d');
    x.fillStyle = 'rgba(0,0,0,0.18)'; x.fillRect(0, 0, c.width, c.height);
    x.globalCompositeOperation = 'destination-out'; x.fillStyle = '#000';
    for (const [px, py] of [[0, 0], [pas, pas], [pas * 2, 0], [0, pas * 2], [pas * 2, pas * 2]]) { // i18n-ok
      x.beginPath(); x.arc(px + 0.5, py + 0.5, 1.15, 0, 7); x.fill(); }
    t = ctx.createPattern(c, 'repeat'); t.setTransform(new DOMMatrix().scale(1 / dpr));
    TRAMES.set(ctx, t); return t;
  }

  function mot(ctx, o) {
    const m = C.mot, MV = C.MV, dpr = echelleDe(ctx);
    const larg = o.larg, haut = o.haut, total = m.bandes_l + m.ecart + m.bloc;
    const ech = (o.hcap != null ? o.hcap / m.ink : (larg * (o.part == null ? 0.78 : o.part)) / total);
    const u = (v) => v * ech;
    const x0f = o.ox != null ? o.ox : (larg - u(total)) / 2;
    const oy = o.oy != null ? o.oy : (haut - u(m.ink)) / 2;
    const anime = o.tr != null && o.tr < K.ARRIVEE;
    const tr = anime ? o.tr : K.ARRIVEE;
    const net = anime ? null : arrondi(dpr);
    const col = o.couleurs || couleurs();
    const ep = (m.bandes_h - 2 * m.filet_b) / 3;
    const f = tr < K.T_MOT ? 0 : lire(K.ETIRE, tr);
    const fuite = K.FUITE * larg;
    const x = fuite + f * (x0f - fuite);
    ctx.clearRect(0, 0, larg, haut);
    if (f > 0) {
      const xd = x + u(m.bandes_l) * f;
      rubans(ctx, xd - (xd - x) * lire(K.OUVRE, tr), xd, oy, u(ep), u(m.filet_b), col.bandes, net);
    }
    let xg = larg * lire(K.SORTIE, tr);
    const xdr = larg * lire(ENTREE, tr);
    if (f > 0) xg = Math.max(xg, x + u(total) * f + u(ep) * f);
    rubans(ctx, xg, xdr, oy, u(ep), u(m.filet_b), col.bandes, null);
    if (f > 0) {
      const p = planche(IMG.mot, u(m.bloc) * dpr, u(m.ink + 2 * MV) * dpr, col.encre);
      if (p) ctx.drawImage(p, x + u(m.bandes_l + m.ecart) * f, oy - u(MV), u(m.bloc) * f, u(m.ink + 2 * MV));
    }
  }

  const ENTREE = K.SORTIE.map(([t, v]) => [
    K.ENTREE[0][0] + (t - K.SORTIE[0][0]) / (K.SORTIE.at(-1)[0] - K.SORTIE[0][0])
      * (K.ENTREE.at(-1)[0] - K.ENTREE[0][0]), v]);
  const PART_OUVERTURE = 0.37;
  const FIN_CHARGEMENT = 0.72, TR_FIN = K.T_MOT + ((0.72 - 0.15) / (1 - 0.15)) * (K.ARRIVEE - K.T_MOT);
  function instant(v) {
    const q = Math.max(0, Math.min(1, v));
    if (q < PART_OUVERTURE) return (q / PART_OUVERTURE) * K.T_MOT;
    if (q < FIN_CHARGEMENT) return K.T_MOT + ((q - PART_OUVERTURE) / (FIN_CHARGEMENT - PART_OUVERTURE)) * (TR_FIN - K.T_MOT);
    return TR_FIN + ((q - FIN_CHARGEMENT) / (1 - FIN_CHARGEMENT)) * (K.ARRIVEE - TR_FIN);
  }


  function cadre(hbloc) {
    const c = C.carre;
    return { larg: (hbloc / c.hb) * c.bloc * 3.4, haut: hbloc / 0.62 };
  }

  window.GMTRMarque = { pret, carre, mot, instant, cadre, couleurs,
                        oublier() { COULEURS = null; cache.clear(); },
                        COTES: C, COURBES: K };
})();
