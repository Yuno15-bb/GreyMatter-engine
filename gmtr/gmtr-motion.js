(function () {
  const reduit = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const attendre = (ms) => new Promise((r) => setTimeout(r, reduit ? 0 : ms));
  const GLYPHES = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' + '01234' + '56789#/_-';

  async function ecrire(el, texte, { pas = 14, decode = true, curseur = true, jeton } = {}) {
    texte = String(texte ?? '');
    if (reduit) { el.textContent = texte; return; }
    const c = document.createElement('span'); c.className = 'm-curseur';
    const t0 = performance.now(), duree = pas * texte.length;
    await new Promise((fini) => {
      (function image(t) {
        if (jeton && jeton.annule) return fini();
        const n = Math.min(texte.length, Math.floor((t - t0) / pas) + 1);
        const brouille = decode && n < texte.length && Math.random() < 0.35 ? GLYPHES[(Math.random() * GLYPHES.length) | 0] : '';
        el.textContent = texte.slice(0, n) + brouille;
        if (curseur && n < texte.length) el.appendChild(c);
        if (t - t0 < duree) requestAnimationFrame(image); else { el.textContent = texte; fini(); }
      })(t0);
    });
  }

  function barreDe(rang) {
    let b = rang.querySelector(':scope > .m-barre');
    if (!b) { b = document.createElement('span'); b.className = 'm-barre'; rang.prepend(b); rang.classList.add('m-rang'); }
    return b;
  }
  function barre(rang, fraction, { sombre = false, anime = true } = {}) {
    const b = barreDe(rang);
    b.classList.toggle('sombre', sombre);
    b.classList.toggle('anime', anime && !reduit);
    if (anime) void b.offsetWidth;
    b.style.transform = `scaleX(${Math.max(0, Math.min(1, fraction))})`;
    rang.classList.toggle('claire', !sombre && fraction > 0.5);
  }
  async function barreVersCible(rang, cible, opts = {}) {
    const r = rang.getBoundingClientRect(), c = cible.getBoundingClientRect();
    const fraction = r.width ? (c.right - r.left + 6) / (r.width + 12) : 1;
    barre(rang, fraction, opts);
    await attendre(420);
    cible.classList.add('m-cadre-cible');
  }

  function jauge(el, fraction, largeur = 96) {
    const n = Math.round(Math.max(0, Math.min(1, fraction)) * (largeur - 2));
    el.classList.add('m-jauge');
    el.innerHTML = `//<span class="plein">${'>'.repeat(n)}</span>${'-'.repeat(largeur - 2 - n)}`;
  }

  function coins(bloc) {
    bloc.classList.add('m-coins');
    if (bloc.querySelector(':scope > .m-coin')) return;
    for (const k of ['hg', 'hd', 'bg', 'bd']) { const s = document.createElement('span'); s.className = 'm-coin ' + k; bloc.appendChild(s); }
  }

  async function graineVers(graine, cibleRect, duree = 520) {
    const d = graine.getBoundingClientRect();
    graine.style.transition = 'none';
    graine.style.transformOrigin = 'left top';
    if (reduit) return;
    const anim = graine.animate([
      { transform: 'translate(0,0) scale(1,1)' },
      { transform: `translate(${cibleRect.left - d.left}px, ${cibleRect.top - d.top}px) scale(${cibleRect.width / d.width}, ${cibleRect.height / d.height})` },
    ], { duration: duree, easing: 'cubic-bezier(.16,.84,.24,1)', fill: 'forwards' });
    await anim.finished;
  }

  window.GMTRMotion = { ecrire, barre, barreVersCible, jauge, coins, graineVers, attendre, reduit };
})();
