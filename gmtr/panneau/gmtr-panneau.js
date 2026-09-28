(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const grille = $('#grille');
  const PERIODE_MS = 2000;
  const FIGE_S = 10;

  const ETATS = {
    'working': { glyphe: '▶', mot: 'working' },
    'idle':   { glyphe: '·', mot: 'idle' },
    'stale':      { glyphe: '!', mot: 'stale' },
    'never-seen':  { glyphe: '○', mot: 'never seen' },
  };

  function motDuVerdict(v) {
    if (!v || v === 'ok') return null;
    if (v === 'quota-or-login') return 'quota or login';
    if (v === 'interrupted') return 'interrupted';
    if (v === 'permissions-unavailable') return 'permissions unavailable';
    const m = /^failed-code-(\d+)$/.exec(v);
    return m ? `code failure ${m[1]}` : v.replace(/-/g, ' ');
  }

  function duree(s) {
    if (s == null) return '';
    if (s < 60) return `${Math.round(s)} s`;
    if (s < 3600) return `${Math.round(s / 60)} min`;
    if (s < 86400) return `${Math.round(s / 3600)} h`;
    return `${Math.round(s / 86400)} d`;
  }

  const cases = new Map();
  let coeur, verdictCoeur, compteCoeur;
  const sceau = document.getElementById('sceau');
  const raisonBande = document.getElementById('raison');

  function batir(agents) {
    grille.textContent = '';
    coeur = document.createElement('section');
    coeur.className = 'coeur';
    coeur.dataset.delibere = '0';
    coeur.innerHTML = `<p class="marque" aria-hidden="true">GMTR</p>
      <p class="verdict" id="c-verdict" role="status">—</p>
      <p class="compte micro" id="c-compte"></p>`;
    grille.appendChild(coeur);
    verdictCoeur = $('#c-verdict', coeur); compteCoeur = $('#c-compte', coeur);

    for (const a of agents) {
      const el = document.createElement('article');
      el.className = 'case';
      el.setAttribute('role', 'listitem');
      el.dataset.case = a.case;
      el.innerHTML = `<span class="numero micro">${String(a.case).padStart(2, '0')}</span>
        <div class="dedans">
          <span class="nom">${a.nom}</span>
          <span class="role micro">${a.cle}</span>
          <span class="etat"><span class="glyphe" aria-hidden="true">·</span><span class="mot">—</span></span>
          <span class="detail"></span>
        </div>`;
      grille.appendChild(el);
      cases.set(a.cle, el);
    }
  }

  function peindre(a) {
    const el = cases.get(a.cle);
    if (!el) return;
    const base = ETATS[a.etat] || ETATS['never-seen'];
    const rate = a.etat === 'idle' ? motDuVerdict(a.verdict) : null;
    el.dataset.etat = a.etat;
    if (rate) el.dataset.echec = '1'; else el.removeAttribute('data-echec');
    $('.glyphe', el).textContent = rate ? '×' : base.glyphe;
    $('.mot', el).textContent = rate || base.mot;

    let detail = '';
    if (a.etat === 'never-seen') detail = 'no recorded run';
    else if (a.etat === 'working') detail = `${a.activite || '—'} · for ${duree(a.depuis_s)}`;
    else if (a.etat === 'stale') detail = `started ${duree(a.depuis_s)} ago, no end recorded`;
    else {
      const bouts = [`${duree(a.depuis_s)} ago`];
      if (a.duree_s != null) bouts.push(`${duree(a.duree_s)} of work`);
      if (a.cout_usd != null) bouts.push(`${a.cout_usd.toFixed(2)}\u00a0$`);
      detail = bouts.join(' · ');
    }
    const p = $('.detail', el);
    if (p.textContent !== detail) p.textContent = detail;
    el.title = `${a.cle}` + (a.raison ? ` · reason: ${a.raison}` : '');
  }

  let derniereRaison = null, jetonRaison = null;

  function peindreCoeur(d) {
    const actifs = d.agents.filter((a) => a.etat === 'working');
    const jamais = d.agents.filter((a) => a.etat === 'never-seen').length;
    coeur.dataset.delibere = d.delibere ? '1' : '0';
    sceau.dataset.actif = d.delibere ? '1' : '0';

    const titre = d.delibere ? 'deliberating' : 'no deliberation';
    if (verdictCoeur.textContent !== titre) verdictCoeur.textContent = titre;
    compteCoeur.textContent = `${actifs.length} working of ${d.agents.length}`
      + (jamais ? ` · ${jamais} never seen` : ''); // i18n-ok

    let raison;
    if (actifs.length) {
      raison = actifs.map((a) => `${a.nom} : ${a.raison || a.activite || 'no reason recorded'}`).join('   ·   ');
    } else {
      const finis = d.agents.filter((a) => a.etat === 'idle')
        .sort((x, y) => (x.depuis_s || 0) - (y.depuis_s || 0));
      raison = finis.length
        ? `last run: ${finis[0].nom}, ${motDuVerdict(finis[0].verdict) || 'completed'}, il y a ${duree(finis[0].depuis_s)}`
        : 'no runs in the journal';
    }
    if (raison !== derniereRaison) {
      derniereRaison = raison;
      if (jetonRaison) jetonRaison.annule = true;
      jetonRaison = { annule: false };
      if (window.GMTRMotion) GMTRMotion.ecrire(raisonBande, raison, { pas: 10, jeton: jetonRaison });
      else raisonBande.textContent = raison;
    }
  }

  let derniereMesure = null;
  const elFraicheur = document.getElementById('fraicheur');

  function peindreFraicheur() {
    if (derniereMesure === null) return;
    const age = (Date.now() - derniereMesure) / 1000;
    const fige = age > FIGE_S;
    elFraicheur.dataset.fige = fige ? '1' : '0';
    elFraicheur.textContent = fige
      ? `stale — last measured ${duree(age)}`
      : `measured ${duree(age)}`;
  }

  function annoncer(texte, alerte) {
    elFraicheur.dataset.fige = alerte ? '1' : '0';
    elFraicheur.textContent = texte;
  }

  let bati = false;

  async function sonder() {
    let d;
    try {
      const r = await fetch('/agents.json', { cache: 'no-store' });
      d = await r.json();
    } catch (e) {
      return annoncer('server unavailable', true);
    }
    if (d.verrouille) return annoncer('locked — open the home page', true);
    if (!Array.isArray(d.agents)) return annoncer('invalid response', true);

    if (!bati) { batir(d.agents); bati = true; }
    for (const a of d.agents) peindre(a);
    peindreCoeur(d);
    derniereMesure = Date.now();
    peindreFraicheur();

    const vues = grille.querySelectorAll('.case').length;
    document.getElementById('recensement').textContent =
      `${d.agents.length} agents · ${vues} shown`
      + (vues < d.agents.length ? ` · ${d.agents.length - vues} NOT SHOWN` : '');

    const src = String(d.source || '').split('/').pop();
    document.getElementById('source').textContent =
      src.includes('demo') ? `${src} — sample data` : src;
  }

  sonder();
  setInterval(sonder, PERIODE_MS);
  setInterval(peindreFraicheur, 1000);
})();
