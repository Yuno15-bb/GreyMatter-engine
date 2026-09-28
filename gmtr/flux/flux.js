(function () {
  const { mouvementReduit } = window.GMTR;
  const $ = (id) => document.getElementById(id);
  const lignesEl = $('lignes'), fiche = $('fiche'), etat = $('etat'); // i18n-ok
  const POLL_MS = 4000, CONSTRUCTION_MS = mouvementReduit ? 0 : 70, RECENTE_S = 60;
  const FILTRES = [['all', 'all'], ['write', 'write'], ['read', 'read'], ['recall', 'recall'], ['commit', 'commit']];

  let tous = [], filtre = 'all', choix = 0, dernierTs = 0, surJour = {}, construction = null;
  const echapper = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const maintenant = () => Date.now() / 1000;
  const heure = (ts) => new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const jourCourt = (ts) => new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
  const memeJour = (ts) => new Date(ts * 1000).toDateString() === new Date().toDateString();

  const visibles = () => tous.filter((e) => filtre === 'all' || e.type === filtre);
  const capacite = () => Math.max(4, Math.floor(lignesEl.clientHeight / 18));

  function ligne(e) {
    const li = document.createElement('li');
    const age = maintenant() - e.ts;
    li.className = `ligne t-${e.type}` + (age < RECENTE_S ? ' recente' : '') + (age > 86400 ? ' vieille' : '');
    li.dataset.ts = e.ts;
    li.innerHTML =
      `<span class="etat-l">[${age < RECENTE_S ? '■' : ' '}]</span>` +
      `<span class="temps">${memeJour(e.ts) ? heure(e.ts) : jourCourt(e.ts)}</span>` +
      `<span class="type">${echapper(e.type)}</span>` +
      `<span class="session">${echapper(e.session || '—')}</span>` +
      `<span class="cible">${echapper(e.cible || '—')}</span>` +
      `<span class="d">${echapper(e.detail || '')}</span>` +
      `<span class="note">${echapper(e.note || '')}</span>`;
    li.addEventListener('click', () => choisir([...lignesEl.children].indexOf(li)));
    return li;
  }

  function choisir(i) {
    const rangs = lignesEl.children;
    if (!rangs.length) return;
    choix = Math.max(0, Math.min(rangs.length - 1, i));
    [...rangs].forEach((r) => r.classList.remove('choisie'));
    void rangs[choix].offsetWidth;
    rangs[choix].classList.add('choisie');
    const e = visibles()[choix];
    if (e) {
      const date = new Date(e.ts * 1000).toLocaleString('en-GB');
      const source = { write: 'state/note-writes.jsonl', read: 'state/read_log.jsonl', recall: 'state/recall_log.jsonl', commit: 'state/git-journal.jsonl' }[e.type];
      fiche.innerHTML = `<b>${echapper(e.cible || '—')}</b><br>${echapper(e.type)} · ${date} · session ${echapper(e.session || '—')}`
        + (e.detail ? ` · ${echapper(e.detail)}` : '') + (e.note ? ` · ${echapper(e.note)}` : '')
        + `<br><span class="src">source: ${source}</span>`;
    }
  }

  function reconstruire() {
    clearInterval(construction);
    lignesEl.innerHTML = '';
    fiche.textContent = '';
    const liste = visibles().slice(0, capacite());
    liste.forEach((e) => lignesEl.appendChild(ligne(e)));
    if (!CONSTRUCTION_MS) { choisir(0); return; }
    lignesEl.classList.add('construction');
    let k = 0;
    setTimeout(() => {
      construction = setInterval(() => {
        const r = lignesEl.children[k++];
        if (r) r.classList.add('vue');
        if (k >= lignesEl.children.length) { clearInterval(construction); lignesEl.classList.remove('construction'); choisir(0); }
      }, CONSTRUCTION_MS);
    }, 280);
  }

  function dessinerFiltres() {
    const total = Object.values(surJour).reduce((a, b) => a + b, 0);
    $('filtres').innerHTML = `<div class="filtre-titre" style="color:var(--sombre)">filter · 24 h</div>` + FILTRES.map(([cle, nom], i) =>
      `<div class="filtre${cle === filtre ? ' actif' : ''}" data-filtre="${cle}"><span class="marqueur"></span><span>${i + 1} ${nom}</span><span class="nb">${cle === 'all' ? total : (surJour[cle] || 0)}</span></div>`).join('');
    document.querySelectorAll('.filtre').forEach((el) => el.addEventListener('click', () => changerFiltre(el.dataset.filtre)));
  }
  function changerFiltre(f) {
    if (f === filtre) return;
    filtre = f; dessinerFiltres(); reconstruire();
  }

  function marquerAges() {
    for (const r of lignesEl.children) {
      const age = maintenant() - Number(r.dataset.ts);
      const recente = age < RECENTE_S;
      r.classList.toggle('recente', recente);
      r.querySelector('.etat-l').textContent = `[${recente ? '■' : ' '}]`;
    }
  }

  async function lire() {
    const r = await fetch('/flux.json', { cache: 'no-store' });
    if (r.status === 401) { location.href = '/'; return null; }
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  async function sonder() {
    try {
      const d = await lire();
      if (!d) return;
      surJour = d.sur_24h || {};
      const nouveaux = d.evenements.filter((e) => e.ts > dernierTs);
      tous = d.evenements;
      if (dernierTs && nouveaux.length) {
        const aMontrer = nouveaux.filter((e) => filtre === 'all' || e.type === filtre).reverse();
        for (const e of aMontrer) {
          const li = ligne(e);
          lignesEl.prepend(li);
          if (lignesEl.children.length > capacite()) lignesEl.lastElementChild.remove();
          if (choix === 0) { choisir(0); li.classList.add('arrive'); setTimeout(() => li.classList.remove('arrive'), 1000); }
          else choix = Math.min(choix + 1, lignesEl.children.length - 1);
        }
        dessinerFiltres();
      }
      if (d.evenements.length) dernierTs = Math.max(dernierTs, d.evenements[0].ts);
      etat.innerHTML = `<span class="vif">live</span> · polling ${POLL_MS / 1000} s · last event ${d.evenements[0] ? heure(d.evenements[0].ts) : '—'}`;
      $('sources').textContent = 'sources: ' + (d.sources || []).join(' · ');
      marquerAges();
    } catch {
      etat.innerHTML = `<span style="color:var(--alerte)">offline</span> · server not answering`;
    }
  }

  addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); choisir(choix + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); choisir(choix - 1); }
    else if (e.key === 'Escape') location.href = '/carte/';
    else if (/^[1-5]$/.test(e.key)) changerFiltre(FILTRES[Number(e.key) - 1][0]);
  });
  addEventListener('resize', () => reconstruire());

  (async function demarrer() {
    await document.fonts.ready;
    await sonder();
    dessinerFiltres();
    reconstruire();
    setInterval(sonder, POLL_MS);
  })();
})();
