(function () {
  const { mouvementReduit, params } = window.GMTR;
  const M = window.GMTRMotion;
  const $ = (id) => document.getElementById(id);
  const rapide = mouvementReduit || !!params.get('instant');
  const echelle = rapide ? 0 : parseFloat(params.get('ralenti') || '1');
  let passee = false;
  const enAttente = new Set();
  const pause = (ms) => new Promise((r) => {
    const fin = () => { clearTimeout(t); enAttente.delete(fin); r(); };
    const t = setTimeout(fin, ms * echelle);
    enAttente.add(fin);
  });
  const passerTout = () => { passee = true; [...enAttente].forEach((f) => f()); };
  const echapper = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const octets = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`;

  const SCENES = ['amorce', 'verrou'];
  function montrer(id) {
    SCENES.forEach((s) => {
      const el = $(s), ici = s === id;
      el.classList.toggle('visible', ici);
      el.setAttribute('aria-hidden', ici ? 'false' : 'true');
    });
  }


  function preparerCanvas(c, l, h) {
    const dpr = devicePixelRatio || 1;
    c.width = l * dpr; c.height = h * dpr; c.style.width = l + 'px'; c.style.height = h + 'px';
    const ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }

  const MOTS = new Set('const let var await async function return if else for of in new while break continue try catch throw class import export from default typeof null true false this'.split(' '));
  function colorer(ligne) {
    const motif = /(`(?:[^`\\]|\\.)*`|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(\b\d[\d_.]*\b)|([A-Za-z_$][\w$]*)(\s*\()?|(--[\w-]+)|([{}()[\];,.=<>+\-*/!&|?:%]+)/g;
    let out = '', dernier = 0, m;
    while ((m = motif.exec(ligne))) {
      out += echapper(ligne.slice(dernier, m.index));
      const [tout, chaine, nombre, ident, appel, variable, ponct] = m;
      if (chaine) out += `<span class="s">${echapper(chaine)}</span>`;
      else if (nombre) out += `<span class="n">${nombre}</span>`;
      else if (ident && MOTS.has(ident)) out += `<span class="k">${ident}</span>${appel || ''}`;
      else if (ident && appel) out += `<span class="f">${echapper(ident)}</span>${echapper(appel)}`;
      else if (ident && ident.startsWith('$')) out += `<span class="f">${echapper(ident)}</span>`;
      else if (ident) out += echapper(ident);
      else if (variable) out += `<span class="s">${variable}</span>`;
      else if (ponct) out += `<span class="p">${echapper(ponct)}</span>`;
      else out += echapper(tout);
      dernier = motif.lastIndex;
    }
    return out + echapper(ligne.slice(dernier));
  }
  function sansCommentaires(texte) {
    return texte.replace(/\/\*[\s\S]*?\*\//g, '').split('\n')
      .map((l) => l.replace(/(^|[^:'"`])\/\/.*$/, '$1').replace(/\s+$/, ''))
      .filter((l, i, t) => l.trim() || (t[i - 1] || '').trim());
  }

  const MARQUE = window.GMTRMarque;
  const logo = { cible: 0, lisse: 0, vue: 0, ctx: null, larg: 0, haut: 0, hbloc: 0, arrive: false };
  const HALO = [[3, 0.45], [12, 0.28]], HALO_BORD = 24;
  function dessinerLogo() {
    MARQUE.carre(logo.ctx, { larg: logo.larg, haut: logo.haut, hbloc: logo.hbloc,
      tr: logo.vue >= 1 ? null : MARQUE.instant(logo.vue), echo: logo.retro, trame: logo.retro });
    if (logo.halo) {
      const h = logo.halo, c = logo.ctx.canvas, d = c.width / logo.larg;
      h.save(); h.setTransform(1, 0, 0, 1, 0, 0); h.clearRect(0, 0, h.canvas.width, h.canvas.height);
      for (const [flou, a] of HALO) { h.filter = `blur(${flou * d}px) contrast(2)`; h.globalAlpha = a; h.drawImage(c, HALO_BORD * d, HALO_BORD * d); }
      h.restore();
    }
  }
  new MutationObserver(() => { if (logo.ctx) { preparerLogo(); dessinerLogo(); } })
    .observe(document.documentElement, { attributes: true, attributeFilter: ['data-app'] });
  function preparerLogo() {
    const impose = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--logo-bloc'));
    logo.hbloc = impose > 0 ? Math.round(impose) : Math.round(Math.min(innerWidth, innerHeight) * 0.2);
    const c = MARQUE.cadre(logo.hbloc);
    logo.larg = Math.round(c.larg); logo.haut = Math.round(c.haut);
    logo.retro = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--logo-retro')) > 0;
    logo.ctx = preparerCanvas($('logo'), logo.larg, logo.haut);
    if (logo.retro) {
      let h = $('logo-halo');
      if (!h) { h = document.createElement('canvas'); h.id = 'logo-halo'; h.className = 'logo-centre logo-halo';
        h.setAttribute('aria-hidden', 'true'); $('logo').before(h); }
      logo.halo = preparerCanvas(h, logo.larg + 2 * HALO_BORD, logo.haut + 2 * HALO_BORD);
    }
    MARQUE.pret.then(() => { if (logo.arrive) dessinerLogo(); });
    (function image() {
      const k = echelle ? 0.1 : 1;
      logo.lisse += (logo.cible - logo.lisse) * k;
      logo.vue += (logo.lisse - logo.vue) * (echelle ? 0.12 : 1);
      if (logo.cible >= 1 && 1 - logo.lisse < 0.002) logo.lisse = 1;
      if (logo.cible >= 1 && 1 - logo.vue < 0.002) logo.vue = 1;
      if (!passee) $('barre-remplissage').style.width = (Math.min(1, logo.vue / FIN_DECALEE) * 100).toFixed(2) + '%';
      dessinerLogo();
      logo.arrive = logo.vue >= 1 && logo.cible >= 1;
      if (!logo.arrive && !passee) requestAnimationFrame(image);
    })();
  }
  function barre(fraction) {
    const v = Math.max(0, Math.min(1, fraction));
    if (!echelle || passee) $('barre-remplissage').style.width = (v * 100).toFixed(2) + '%';
    logo.cible = v * FIN_DECALEE;
  }
  const FIN_DECALEE = 0.72, DECALAGE_MS = 2200;
  async function finirLogo() {
    const depart = logo.cible, t0 = performance.now(), duree = DECALAGE_MS * echelle;
    await new Promise((fini) => {
      (function image(t) {
        const q = duree ? Math.min(1, (t - t0) / duree) : 1;
        logo.cible = depart + (1 - depart) * q;
        if (q < 1 && !passee) requestAnimationFrame(image); else { logo.cible = 1; fini(); }
      })(t0);
    });
    while (!logo.arrive && !passee && echelle) await new Promise((r) => requestAnimationFrame(r));
  }
  const TENUE_MS = 250;
  function bipSonore() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      if (ctx.state !== 'running') { ctx.close(); return; }
      [0].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = 'square'; o.frequency.value = 1320;
        g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.025, ctx.currentTime + t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.08);
        o.connect(g).connect(ctx.destination); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.1);
      });
      setTimeout(() => ctx.close(), 800);
    } catch {  }
  }
  const CLIGNOTEMENT_LOGO_MS = 200;
  async function tenirLogo() {
    if (passee) return;
    await pause(TENUE_MS);
    if (passee) return;
    const c = $('logo');
    c.classList.remove('bip'); void c.offsetWidth; c.classList.add('bip');
    bipSonore();
    await pause(CLIGNOTEMENT_LOGO_MS);
  }

  async function sceneAmorce(amorce) {
    montrer('amorce');
    preparerLogo();
    barre(0);
    const etat = $('etat-machine'), flux = $('flux'), jaugeEl = $('flux-jauge');
    etat.innerHTML = ''; flux.innerHTML = '';
    M.coins($('amorce-gauche')); M.coins($('flux-bloc'));
    const largeurJauge = () => Math.max(20, Math.floor(jaugeEl.clientWidth / 6.9));
    M.jauge(jaugeEl, 0, largeurJauge());
    const phase = (nom) => document.querySelectorAll('#phases li').forEach((li, k, t) => {
      const ordre = [...t].map((x) => x.dataset.phase), ici = ordre.indexOf(nom);
      li.classList.toggle('courante', k === ici); li.classList.toggle('m-cadre', k === ici); li.classList.toggle('faite', k < ici); // i18n-ok
    });
    phase('source');
    await pause(80);
    const lignesEtat = amorce
      ? [['PROG', amorce.programme], ['LISTEN', amorce.ecoute], ['PID', amorce.pid], ['PYTHON', amorce.python], ['TRUNK', amorce.commit || '—']]
      : [['PROG', 'GMTR'], ['LISTEN', 'no answer']];
    for (const [cle, val] of lignesEtat) {
      if (passee) return;
      const ligneEtat = document.createElement('span');
      etat.appendChild(document.createTextNode(`${cle.padEnd(7)}: `));
      ligneEtat.className = 'ref'; etat.appendChild(ligneEtat); etat.appendChild(document.createTextNode('\n'));
      await M.ecrire(ligneEtat, String(val), { pas: 3 * (echelle || 0.001) });
    }

    let texte = '';
    try { texte = (await Promise.all(['sequence.js', 'commun.js'].map((f) => fetch(f).then((r) => r.text())))).join('\n'); } catch {  }
    const code = sansCommentaires(texte);
    const tests = amorce ? amorce.lignes : [];
    const hex = (n) => '0x' + n.toString(16).toUpperCase().padStart(4, '0');

    let capValeur = 0, capLargeur = -1;
    const capacite = () => {
      if (flux.clientWidth === capLargeur && capValeur) return capValeur;
      capLargeur = flux.clientWidth;
      if (!capLargeur) return 78;
      const d = document.createElement('div');
      d.className = 'ligne'; d.style.visibility = 'hidden';
      d.innerHTML = `<span class="txt">${'M'.repeat(40)}</span>`;
      flux.appendChild(d);
      const chasse = d.firstElementChild.getBoundingClientRect().width / 40;
      const large = d.clientWidth;
      d.remove();
      capValeur = chasse > 1 ? Math.max(24, Math.floor(large / chasse) - 1) : 78;
      return capValeur;
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { capLargeur = -1; });
    const court = (s, n) => { s = String(s); return s.length > n ? '…' + s.slice(-(n - 1)) : s.padEnd(n); };
    const courtD = (s, n) => { s = String(s); return s.length > n ? (s.slice(0, n - 1).replace(/\s+$/, '') + '…').padEnd(n) : s.padEnd(n); };
    const poidsDe = (l) => l.detail || (l.octets == null ? '—' : octets(l.octets));
    const repartir = (place, aMax, bMax) => {
      if (aMax + bMax <= place) return [aMax, bMax];
      let a = Math.min(aMax, Math.max(5, Math.round(place * aMax / (aMax + bMax))));
      const b = Math.min(bMax, Math.max(5, place - a));
      return [Math.max(4, Math.min(aMax, place - b)), b];
    };
    const mesurerColonnes = () => {
      const cap = capacite();
      const roleMax = Math.max(4, ...tests.map((l) => l.role.length));
      const cheminMax = Math.max(6, ...tests.map((l) => l.chemin.length));
      const poidsMax = Math.max(1, ...tests.map((l) => poidsDe(l).length));
      const dureeMax = Math.max(4, ...tests.map((l) => l.lu_ms.toFixed(2).length));
      const verdictMax = Math.max(2, ...tests.map((l) => (l.present ? 2 : 6)));
      let dernier = null;
      for (const [tete, poids, duree] of [[1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0]]) {
        const fixe = (tete ? 9 : 0) + (poids ? 1 + poidsMax : 0) + (duree ? 6 + dureeMax : 0) + 3 + verdictMax;
        const place = cap - fixe - 1;
        const [role, chemin] = repartir(place, roleMax, cheminMax);
        dernier = { tete, poids, duree, role, chemin, poidsMax, dureeMax };
        if (role >= 6 && chemin >= 10) return dernier;
      }
      return dernier;
    };
    let COL = null;
    const segmentsTest = (b, l) => {
      const s = [];
      if (COL.tete) s.push({ t: hex(b) + ' | ', c: 't' });
      s.push({ t: courtD(l.role.toUpperCase(), COL.role), c: 'b' }, { t: ' ' });
      s.push({ t: court(l.chemin, COL.chemin), c: 'ref', ech: true });
      if (COL.poids) s.push({ t: ' ' + poidsDe(l).padStart(COL.poidsMax) });
      if (COL.duree) s.push({ t: ' · ', c: 'p' }, { t: l.lu_ms.toFixed(2).padStart(COL.dureeMax), c: 'n' }, { t: ' ms' });
      s.push({ t: ' · ', c: 'p' },
             { t: l.present ? 'OK' : 'ABSENT', c: l.present ? 'ok' : (l.chemin === 'state/FREEZE' ? 'p' : 'ko') });
      return s;
    };
    const enClair = (s) => s.map((x) => x.t).join('');
    const enCouleur = (s) => s.map((x) => {
      const t = x.ech ? echapper(x.t) : x.t;
      return x.c ? `<span class="${x.c}">${t}</span>` : t;
    }).join('');
    const preparerColonnes = () => {
      if (COL) return COL;
      COL = mesurerColonnes();
      if (!tests.length || !flux.clientWidth) return COL;
      const large = flux.clientWidth;
      const d = document.createElement('div');
      d.className = 'ligne test'; d.style.visibility = 'hidden';
      d.innerHTML = '<span class="txt"></span>';
      flux.appendChild(d);
      const txt = d.firstElementChild;
      const encreMax = () => tests.reduce((max, l, k) => {
        txt.innerHTML = enCouleur(segmentsTest(k, l));
        const r = document.createRange(); r.selectNodeContents(txt);
        return Math.max(max, r.getBoundingClientRect().width);
      }, 0);
      for (let garde = 40; garde > 0 && encreMax() > large; garde--) { // i18n-ok
        if (COL.chemin > 10) COL.chemin--;
        else if (COL.role > 5) COL.role--;
        else if (COL.duree) COL.duree = 0;
        else if (COL.poids) COL.poids = 0;
        else if (COL.tete) COL.tete = 0;
        else break;
      }
      d.remove();
      return COL;
    };

    const curseur = document.createElement('span'); curseur.className = 'curseur-flux';
    const ajouter = (html, classe = '') => {
      const div = document.createElement('div');
      div.className = 'ligne ' + classe; div.innerHTML = `<span class="txt">${html || '&nbsp;'}</span>`;
      curseur.remove(); div.querySelector('.txt').appendChild(curseur);
      flux.appendChild(div);
      while (flux.scrollHeight > flux.clientHeight && flux.firstChild) flux.firstChild.remove();
      return div;
    };

    const capTete = capacite();
    const trunk = echapper(String((amorce && amorce.commit) || 'unknown'));
    ajouter(amorce
      ? (capTete >= 84
          ? `<span class="b">GMTR POWER-ON SELF-TEST</span> <span class="p">//</span> <span class="ref">trunk ${trunk}</span> <span class="p">//</span> reading trunk files, contents untouched`
          : capTete >= 63
            ? `<span class="b">GMTR POWER-ON SELF-TEST</span> <span class="p">//</span> <span class="ref">trunk ${trunk.slice(0, 7)}</span> <span class="p">//</span> contents untouched`
            : capTete >= 44
              ? `<span class="b">GMTR POWER-ON SELF-TEST</span> <span class="p">//</span> <span class="ref">${trunk.slice(0, 7)}</span>`
              : `<span class="b">GMTR SELF-TEST</span> <span class="p">//</span> <span class="ref">${trunk.slice(0, 7)}</span>`)
      : (capTete >= 64
          ? '<span class="ko">GMTR SELF-TEST · /amorce.json NOT ANSWERING · NO FILE CHECKED</span>'
          : '<span class="ko">SELF-TEST · NO ANSWER · 0 FILE</span>'), 'tete');
    await pause(60);

    let i = 0;
    const blocs = Math.max(tests.length, 1);
    const parBloc = Math.max(4, Math.min(10, Math.floor(code.length / blocs)));
    const unites = Math.min(code.length, blocs * parBloc) + tests.length + 1;
    let faites = 0;
    const avancer = () => barre(++faites / unites);
    const DUREE_DEFILEMENT = 4060 * echelle, debutDefilement = performance.now();
    const auRythme = async () => {
      if (!echelle) return;
      const reste = debutDefilement + DUREE_DEFILEMENT * (faites / unites) - performance.now();
      if (reste > 0) await pause(reste / echelle);
    };
    phase(tests.length ? 'source' : 'lock');
    for (let b = 0; b < blocs; b++) {
      for (let j = 0; j < parBloc && i < code.length; j++, i++) {
        if (passee) return;
        ajouter(colorer(code[i]));
        avancer();
        await auRythme();
      }
      const l = tests[b];
      if (!l) continue;
      phase('test');
      const rang = ajouter('', 'test');
      M.barre(rang, 1, { sombre: true, anime: false });
      await pause(30);
      if (passee) return;
      M.barre(rang, 1, { anime: false });
      preparerColonnes();
      const seg = segmentsTest(b, l);
      const classeVerdict = seg[seg.length - 1].c;
      const txt = rang.querySelector('.txt');
      await M.ecrire(txt, enClair(seg), { pas: 0.5 * (echelle || 0.001) });
      txt.innerHTML = enCouleur(seg);
      const ref = txt.querySelector('.ref').getBoundingClientRect(), rr = rang.getBoundingClientRect();
      M.barre(rang, rr.width ? (ref.left + ref.width * 0.55 - rr.left) / rr.width : 0.4, { sombre: true });
      await pause(30);
      txt.querySelector('.' + classeVerdict)?.classList.add('m-cadre-cible');
      M.jauge(jaugeEl, (b + 1) / tests.length, largeurJauge());
      avancer();
      await auRythme();
    }
    barre(1);
    if (amorce) {
      const trouves = tests.filter((l) => l.present).length;
      ajouter(capacite() >= 56
        ? `<span class="t">${hex(tests.length)} |</span> <span class="b">SELF-TEST COMPLETE</span> in <span class="n">${amorce.duree_ms.toFixed(2)}</span> ms <span class="p">·</span> <span class="ok">${trouves}/${tests.length} FOUND</span>`
        : `<span class="b">SELF-TEST COMPLETE</span> <span class="p">·</span> <span class="ok">${trouves}/${tests.length}</span> <span class="p">·</span> <span class="n">${amorce.duree_ms.toFixed(0)}</span> ms`, 'test');
    }
    phase('lock');
    await finirLogo();
    await tenirLogo();
  }

  const X = ['#...#', '.#.#.', '..#..', '.#.#.', '#...#'];
  const CLIGNOTEMENT_MS = 280;
  function glyphe() {
    const g = document.createElement('span'); g.className = 'glyphe';
    g.innerHTML = X.join('').split('').map((c) => `<i class="${c === '#' ? 'on' : ''}"></i>`).join('');
    return g;
  }
  function afficherGlyphes(n) {
    const box = $('glyphes'), croix = () => box.querySelectorAll(':scope > .glyphe');
    while (croix().length < n) box.appendChild(glyphe());
    while (croix().length > n) croix()[croix().length - 1].remove();
  }
  function essais(restants) {
    $('coin-essais').textContent = restants == null ? 'lock armed' : `attempts left · ${restants}`;
  }

  async function sceneVerrou() {
    montrer('verrou');
    $('passer').classList.remove('visible');
    essais(5);
    M.coins($('glyphes'));
    M.ecrire(document.querySelector('.verrou-titre'), 'access code', { pas: 55 });
    const champ = $('code'), msg = $('verrou-message');
    msg.className = 'verrou-message indice';
    msg.textContent = 'type the code · enter';
    champ.value = ''; afficherGlyphes(0); champ.focus();
    document.addEventListener('pointerdown', () => setTimeout(() => champ.focus(), 0));
    champ.addEventListener('input', () => {
      champ.value = champ.value.replace(/\s/g, '');
      $('glyphes').classList.remove('refuse');
      msg.className = 'verrou-message'; msg.textContent = '';
      afficherGlyphes(champ.value.length);
    });

    return new Promise((accorde) => {
      let occupe = false;
      champ.addEventListener('keydown', async (e) => {
        if (e.key !== 'Enter' || occupe || !champ.value) return;
        e.preventDefault(); occupe = true;
        const attente = $('attente'); attente.classList.add('visible');
        let angle = 0;
        const tourne = setInterval(() => { angle = (angle + 45) % 180; attente.style.transform = `translateX(-50%) rotate(${angle}deg)`; }, 130);
        const [rep] = await Promise.all([
          fetch('/deverrouiller', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: champ.value }) })
            .then(async (r) => ({ statut: r.status, corps: await r.json().catch(() => ({})) }))
            .catch(() => ({ statut: 0, corps: {} })),
          pause(1100),
        ]);
        clearInterval(tourne); attente.classList.remove('visible');
        if (rep.statut === 200 && rep.corps.ok) return accorde();
        const box = $('glyphes');
        box.classList.add('refuse');
        champ.readOnly = true;
        msg.className = 'verrou-message refuse';
        const r = rep.corps;
        if (rep.statut === 429 || r.attendre_s) { msg.textContent = `locked · retry in ${r.attendre_s} s`; essais(0); }
        else if (r.raison === 'non_arme') { msg.textContent = 'lock not armed · no code stored'; essais(null); }
        else if (rep.statut === 0) msg.textContent = 'server unreachable';
        else { M.ecrire(msg, 'access denied', { pas: 30 }); essais(r.restants); }
        await new Promise((r) => setTimeout(r, mouvementReduit ? 800 : 3 * CLIGNOTEMENT_MS));
        champ.value = ''; afficherGlyphes(0);
        box.classList.remove('refuse');
        champ.readOnly = false; occupe = false;
      });
    });
  }

  async function sceneAccorde() {
    const g = [...$('glyphes').querySelectorAll(':scope > .glyphe')];
    for (const el of g) { el.classList.add('balaye'); await pause(Math.max(60, 420 / g.length)); }
    await pause(700);
  }

  async function ouvrir() {
    addEventListener('keydown', function passer(e) {
      if (e.key !== 'Escape' || passee) return;
      removeEventListener('keydown', passer);
      $('passer').classList.remove('visible');
      passerTout();
    });
    $('voile').classList.add('pret');
    if (!rapide) $('passer').classList.add('visible');

    const amorce = await fetch('/amorce.json', { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
    await document.fonts.ready;
    if (!passee) await sceneAmorce(amorce);
    passee = true;
    await sceneVerrou();
    passee = false;
    await sceneAccorde();
    location.href = '/carte/';
  }
  ouvrir();
})();
