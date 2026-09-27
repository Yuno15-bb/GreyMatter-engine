(function () {
  const M = window.GMTRMotion;
  const $ = (s, r = document) => r.querySelector(s);
  const nombre = (n) => Number(n).toLocaleString('en-US');

  const shell = document.createElement('div');
  shell.id = 'gmtr-shell'; shell.className = 'chargement';
  shell.innerHTML = `
    <header class="g-entete m-pixel"><span class="g-marque"><canvas class="g-logo actionnable" id="g-logo" role="button" aria-label="GMTR — home"></canvas><span>· map</span></span><span class="g-etat" id="g-etat"></span><span class="g-lieu" id="g-lieu" hidden></span>

      <label class="g-cherche actionnable" id="g-cherche"><span class="g-cherche-signe" aria-hidden="true">/</span><input id="g-cherche-champ" type="search" placeholder="search notes" autocomplete="off" spellcheck="false" aria-label="Search notes" aria-controls="g-resultats-liste"></label>
      <nav class="g-modes"><span class="g-mode actionnable" data-mode="struct"><span>panel</span></span><span class="g-mode actionnable" data-mode="sens"><span>graph</span></span></nav></header>
    <aside class="g-regions g-plaque m-pixel" id="g-regions">

      <div class="g-titre"><span class="g-axes"><span class="g-axe actionnable" data-axe="region">region</span> / <span class="g-axe actionnable" data-axe="topic">topic</span></span><span>share · notes</span></div>
      <ol id="g-liste"></ol>
      <ol id="g-liste-sujets" hidden></ol>
    </aside>
    <section class="g-journal m-pixel" id="g-journal">

      <div class="g-colonnes">
        <div class="g-col g-plaque" id="g-col-log">

          <div class="g-agent" id="g-agent"><span class="puce">○</span><span class="quoi" id="g-agent-quoi">reading state/status.json…</span><span class="age" id="g-agent-age"></span></div>
          <div class="g-titre"><span id="g-journal-titre">system log</span><span id="g-journal-etat"></span></div>
          <ol id="g-journal-liste"></ol>
        </div>
        <section class="g-col g-ecrit g-plaque m-pixel" id="g-ecrit">
          <div class="g-titre"><span id="g-ecrit-tete">live write</span><span id="g-ecrit-etat"></span></div>
          <pre class="g-ecrit-corps" id="g-ecrit-corps"></pre>
        </section>
      </div>
    </section>
    <section class="g-resultats g-plaque m-pixel" id="g-resultats" hidden>
      <div class="g-titre"><span id="g-resultats-titre">results</span><span id="g-resultats-n"></span></div>
      <ol id="g-resultats-liste" role="listbox"></ol>
    </section>
    <section class="g-fiche g-plaque m-pixel" id="g-fiche" hidden> <!-- i18n-ok -->
      <div class="g-fiche-tete" id="g-fiche-tete"><span id="g-fiche-region"></span><span id="g-fiche-etat"></span></div> <!-- i18n-ok -->
      <h2 class="g-fiche-titre" id="g-fiche-titre"></h2> <!-- i18n-ok -->
      <p class="g-fiche-texte" id="g-fiche-texte"></p> <!-- i18n-ok -->
      <div class="g-fiche-bas"><span class="g-fiche-chemin" id="g-fiche-chemin"></span><span class="liens" id="g-fiche-liens"></span></div> <!-- i18n-ok -->

      <ol class="g-fiche-voisins" id="g-fiche-voisins"></ol> <!-- i18n-ok -->
    </section>


    <footer class="g-pied m-pixel"><span class="g-touches"><b>click</b> region = enter · <b>Esc</b> or click outside = back · <b>/</b> search</span><span class="g-doigts"><b>tap</b> a region = enter · <b>tap outside</b> = back</span><span id="g-pied-droite"></span></footer>`;
  document.body.appendChild(shell);

  M.coins($('#g-regions')); M.coins($('#g-fiche')); M.coins($('#g-resultats')); M.coins($('#g-col-log')); M.coins($('#g-ecrit'));

  const MARQUE = window.GMTRMarque;
  function marque(tr) {
    const c = $('#g-logo'), ent = $('.g-entete');
    if (!c || !MARQUE) return;
    const cap = Math.round(parseFloat(getComputedStyle(ent).fontSize) * 1.38);
    const m = MARQUE.COTES.mot, larg = Math.ceil(cap / m.ink * (m.bandes_l + m.ecart + m.bloc));
    const dpr = devicePixelRatio || 1;
    c.width = larg * dpr; c.height = cap * dpr;
    c.style.width = larg + 'px'; c.style.height = cap + 'px';
    const ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    MARQUE.mot(ctx, { larg, haut: cap, hcap: cap, ox: 0, oy: 0, tr });
  }
  if (MARQUE) { marque(); MARQUE.pret.then(() => marque()); addEventListener('resize', () => marque(), { passive: true }); }
  const REJEU_MS = 1400;
  let rejeu = 0;
  $('#g-logo')?.addEventListener('click', () => {
    fermerFiche(); window.__planete?.accueil?.();
    if (!MARQUE) return;
    cancelAnimationFrame(rejeu);
    const t0 = performance.now(), fin = MARQUE.COURBES.ARRIVEE;
    const pas = (now) => {
      const k = Math.min(1, (now - t0) / REJEU_MS);
      marque(k < 1 ? k * fin : undefined);
      if (k < 1) rejeu = requestAnimationFrame(pas);
    };
    rejeu = requestAnimationFrame(pas);
  });

  let total = 0, lignes = {};

  const MARGE = 22;
  const etroit = matchMedia('(max-width:1000px)');
  function zoneLibre() {
    const W = innerWidth, H = innerHeight;
    const rect = (s) => { const e = $(s); if (!e) return null; const b = e.getBoundingClientRect(); return b.width > 4 ? b : null; };
    const ficEl = $('#g-fiche');
    const fic = ficEl && !ficEl.hidden ? rect('#g-fiche') : null;
    const reg = rect('#g-regions'), jou = rect('#g-journal'), ent = rect('.g-entete');
    const ecr = rect('#g-ecrit');
    const bas = (jou ? jou.top : H) - MARGE;
    let z;
    if (etroit.matches) z = { x: MARGE, r: W - MARGE, y: (reg ? reg.bottom : 120) + MARGE, b: bas };
    else {
      const hauts = [reg, jou, ecr].filter(Boolean).map((b) => b.top);
      const lieu = rect('#g-lieu');
      const haut = Math.max(ent ? ent.bottom : 0, lieu ? lieu.bottom : 0) + MARGE;
      z = { x: MARGE, r: (fic && fic.left > W / 2 ? fic.left : W) - MARGE, y: haut,
            b: (hauts.length ? Math.min(...hauts) : H) - MARGE };
    }
    return { x: z.x, y: z.y, w: Math.max(120, z.r - z.x), h: Math.max(120, z.b - z.y) };
  }
  let cadreFait = '', distAvant = null;
  let cible = null, posee = null, tPrec = 0;
  function poser() {
    const cam = window.__planete && window.__planete.camera_objet;
    if (!posee || !cam) return;
    cam.setViewOffset(posee.fw, posee.fh, posee.dx, posee.dy, posee.w, posee.h);
    cam.updateProjectionMatrix();
  }
  function viser(c) {
    cible = c;
    if (!posee) { posee = Object.assign({}, c); montrer(); }
    poser();
  }
  function glisser(t) {
    requestAnimationFrame(glisser);
    const dt = Math.min(0.1, (t - tPrec) / 1000) || 0.016; tPrec = t;
    if (!cible || !posee) return;
    posee.w = cible.w; posee.h = cible.h;
    let bouge = false;
    const k = 1 - Math.exp(-dt * 9);
    for (const n of ['fw', 'fh', 'dx', 'dy']) {
      const d = cible[n] - posee[n];
      if (Math.abs(d) < 0.02) { posee[n] = cible[n]; continue; }
      posee[n] += d * k; bouge = true;
    }
    if (bouge) poser();
  }
  requestAnimationFrame(glisser);
  const toile = $('#c');
  function montrer() { if (toile) toile.classList.add('cadree'); }
  setTimeout(montrer, 3000);
  (function premierCadre(n) {
    if (posee) return;
    const p = window.__planete;
    if (p && p.regions && p.regions.length > 4) n++;
    if (n > 1) cadrer();
    requestAnimationFrame(() => premierCadre(n));
  })(0);
  function cadrer() {
    const p = window.__planete, cam = p && p.camera_objet;
    if (!cam || !cam.setViewOffset || !p.noeuds.length || !p.vue) return;
    const z = zoneLibre();
    window.__gmtrBornes = { haut: z.y - MARGE + 6, bas: z.y + z.h + MARGE - 6, gauche: z.x, droite: z.x + z.w };
    const fin = p.arrivee ? p.arrivee() : null;
    const W = innerWidth, H = innerHeight, mode = fin ? fin.mode : p.vue.mode;
    const v = p.vue, fige = (v.view === 0 || v.view === 1) && (v.sem === 0 || v.sem === 1);
    const dist = cam.position.length();
    const stable = distAvant !== null && Math.abs(dist - distAvant) < 0.05;
    distAvant = dist;
    let objets;
    if (fin) objets = fin.objets;
    else { objets = p.noeuds.filter((m) => m.visible); if (objets.length < 10) objets = p.regions.filter((b) => b.visible); }
    const ou = (o) => (o.p ? w.copy(o.p) : o.getWorldPosition(w));
    const rayon = (o) => (o.p ? o.rad : (o.userData && o.userData.rad) || 0);
    const vue = fin ? fin.camera : cam;
    const cle = [W, H, Math.round(z.x), Math.round(z.y), Math.round(z.w), Math.round(z.h), mode, objets.length].join('|');
    if (!fige) cadreFait = '';
    else if ((posee && !stable) || cle === cadreFait) return;
    else cadreFait = cle;
    const V = p.noeuds[0].position.constructor, w = new V();
    let x0, y0, x1, y1;
    if (mode === '3d') {
      let r = 0;
      for (const o of objets) { const l = ou(o).length() + rayon(o) * 1.8; if (l > r) r = l; }
      const rp = r * 1.08 * (H / 2) / (vue.position.length() * Math.tan(cam.fov * Math.PI / 360));
      const ouverte = !!document.querySelector('#g-lieu') && document.querySelector('#g-lieu').getBoundingClientRect().width > 4;
      const nom = ouverte ? 120 : 0, etage = ouverte ? 28 : 0;
      const s3 = Math.min(3, (z.w - 2 * nom) / (2 * rp), (z.h - 2 * etage) / (2 * rp));
      const cx3 = z.x + z.w / 2, cy3 = z.y + z.h / 2;
      viser({ fw: W * s3, fh: H * s3, dx: s3 * W / 2 - cx3, dy: s3 * H / 2 - cy3, w: W, h: H });
      return;
    } else {
      vue.clearViewOffset(); vue.updateProjectionMatrix();
      x0 = y0 = Infinity; x1 = y1 = -Infinity;
      for (const o of objets) {
        const v = ou(o).project(vue);
        if (v.z > 1) continue;
        const px = (v.x * 0.5 + 0.5) * W, py = (-v.y * 0.5 + 0.5) * H;
        if (px < x0) x0 = px; if (px > x1) x1 = px; if (py < y0) y0 = py; if (py > y1) y1 = py;
      }
      if (!isFinite(x0)) { poser(); return; }
      const mx = (x1 - x0) * 0.05 + 8, my = (y1 - y0) * 0.05 + 10;
      x0 -= mx; x1 += mx; y0 -= my; y1 += my;
    }
    const s = Math.min(3, z.w / (x1 - x0), z.h / (y1 - y0));
    const bcx = (x0 + x1) / 2, bcy = (y0 + y1) / 2, cx = z.x + z.w / 2, cy = z.y + z.h / 2;
    viser({ fw: W * s, fh: H * s, dx: s * bcx - cx, dy: s * bcy - cy, w: W, h: H });
  }
  addEventListener('resize', () => { cadreFait = ''; cadrer(); });

  async function chargement() {
    journal();
    const etapes = [
      () => window.__planete && window.__planete.noeuds.length > 0,
      () => window.__planete && window.__planete.regions.length > 0,
      () => window.__planete && window.__planete.liens.length > 0,
    ];
    const limite = Date.now() + 20000;
    let complet = true;
    for (const pret of etapes) {
      while (!pret()) {
        if (Date.now() > limite) { complet = false; break; }
        await new Promise((r) => setTimeout(r, 60));
      }
      if (!complet) break;
    }
    construireListe();
    shell.classList.remove('chargement');
    setInterval(() => { cadrer(); calerSurLaLigne(); }, 350);
    await ecrireListe();
    entete();
    if (!complet) {
      if (noterJournal) noterJournal('<span class="ko">SCENE SLOW TO ANSWER</span> <span class="p">·</span> map shown without its clusters', 'boot');
      const revenir = setInterval(async () => {
        if (!etapes.every((pret) => pret())) return;
        clearInterval(revenir);
        if (noterJournal) noterJournal('<span class="ok">SCENE READY</span> <span class="p">·</span> region list rebuilt', 'boot');
        construireListe(); await ecrireListe(); entete();
      }, 500);
    }
  }

  function couleurDe(nom) {
    const d = $(`#legend .row[data-region="${CSS.escape(nom)}"] .dot`);
    return d ? getComputedStyle(d).backgroundColor : '#8a868f';
  }

  function regions() {
    const r = (window.__planete.regions || []).map((b) => ({ nom: b.userData.region, n: b.userData.n || 0 }));
    return r.sort((a, b) => b.n - a.n);
  }

  function construireListe() {
    const liste = $('#g-liste'), toutes = regions();
    total = toutes.reduce((t, r) => t + r.n, 0);
    const max = Math.max(1, ...toutes.map((x) => x.n));
    const grandes = toutes.filter((r) => r.n > 2), petites = toutes.filter((r) => r.n <= 2);
    const ligne = (r, classe = '') => {
      const li = document.createElement('li');
      li.className = 'g-ligne actionnable ' + classe; li.dataset.region = r.nom;
      li.innerHTML = `<span class="nom"></span>`
        + `<span class="part" title="${r.n} of ${total} notes"><i style="width:${Math.round(100 * r.n / max)}%;background:${couleurDe(r.nom)}"></i></span>`
        + `<span class="nb"></span>`;
      li._texte = [r.nom, nombre(r.n)];
      brancher(li, r);
      lignes[r.nom] = li;
      return li;
    };
    grandes.forEach((r) => liste.appendChild(ligne(r)));
    if (petites.length) {
      const plus = document.createElement('li');
      plus.className = 'g-ligne g-plus actionnable'; // i18n-ok
      plus.innerHTML = `<span class="nom"></span><span class="part"></span><span class="nb"></span>`;
      plus._texte = [`${petites.length} small`, nombre(petites.reduce((t, r) => t + r.n, 0))];
      plus.addEventListener('click', () => {
        const ouvert = plus.classList.toggle('ouvert');
        petites.forEach((r) => lignes[r.nom].classList.toggle('cachee', !ouvert));
      });
      liste.appendChild(plus);
      petites.forEach((r) => liste.appendChild(ligne(r, 'petite cachee')));
    }
  }
  async function ecrireListe() {
    for (const li of $('#g-liste').children) {
      if (li.classList.contains('cachee')) { li.querySelector('.nom').textContent = li._texte[0]; li.querySelector('.nb').textContent = li._texte[1]; continue; }
      M.ecrire(li.querySelector('.nb'), li._texte[1], { pas: 20, curseur: false });
      await M.ecrire(li.querySelector('.nom'), li._texte[0], { pas: 7 });
    }
  }

  const legendeDe = (nom) => $(`#legend .row[data-region="${CSS.escape(nom)}"]`);
  function brancher(li, r) {
    li.addEventListener('mouseenter', () => {
      legendeDe(r.nom)?.dispatchEvent(new MouseEvent('mouseenter'));
      M.barre(li, 1);
      $('#g-pied-droite').textContent = `${r.nom} · ${r.n} notes · ${Math.round(100 * r.n / Math.max(1, total))}% of trunk`;
    });
    li.addEventListener('mouseleave', () => {
      legendeDe(r.nom)?.dispatchEvent(new MouseEvent('mouseleave'));
      M.barre(li, 0);
      $('#g-pied-droite').textContent = '';
    });
    li.addEventListener('click', () => window.__planete.entrerRegion(r.nom));
  }

  async function entete() {
    const p = window.__planete;
    await M.ecrire($('#g-etat'), `${nombre(p.noeuds.length)} notes · ${nombre(p.liens.length)} links · ${p.regions.length} regions`, { pas: 10 });
    $('#g-etat').insertAdjacentHTML('beforeend', ' · <span id="g-vif"></span>');
  }
  $('.g-modes').addEventListener('click', (e) => { const m = e.target.closest('.g-mode'); if (m) window.__planete.setMode(m.dataset.mode); });

  let modeAffiche = null, regionAffichee = null;
  setInterval(() => {
    const p = window.__planete; if (!p || !p.vue) return;
    const mode = p.vue.mode === '3d' ? 'struct' : p.vue.mode;
    if (mode !== modeAffiche) {
      modeAffiche = mode;
      document.querySelectorAll('.g-mode').forEach((el) => M.barre(el, el.dataset.mode === modeAffiche ? 1 : 0));
    }
    if (p.region_ouverte !== regionAffichee) {
      if (regionAffichee && lignes[regionAffichee]) lignes[regionAffichee].querySelector('.nom').classList.remove('m-cadre');
      regionAffichee = p.region_ouverte;
      if (regionAffichee && lignes[regionAffichee]) lignes[regionAffichee].querySelector('.nom').classList.add('m-cadre');
      const lieu = $('#g-lieu'), li = regionAffichee && lignes[regionAffichee];
      if (lieu) { lieu.hidden = !li; if (li) lieu.textContent = li._texte.join(' · '); }
    }
    const vif = $('#g-vif'), brut = ($('#livenow')?.textContent || '').match(/(\d+) active/);
    if (vif && brut) { const n = +brut[1]; vif.innerHTML = n ? `<span class="vif">${n} active</span>` : '0 active'; }
  }, 250);

  async function journal() {
    const liste = $('#g-journal-liste'), etat = $('#g-journal-etat'), LIGNES = 200;
    const enBas = () => liste.scrollHeight - liste.scrollTop - liste.clientHeight < 24;
    const heure = (ts) => new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const hex = (n) => n.toString(16).toUpperCase().padStart(2, '0');
    const echapper = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
    const court = (s, n) => { s = String(s); return s.length > n ? '…' + s.slice(-(n - 1)) : s.padEnd(n); };
    const capaciteLog = () => {
      const liste = $('#g-journal-liste');
      if (!liste || !liste.clientWidth) return 52;
      const li = document.createElement('li');
      li.className = 'g-evt';
      li.style.visibility = 'hidden';
      li.innerHTML = `<span class="txt">${'M'.repeat(40)}</span>`;
      liste.appendChild(li);
      const chasse = li.firstElementChild.getBoundingClientRect().width / 40;
      const large = li.clientWidth;
      li.remove();
      return chasse > 1 ? Math.floor(large / chasse) : 52;
    };
    let CAPACITE = capaciteLog();
    const remesurer = () => { CAPACITE = capaciteLog(); };
    addEventListener('resize', remesurer, { passive: true });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(remesurer);
    const place = (avant, apres) => Math.max(18, CAPACITE - avant - apres); // i18n-ok
    const ajouter = (html, classe = '') => {
      const colle = enBas();
      const li = document.createElement('li');
      li.className = 'g-evt ' + classe; li.innerHTML = `<span class="txt">${html}</span>`;
      liste.appendChild(li);
      while (liste.children.length > LIGNES) liste.firstElementChild.remove();
      if (colle) liste.scrollTop = liste.scrollHeight;
      return li;
    };
    noterJournal = ajouter;
    const amorce = await fetch('/amorce.json', { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
    if (document.fonts && document.fonts.ready) await document.fonts.ready.catch(() => {});
    remesurer();
    if (amorce) {
      ajouter(`<span class="b">GMTR POWER-ON SELF-TEST</span> <span class="p">//</span> <span class="ref">trunk ${echapper(amorce.commit || 'unknown')}</span>`, 'tete');
      for (const [k, l] of amorce.lignes.entries()) {
        const mot = l.present ? 'OK' : (l.chemin === 'state/FREEZE' ? 'NONE' : 'ABSENT');
        const classe = l.present ? 'ok' : (l.chemin === 'state/FREEZE' ? 't' : 'ko');
        const tete = `${hex(k)} | ${l.t.toFixed(3)} |`;
        ajouter(`<span class="t">${tete}</span> <span class="b">READ  </span> `
          + `<span class="ref">${echapper(court(l.chemin, place(tete.length + 8, mot.length + 3)))}</span> `
          + `<span class="p">·</span> <span class="${classe}">${mot}</span>`, 'boot');
        await M.attendre(60);
      }
      ajouter(`<span class="t">${hex(amorce.lignes.length)} |</span> <span class="b">SELF-TEST COMPLETE</span> in <span class="n">${amorce.duree_ms.toFixed(2)}</span> ms `
        + `<span class="p">·</span> <span class="ok">${amorce.lignes.filter((l) => l.present).length}/${amorce.lignes.length} FOUND</span>`, 'boot');
    }
    let dernier = 0;
    async function sonder() {
      try {
        const d = await fetch('/flux.json', { cache: 'no-store' }).then((r) => r.json());
        const nouveaux = d.evenements.filter((e) => e.ts > dernier).sort((a, b) => a.ts - b.ts);
        if (!dernier) { etat.innerHTML = '<span class="vif">live</span>'; $('#g-journal-titre').textContent = 'system log · self-test + live'; }
        for (const e of (dernier ? nouveaux : nouveaux.slice(-4))) {
          const tete = `${heure(e.ts)} |`, verbe = String(e.type).toUpperCase().padEnd(6), sess = e.session || '';
          const cible = (e.cible || '').replace(/\.md$/, '');
          const li = ajouter(`<span class="t">${tete}</span> <span class="b">${verbe}</span> `
            + `<span class="ref">${echapper(court(cible, place(tete.length + verbe.length + 2, sess.length + 3)))}</span> `
            + `<span class="p">·</span> <span class="t">${echapper(sess)}</span>`, 'vivant');
          if (dernier) { M.barre(li, 1); setTimeout(() => M.barre(li, 0), 900); }
        }
        dernier = Math.max(dernier, ...d.evenements.map((e) => e.ts));
      } catch { etat.innerHTML = '<span class="ko">offline</span>'; }
    }
    await sonder();
    setInterval(sonder, 4000);
    agentActif();
  }

  async function agentActif() {
    const bloc = $('#g-agent'), quoi = $('#g-agent-quoi'), puce = $('.puce', bloc), age = $('#g-agent-age');
    let dernierTexte = null;
    const depuis = (ts) => {
      const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
      return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
    };
    async function sonder() {
      let e = null;
      try { e = await fetch('/etat.json', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null); } catch {}
      const s = e && e.session;
      if (!s || !s.ts) { bloc.className = 'g-agent'; puce.textContent = '×'; age.textContent = ''; quoi.textContent = 'state/status.json unreadable'; return; }
      const tourne = s.etat === 'busy';
      const nom = (s.detail && s.qui === 'agent') ? s.detail : (s.qui === 'you' ? 'this session' : (s.detail || '')); // i18n-ok
      const texte = tourne ? `${(s.activite || 'busy')}${nom ? ' · ' + nom : ''}` : 'idle · nothing running';
      bloc.className = 'g-agent' + (tourne ? ' tourne' : '');
      puce.textContent = tourne ? '●' : '○';
      age.textContent = tourne ? depuis(s.ts) : `last ${depuis(s.ts)}`; // i18n-ok
      if (texte !== dernierTexte) { dernierTexte = texte; M.ecrire(quoi, texte, { pas: 5, decode: false }); }
    }
    await sonder();
    setInterval(sonder, 2000);
    ceQuiSecrit();
  }

  async function ceQuiSecrit() {
    const tete = $('#g-ecrit-tete'), etat = $('#g-ecrit-etat'), corps = $('#g-ecrit-corps');
    const GARDE = 800, file = [], RETARD_MAX = 40;
    let depuis = 0, enAttente = false, premier = true, suivre = true;
    const heure = (ts) => new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const enBas = () => corps.scrollHeight - corps.scrollTop - corps.clientHeight < 30;
    corps.addEventListener('wheel', () => requestAnimationFrame(() => { suivre = enBas(); }), { passive: true });
    corps.addEventListener('scroll', () => { if (enBas()) suivre = true; }, { passive: true });
    const poser = (l) => {
      const div = document.createElement('div');
      div.className = 'g-l ' + l.c; div.textContent = l.t;
      corps.appendChild(div);
      return div;
    };
    const couper = () => { while (corps.children.length > GARDE) corps.firstElementChild.remove(); };
    const suivreBas = () => { if (suivre) corps.scrollTop = corps.scrollHeight; };
    const classe = (l) => l.startsWith('@@') ? 'hunk' : l.startsWith('+') ? 'plus' : l.startsWith('-') ? 'moins' : '';
    const degager = (l) => l.replace(/^([+-]?)(\s+)/, (_, s, e) => s + ' '.repeat(Math.min(e.length, 4)));

    async function sonder() {
      let d = null;
      try { d = await fetch('/ecrit.json?depuis=' + depuis, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null); } catch {} // i18n-ok
      if (!d) { etat.innerHTML = '<span class="t">offline</span>'; return; }
      const arrivees = [];
      for (const e of d.evenements) {
        depuis = Math.max(depuis, e.ts); // i18n-ok
        const bilan = (e.ajoutees != null ? ` +${e.ajoutees}` : '') + (e.retirees != null ? ` −${e.retirees}` : '');
        arrivees.push({ c: 'bloc', t: `${heure(e.ts)} · ${e.qui} · ${e.outil} · ${e.chemin}${bilan}`, chemin: e.chemin, qui: e.qui }); // i18n-ok
        for (const l of e.diff) arrivees.push({ c: classe(l), t: degager(l.replace(/\t/g, '  ')) });
        if (e.coupees) arrivees.push({ c: 'hunk', t: `… ${e.coupees} lignes de plus, non transmises` });
      }
      if (premier) {
        premier = false;
        arrivees.forEach(poser); couper(); suivreBas();
        const b = arrivees.filter((x) => x.c === 'bloc').pop();
        if (b) tete.textContent = b.chemin;
        return;
      }
      file.push(...arrivees);
      if (file.length > RETARD_MAX) { file.splice(0, file.length - RETARD_MAX).forEach(poser); couper(); suivreBas(); }
    }

    async function ecrireEnContinu() {
      for (;;) {
        if (!file.length) {
          if (!enAttente) { enAttente = true; etat.innerHTML = '<span class="t">waiting for next write</span><span class="m-curseur g-attente"></span>'; }
          await M.attendre(150);
          continue;
        }
        if (enAttente) { enAttente = false; }
        const l = file.shift();
        const div = poser({ c: l.c, t: '' });
        if (l.c === 'bloc') {
          tete.textContent = l.chemin;
          etat.innerHTML = `<span class="vif">writing</span> <span class="t">· ${l.qui}</span>`;
        }
        suivreBas();
        const retard = file.length;
        const pas = retard > 20 ? 1 : 4;
        if (l.t.length > 180) div.textContent = l.t;
        else await M.ecrire(div, l.t, { pas, decode: false, curseur: true });
        couper(); suivreBas();
        await M.attendre(retard > 20 ? 8 : 45);
      }
    }

    await sonder();
    setInterval(sonder, 1500);
    ecrireEnContinu();
  }

  const tip = document.getElementById('tip'), fiche = $('#g-fiche'); // i18n-ok
  let jeton = { annule: false }, ficheId = null, regionContexte = null, modeFiche = null;

  const BLOC = /^(DIV|SECTION|P|HEADER|FOOTER|LI|UL|OL|DETAILS|SUMMARY|BR|H1|H2|H3|H4|H5|H6|TABLE|TR|TD|PRE|BLOCKQUOTE)$/;
  function texteCache(el) {
    if (!el) return '';
    const bouts = [];
    (function lire(n) {
      for (const e of n.childNodes) {
        if (e.nodeType === 3) bouts.push(e.nodeValue);
        else if (e.nodeType === 1) {
          const b = BLOC.test(e.tagName);
          if (b) bouts.push(' ');
          lire(e);
          if (b) bouts.push(' ');
        }
      }
    })(el);
    return bouts.join('').replace(/\s+/g, ' ').trim();
  }

  function contenuTip() {
    if (!tip.classList.contains('show')) return null;
    const titre = ($('.n', tip)?.textContent || '').trim();
    if (!titre) return null;
    if (document.documentElement.dataset.ficheBrute === '1') {
      const d0 = ($('.d', tip)?.innerText || '').replace(/\s+/g, ' ').trim();
      return { titre, chemin: ($('.f', tip)?.textContent || '').trim(),
        region: ($('.lbl', tip)?.textContent || '').replace(/⟡.*$/, '').trim(),
        clair: d0, entier: d0,
        liens: ($('.lnk .hd', tip)?.textContent || '').match(/\((\d+)\)/) };
    }
    const clair = texteCache($('.bl.clair .txt', tip));
    const entier = texteCache($('.bl.modele .txt', tip));
    const secours = (clair || entier) ? '' : texteCache($('.d', tip));
    return {
      titre,
      chemin: ($('.f', tip)?.textContent || '').trim(),
      region: ($('.lbl', tip)?.textContent || '').replace(/⟡.*$/, '').trim(),
      clair: clair || entier || secours,
      entier: entier || clair || secours,
      liens: ($('.lnk .hd', tip)?.textContent || '').match(/\((\d+)\)/),
    };
  }

  function fermerFiche() {
    if (ficheId === null) return;
    ficheId = null; modeFiche = null; jeton.annule = true;
    M.barre($('#g-fiche-tete'), 0);
    if (regionContexte && lignes[regionContexte]) M.barre(lignes[regionContexte], 0);
    regionContexte = null;
    fiche.classList.remove('grand');
    if (parRecherche) { parRecherche = false; window.__planete.lacher(); }
    setTimeout(() => { if (ficheId === null) fiche.hidden = true; }, 420);
  }

  const ECART_LISTE = 12;
  function calerLaListe() {
    const reg = $('#g-regions');
    if (!reg) return;
    reg.classList.remove('serree');
    reg.style.removeProperty('--m-liste-max');
    if (fiche.hidden) return;
    const rr = reg.getBoundingClientRect(), rf = fiche.getBoundingClientRect();
    if (rf.width < 4 || rf.height < 4) return;
    if (rf.left >= rr.right - 1 || rf.right <= rr.left + 1) return;
    if (rf.top >= rr.bottom - 0.5) return;
    const liste = reg.querySelector('#g-liste'), rang = reg.querySelector('.g-ligne');
    const hr = rang ? rang.getBoundingClientRect().height : 0;
    if (!hr || !liste) return;
    const padBas = parseFloat(getComputedStyle(reg).paddingBottom) || 0;
    const haut = liste.getBoundingClientRect().top;
    const n = Math.floor((rf.top - ECART_LISTE - padBas - haut) / hr);
    reg.style.setProperty('--m-liste-max', (Math.max(1, n) * hr) + 'px');
    reg.classList.add('serree');
  }

  function arrondirLaListe() {
    const reg = $('#g-regions'), li = reg && reg.querySelector('#g-liste');
    if (!li) return;
    li.style.removeProperty('height');
    const rang = reg.querySelector('.g-ligne');
    const hr = rang ? rang.getBoundingClientRect().height : 0;
    if (!hr) return;
    const dispo = li.clientHeight;
    if (li.scrollHeight <= dispo + 0.5) return;
    const n = Math.max(1, Math.floor(dispo / hr));
    if (Math.abs(dispo - n * hr) > 0.5) li.style.height = (n * hr) + 'px';
  }

  function calerSurLaLigne() {
    calerLaListe();
    arrondirLaListe();
    const t = $('#g-fiche-texte');
    if (!t || fiche.hidden) return;
    const lu = t.scrollTop;
    t.style.maxHeight = '';
    const lh = parseFloat(getComputedStyle(t).lineHeight);
    if (!lh) { t.scrollTop = lu; return; }
    const haut = t.getBoundingClientRect().top;
    let bas = Infinity, apres = 0;
    for (let n = t; n.parentElement; n = n.parentElement) {
      for (let s = n.nextElementSibling; s; s = s.nextElementSibling) {
        const ss = getComputedStyle(s);
        if (ss.display === 'none' || ss.position === 'absolute' || ss.position === 'fixed') continue;
        apres += s.getBoundingClientRect().height + parseFloat(ss.marginTop) + parseFloat(ss.marginBottom);
      }
      const a = n.parentElement, sa = getComputedStyle(a);
      if (sa.overflow === 'visible' && sa.overflowY === 'visible') continue;
      bas = Math.min(bas, a.getBoundingClientRect().bottom - parseFloat(sa.paddingBottom) - apres);
    }
    if (bas === Infinity) { t.scrollTop = lu; return; }
    const dispo = bas - haut;
    if (dispo <= 0) { t.scrollTop = lu; return; }
    t.style.maxHeight = Math.max(lh, Math.floor(dispo / lh + 0.02) * lh) + 'px';
    t.style.overflow = fiche.classList.contains('grand') ? 'auto' : 'hidden';
    if (t.scrollTop !== lu) t.scrollTop = lu; // i18n-ok
    t.classList.toggle('tronque', t.scrollHeight - t.clientHeight - t.scrollTop > 1);
  }
  addEventListener('resize', calerSurLaLigne);
  $('#g-fiche-texte')?.addEventListener('scroll', () => {
    const t = $('#g-fiche-texte');
    t.classList.toggle('tronque', t.scrollHeight - t.clientHeight - t.scrollTop > 1);
  }, { passive: true });

  function afficherFiche(c, mode) {
    const cle = c.chemin + '|' + c.titre + '|' + mode;
    if (cle === ficheId) return;
    ficheId = cle; modeFiche = mode; jeton.annule = true; jeton = { annule: false };
    const brut = mode === 'grand' ? c.entier : c.clair;
    const texte = mode === 'grand' || brut.length <= 260
                ? brut : brut.slice(0, 259).replace(/\s+\S*$/, '') + '…';
    const pasTexte = mode === 'grand' ? Math.max(0.35, Math.min(2, 1500 / Math.max(1, texte.length))) : 2;
    fiche.hidden = false;
    fiche.classList.toggle('grand', mode === 'grand');
    $('#g-fiche-region').textContent = c.region;
    $('#g-fiche-etat').textContent = mode === 'grand' ? 'expanded' : 'preview';
    M.barre($('#g-fiche-tete'), 1, { sombre: true });
    $('#g-fiche-chemin').textContent = c.chemin;
    $('#g-fiche-liens').textContent = c.liens ? `${c.liens[1]} links` : ''; // i18n-ok: inherited selector
    ecrireVoisins(c);
    $('#g-fiche-texte').textContent = '';
    if (regionContexte && lignes[regionContexte]) M.barre(lignes[regionContexte], 0);
    regionContexte = lignes[c.region] ? c.region : null;
    if (regionContexte) M.barre(lignes[regionContexte], 1, { sombre: true });
    const j = jeton;
    let frappe = true;
    M.ecrire($('#g-fiche-titre'), c.titre, { pas: 9, jeton: j }) // i18n-ok
      .then(() => !j.annule && M.ecrire($('#g-fiche-texte'), texte, { pas: pasTexte, decode: false, curseur: true, jeton: j })) // i18n-ok
      .then(() => { frappe = false; if (!j.annule) calerSurLaLigne(); })
      .catch(() => { frappe = false; });
    (function caleEnFrappant() {
      calerSurLaLigne();
      if (frappe && !j.annule) requestAnimationFrame(caleEnFrappant);
    })();
  }

  addEventListener('click', (e) => {
    if (e.target.closest('#gmtr-shell')) return;
    if (parRecherche) { parRecherche = false; window.__planete.lacher(); }
    const c = contenuTip();
    if (!c) { fermerFiche(); return; }
    const dejaGrande = modeFiche === 'grand' && ficheId === c.chemin + '|' + c.titre + '|grand';
    if (!dejaGrande) afficherFiche(c, 'apercu');
  }, true);

  addEventListener('dblclick', () => {
    setTimeout(() => { const c = contenuTip(); if (c) afficherFiche(c, 'grand'); }, 140);
  });
  addEventListener('keydown', (e) => { if (e.key === 'Escape') fermerFiche(); });

  new MutationObserver(() => {
    if (modeFiche !== 'grand') return;
    const c = contenuTip();
    if (c && c.entier.length > ($('#g-fiche-texte').textContent || '').length) { ficheId = null; afficherFiche(c, 'grand'); }
  }).observe(tip, { childList: true, subtree: true, characterData: true });

  let parRecherche = false;
  const P = () => window.__planete;
  const titreDe = (d) => d.title || (d.name || '').replace(/-/g, ' ').replace(/^\w/, (x) => x.toUpperCase());
  function allerA(m) {
    P().epingler(m); parRecherche = true;
    const c = contenuTip();
    if (c) { ficheId = null; afficherFiche(c, 'apercu'); }
  }
  const noeudDe = (chemin) => (P()?.noeuds || []).find((o) => o.userData.data.file === chemin);
  function ecrireVoisins(c) {
    const ol = $('#g-fiche-voisins');
    ol.textContent = '';
    const m = noeudDe(c.chemin);
    if (!m) return;
    const rn = P().regionDe(m.userData.data);
    const autres = (m.userData.links || []).map((L) => (L.a === m ? L.b : L.a));
    autres.forEach((o) => {
      const d = o.userData.data, li = document.createElement('li');
      li.className = 'actionnable';
      li.textContent = titreDe(d);
      const r = P().regionDe(d);
      if (r !== rn) { const em = document.createElement('em'); em.textContent = ' · ' + r; li.appendChild(em); }
      li.addEventListener('click', () => allerA(o));
      ol.appendChild(li);
    });
  }

  const calqueNoms = document.createElement('div');
  calqueNoms.className = 'g-noms'; calqueNoms.setAttribute('aria-hidden', 'true'); calqueNoms.hidden = true;
  shell.prepend(calqueNoms);
  const NOM_MAX = 34, nomDe = new Map();
  const ECHELLE_MIN = 0.4;
  const DENSITE = 0.3, AIRE_NOM = 150 * 16;
  let rangDe = new Map(), glisse = false;
  addEventListener('pointerdown', () => { glisse = true; }, { passive: true });
  addEventListener('pointerup', () => { glisse = false; }, { passive: true });
  addEventListener('pointercancel', () => { glisse = false; }, { passive: true });
  const nomCourt = (t) => (t.length > NOM_MAX ? t.slice(0, NOM_MAX - 1).trimEnd() + '…' : t);
  let regionNommee = null;
  const lisse = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  function spanDe(m) {
    let o = nomDe.get(m);
    if (!o) {
      const el = document.createElement('span'); calqueNoms.appendChild(el);
      el.dataset.fiche = m.userData.data.id;
      o = { el, texte: '', vu: false }; nomDe.set(m, o);
    }
    return o;
  }
  function nommerPoints(t) {
    requestAnimationFrame(nommerPoints);
    const p = P(), region = p?.region_ouverte, cam = p?.camera_objet;
    if (!region || !cam || document.body.classList.contains('g-cherche-ouverte')) {
      calqueNoms.hidden = true;
      if (regionNommee) { for (const o of nomDe.values()) { o.vu = false; o.el.classList.remove('vu'); } regionNommee = null; }
      return;
    }
    calqueNoms.hidden = false;
    if (region !== regionNommee) {
      for (const o of nomDe.values()) { o.vu = false; o.el.classList.remove('vu'); }
      regionNommee = region;
      rangDe = new Map();
    }
    const W = innerWidth, H = innerHeight, pin = p.epingle, vise = p.survol;
    const pts = [];
    let cx = 0, cy = 0, cz = 0;
    for (const m of p.noeuds) {
      if (!m.visible || p.regionDe(m.userData.data) !== region) continue;
      const w = m.getWorldPosition(m.position.clone());
      pts.push({ m, w }); cx += w.x; cy += w.y; cz += w.z;
    }
    if (!pts.length) return;
    cx /= pts.length; cy /= pts.length; cz /= pts.length;
    const dist = pts.map((q) => Math.hypot(q.w.x - cx, q.w.y - cy, q.w.z - cz)).sort((a, b) => a - b);
    const rayon = dist[Math.floor(dist.length * 0.9)] || 0;
    const cp = cam.position, dCentre = Math.hypot(cp.x - cx, cp.y - cy, cp.z - cz);
    if (rangDe.size !== pts.length) {
      const ordre = pts.map((q) => q.m).sort((a, b) => (b.userData.links?.length || 0) - (a.userData.links?.length || 0)
        || String(a.userData.data.id).localeCompare(String(b.userData.data.id)));
      rangDe = new Map(ordre.map((m, i) => [m, i]));
    }
    const rayonPx = cam.isPerspectiveCamera
      ? rayon / (dCentre * Math.tan(cam.fov * Math.PI / 360)) * H / 2
      : rayon * cam.zoom * H / (cam.top - cam.bottom);
    const budget = DENSITE * Math.PI * rayonPx * rayonPx / AIRE_NOM;
    const dt = Math.min(0.1, Math.max(0, (t - (nommerPoints.t || t)) / 1000)); nommerPoints.t = t;
    const k = 1 - Math.exp(-dt / 0.12);
    const vus = new Set();
    for (const q of pts) {
      const d = Math.hypot(cp.x - q.w.x, cp.y - q.w.y, cp.z - q.w.z);
      const fond = rayon > 1e-6 ? (d - (dCentre - rayon)) / (2 * rayon) : 0;
      const echelle = 1 - lisse(0.45, 0.95, fond);
      const v = q.w.project(cam);
      if (v.z < -1 || v.z > 1) continue;
      const force = q.m === pin || (q.m === vise && !glisse);
      const vise_a = force ? 1 : 0;
      const vise_e = force ? Math.max(echelle, 1) : echelle;
      const o = spanDe(q.m);
      if (o.a === undefined) { o.a = 0; o.e = vise_e; }
      o.a += (vise_a - o.a) * k; o.e += (vise_e - o.e) * k;
      if (vise_a === 0 && o.a < 0.01) { o.a = 0; continue; }
      vus.add(o);
      const texte = nomCourt(titreDe(q.m.userData.data));
      if (o.texte !== texte) { o.el.textContent = texte; o.texte = texte; }
      const x = (v.x + 1) / 2 * W, y = (1 - v.y) / 2 * H;
      o.el.style.transform = `translate(${x}px, ${y - 7 * o.e}px) translate(-50%, -100%) scale(${o.e})`;
      o.el.style.opacity = o.a.toFixed(3);
      o.el.style.zIndex = force ? 1000 : Math.round(echelle * 100);
      o.el.classList.toggle('epingle', q.m === pin);
    }
    for (const o of nomDe.values()) { o.cible = vus.has(o); if (!o.cible) o.a = 0; }
    for (const o of nomDe.values()) if (o.vu !== o.cible) { o.vu = !!o.cible; o.el.classList.toggle('vu', o.vu); }
  }
  requestAnimationFrame(nommerPoints);

  const calqueCadres = document.createElement('div');
  calqueCadres.className = 'g-cadres'; calqueCadres.setAttribute('aria-hidden', 'true');
  shell.prepend(calqueCadres);
  const nomCadre = new Map();
  const SVGNS = 'http://www.w3.org/2000/svg';
  const filsCadres = document.createElementNS(SVGNS, 'svg');
  filsCadres.setAttribute('class', 'g-cadres-fils'); calqueCadres.appendChild(filsCadres);
  const ECART = 20, PAS = 18;
  function nommerCadres() {
    requestAnimationFrame(nommerCadres);
    const p = P(), cam = p?.camera_objet, liste = p?.cadres || [];
    for (const [c, o] of nomCadre) if (!liste.includes(c)) { o.el.remove(); o.fil.remove(); o.pt.remove(); nomCadre.delete(c); }
    const V = cam && new cam.position.constructor(), vus = [];
    const ecran = (w) => { V.copy(w).project(cam); return [(V.x + 1) / 2 * innerWidth, (1 - V.y) / 2 * innerHeight]; };
    let sx = 0, sy = 0, rs = 0;
    for (const c of liste) {
      let o = nomCadre.get(c);
      if (!o) { const el = document.createElement('span'); el.dataset.role = c.role;
        el.textContent = `${c.nom} · ${c.n}`; calqueCadres.appendChild(el);
        const fil = document.createElementNS(SVGNS, 'polyline'), pt = document.createElementNS(SVGNS, 'circle');
        pt.setAttribute('r', '1.5'); filsCadres.append(fil, pt);
        o = { el, fil, pt }; nomCadre.set(c, o); }
      const f = Math.min(1, Math.max(0, ((c.face ?? 1) - 0.45) / 0.30)), a = c.ligne.material.opacity / 0.38 * f * f * (3 - 2 * f);
      o.a = a;
      if (!cam || a < 0.02) { o.el.style.opacity = 0; o.fil.style.opacity = o.pt.style.opacity = 0; continue; }
      if (!rs) { const g = c.ligne.parent, w = g.getWorldPosition(new cam.position.constructor());
        [sx, sy] = ecran(w);
        const r = c.ligne.localToWorld(V.fromBufferAttribute(c.ligne.geometry.attributes.position, 0)).distanceTo(w);
        const haut = new cam.position.constructor().setFromMatrixColumn(cam.matrixWorld, 1).multiplyScalar(r).add(w);
        const [hx, hy] = ecran(haut); rs = Math.hypot(hx - sx, hy - sy); }
      const pos = c.ligne.geometry.attributes.position;
      let cx = 0, cy = 0, ax = 0, ay = 0, best = -Infinity;
      const pts = [];
      for (let i = 0; i < pos.count; i++) {
        const [x, y] = ecran(c.ligne.localToWorld(V.fromBufferAttribute(pos, i))); pts.push(x, y); cx += x; cy += y; }
      cx /= pos.count; cy /= pos.count;
      let dx = cx - sx, dy = cy - sy, d = Math.hypot(dx, dy);
      if (d < 1) { dx = 0; dy = -1; d = 1; }
      dx /= d; dy /= d;
      for (let i = 0; i < pts.length; i += 2) { const k = (pts[i] - sx) * dx + (pts[i + 1] - sy) * dy;
        if (k > best) { best = k; ax = pts[i]; ay = pts[i + 1]; } }
      vus.push({ o, a, ax, ay, dx, dy, droite: dx >= 0, y: sy + dy * (rs + ECART) });
    }
    for (const droite of [true, false]) {
      const cote = vus.filter((v) => v.droite === droite).sort((u, v) => u.y - v.y);
      for (let i = 1; i < cote.length; i++) cote[i].y = Math.max(cote[i].y, cote[i - 1].y + PAS);
      const bas = cote.length ? cote[cote.length - 1].y - (innerHeight - 24) : 0;
      if (bas > 0) for (let i = cote.length - 1; i >= 0; i--) {
        cote[i].y = Math.min(cote[i].y - (i === cote.length - 1 ? bas : 0), i < cote.length - 1 ? cote[i + 1].y - PAS : Infinity); }
      for (const v of cote) {
        const h = Math.max(-rs - ECART, Math.min(rs + ECART, v.y - sy));
        const lx = sx + (droite ? 1 : -1) * (Math.sqrt(Math.max(0, (rs + ECART) ** 2 - h * h)) || 0);
        const bx = lx;
        const bo = window.__gmtrBornes, place = bo && bo.droite ? (droite ? bo.droite - bx : bx - bo.gauche) - 6 : 0;
        v.o.el.style.maxWidth = place > 40 ? place + 'px' : '';
        v.o.el.style.transform = `translate(${bx}px, ${v.y}px) translate(${droite ? '6px' : 'calc(-100% - 6px)'}, -50%)`;
        v.o.el.style.opacity = v.a.toFixed(3);
        v.o.fil.setAttribute('points', `${v.ax},${v.ay} ${bx},${v.y}`);
        v.o.pt.setAttribute('cx', v.ax); v.o.pt.setAttribute('cy', v.ay);
        v.o.fil.style.opacity = v.o.pt.style.opacity = (v.a * 0.8).toFixed(3);
      }
    }
  }
  requestAnimationFrame(nommerCadres);

  const plat = (t) => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  let index = null;
  let corps = {};
  function chargerCorps() {
    P()?.textes?.().then((j) => {
      if (!j || corps === j) return;
      corps = j; index = null;
      if (champ.value.trim()) montrerResultats();
    });
  }
  function indexer() {
    index = (P()?.noeuds || []).map((m) => {
      const d = m.userData.data, titre = titreDe(d);
      return { m, titre, t: plat(titre), f: plat(d.file + ' ' + d.name),
               x: plat((d.desc || '') + ' ' + (d.en_clair || '')), c: plat(corps[d.id] || d.long || ''),
               region: P().regionDe(d), sujet: d.topic || null };
    });
  }
  function chercher(q) {
    const mots = plat(q).split(/\s+/).filter((w) => w.length > 1);
    if (!mots.length) return [];
    if (!index || index.length !== (P()?.noeuds || []).length) indexer();
    const res = [];
    for (const e of index) {
      let score = 0, palier = 3, ok = true;
      for (const w of mots) {
        if (e.t.includes(w)) score += e.t.startsWith(w) ? 12 : 8;
        else if (e.f.includes(w)) { score += 4; palier = Math.min(palier, 2); }
        else if (e.x.includes(w)) { score += 1; palier = Math.min(palier, 1); }
        else if (e.c.includes(w)) { score += 0.5; palier = 0; }
        else { ok = false; break; }
      }
      if (ok) res.push([palier, score, e]);
    }
    return res.sort((a, b) => b[0] - a[0] || b[1] - a[1] || a[2].titre.localeCompare(b[2].titre)).map((r) => r[2]);
  }
  const champ = $('#g-cherche-champ'), panneauRes = $('#g-resultats'), listeRes = $('#g-resultats-liste');
  let trouves = [], choisi = 0;
  function montrerResultats() {
    const q = champ.value.trim();
    trouves = q ? chercher(q) : [];
    choisi = 0; sujetOuvert = null;
    $('#g-resultats-titre').textContent = 'results';
    listeRes.classList.add('defile');
    listeRes.textContent = '';
    panneauRes.hidden = !q;
    panneauRes.classList.toggle('accroche', !!q);
    document.body.classList.toggle('g-cherche-ouverte', !!q);
    if (!q) return;
    $('#g-resultats-n').textContent = trouves.length ? nombre(trouves.length) + ' found' : 'none';
    trouves.forEach((e, i) => {
      const li = document.createElement('li');
      li.className = 'actionnable' + (i === choisi ? ' choisi' : '');
      li.setAttribute('role', 'option');
      const t = document.createElement('span'); t.className = 'titre'; t.textContent = e.titre;
      const r = document.createElement('span'); r.className = 'region'; r.textContent = e.region;
      li.append(t, r);
      li.addEventListener('mousedown', (ev) => ev.preventDefault());
      li.addEventListener('click', () => valider(i));
      listeRes.appendChild(li);
    });
    accrocher();
  }
  function valider(i) {
    const e = trouves[i]; if (!e) return;
    champ.value = ''; montrerResultats(); champ.blur();
    allerA(e.m);
  }
  function surligner(i) {
    const n = trouves.length; if (!n) return;
    choisi = (i + n) % n;
    listeRes.querySelectorAll('li').forEach((li, k) => li.classList.toggle('choisi', k === choisi));
    listeRes.children[choisi]?.scrollIntoView({ block: 'nearest' });
  }
  function accrocher() {
    const r = $('#g-cherche').getBoundingClientRect();
    const st = getComputedStyle(panneauRes), pad = parseFloat(st.paddingLeft) || 0;
    const marge = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--g-marge')) || 20;
    const large = Math.min(Math.max(r.width + 2 * pad, 420), innerWidth - 2 * marge);
    const gauche = Math.max(marge, Math.min(r.left - pad, innerWidth - marge - large));
    Object.assign(panneauRes.style, { left: gauche + 'px', top: r.bottom + 'px', width: large + 'px', right: 'auto' });
    let plancher = innerHeight - marge;
    for (const el of document.querySelectorAll('.g-regions, .g-journal, .g-ecrit')) {
      const b = el.getBoundingClientRect();
      if (getComputedStyle(el).visibility !== 'hidden' && b.height && b.top > r.bottom + 100) plancher = Math.min(plancher, b.top - 12);
    }
    const habillage = panneauRes.offsetHeight - listeRes.offsetHeight;
    const ligne = listeRes.firstElementChild?.offsetHeight || 26;
    const place = Math.max(120, Math.min(innerHeight * .6, plancher - r.bottom - habillage));
    listeRes.style.maxHeight = Math.floor(place / ligne) * ligne + 'px';
  }
  addEventListener('resize', () => { if (panneauRes.classList.contains('accroche')) accrocher(); }, { passive: true });
  let sujetOuvert = null;
  const listeSujets = $('#g-liste-sujets');
  function construireSujets() {
    if (!index || index.length !== (P()?.noeuds || []).length) indexer();
    const compte = {};
    for (const e of index) compte[e.sujet || ''] = (compte[e.sujet || ''] || 0) + 1;
    const rangs = Object.entries(compte).filter(([k]) => k).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...rangs.map((r) => r[1]));
    listeSujets.textContent = '';
    const ligne = (id, n, libelle) => {
      const li = document.createElement('li');
      li.className = 'g-ligne actionnable' + (id ? '' : ' g-sans-sujet'); li.dataset.sujet = id;
      li.innerHTML = `<span class="nom"></span><span class="part" title="${n} of ${index.length} notes"><i style="width:${Math.round(100 * n / max)}%"></i></span><span class="nb"></span>`;
      li.querySelector('.nom').textContent = libelle; li.querySelector('.nb').textContent = nombre(n);
      if (id) li.title = id;
      li.addEventListener('mouseenter', () => M.barre(li, 1));
      li.addEventListener('mouseleave', () => M.barre(li, 0));
      li.addEventListener('click', () => montrerSujet(id));
      listeSujets.appendChild(li);
    };
    const court = (id) => id.split(/-(?:and|with)-/)[0];
    rangs.forEach(([id, n]) => ligne(id, n, court(id)));
    if (compte['']) ligne('', compte[''], 'no topic');
  }
  function montrerSujet(id) {
    if (sujetOuvert === id && !panneauRes.hidden) { fermerSujet(); return; }
    champ.value = '';
    sujetOuvert = id;
    P()?.viserSujet?.(id);
    trouves = index.filter((e) => (e.sujet || '') === id).sort((a, b) => a.titre.localeCompare(b.titre));
    choisi = -1;
    $('#g-resultats-titre').textContent = id || 'no topic';
    $('#g-resultats-n').textContent = nombre(trouves.length) + ' notes';
    listeRes.textContent = '';
    listeRes.classList.add('defile');
    panneauRes.classList.remove('accroche'); panneauRes.removeAttribute('style'); listeRes.style.maxHeight = '';
    trouves.forEach((e, i) => {
      const li = document.createElement('li');
      li.className = 'actionnable'; li.setAttribute('role', 'option');
      const t = document.createElement('span'); t.className = 'titre'; t.textContent = e.titre;
      const r = document.createElement('span'); r.className = 'region'; r.textContent = e.region;
      li.append(t, r);
      li.addEventListener('click', () => { fermerSujet(); allerA(e.m); });
      listeRes.appendChild(li);
    });
    listeRes.scrollTop = 0;
    panneauRes.hidden = false;
    document.body.classList.add('g-cherche-ouverte');
    listeSujets.querySelectorAll('li').forEach((li) => li.querySelector('.nom').classList.toggle('m-cadre', li.dataset.sujet === id));
  }
  function fermerSujet() {
    sujetOuvert = null;
    P()?.viserSujet?.(null);
    listeSujets.querySelectorAll('.m-cadre').forEach((el) => el.classList.remove('m-cadre'));
    montrerResultats();
  }
  function choisirAxe(axe) {
    const sujets = axe === 'topic';
    if (sujets) construireSujets(); else if (sujetOuvert !== null) fermerSujet();
    $('#g-liste').hidden = sujets; listeSujets.hidden = !sujets;
    document.querySelectorAll('.g-axe').forEach((el) => el.classList.toggle('on', el.dataset.axe === axe));
  }
  document.querySelectorAll('.g-axe').forEach((el) => el.addEventListener('click', () => choisirAxe(el.dataset.axe)));
  choisirAxe('region');
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && sujetOuvert !== null) fermerSujet(); });

  champ.addEventListener('focus', chargerCorps);
  champ.addEventListener('input', montrerResultats);
  champ.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'ArrowDown') { e.preventDefault(); surligner(choisi + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); surligner(choisi - 1); }
    else if (e.key === 'Enter') { e.preventDefault(); valider(choisi); }
    else if (e.key === 'Escape') { champ.value = ''; montrerResultats(); champ.blur(); }
  });
  addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.target.closest?.('input, textarea')) return;
    e.preventDefault(); champ.focus();
  });

  chargement();
})();
