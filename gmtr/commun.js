(function () {
  const racine = document.documentElement;
  const params = new URLSearchParams(location.search);
  const mouvementReduit = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function lire(cle, defaut) {
    try { return localStorage.getItem('cbrain.' + cle) ?? defaut; } catch { return defaut; }
  }
  function ecrire(cle, valeur) {
    try { localStorage.setItem('cbrain.' + cle, valeur); } catch {  }
  }

  racine.dataset.palette = params.get('palette') || lire('palette', 'vert');
  racine.dataset.effets = params.get('effets') || lire('effets', mouvementReduit ? '0' : '1');

  addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'p' || e.key === 'P') {
      racine.dataset.palette = racine.dataset.palette === 'vert' ? 'orange' : 'vert';
      ecrire('palette', racine.dataset.palette);
    } else if (e.key === 'e' || e.key === 'E') {
      racine.dataset.effets = racine.dataset.effets === '1' ? '0' : '1';
      ecrire('effets', racine.dataset.effets);
    }
  });

  function dissoudre(canvas, sens, fini) {
    const duree = parseInt(getComputedStyle(racine).getPropertyValue('--duree-dissolution'), 10) || 320;
    if (mouvementReduit || params.get('instant')) {
      canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
      canvas.classList.add('pret');
      return fini && fini();
    }
    const dpr = devicePixelRatio || 1, cote = 10;
    const l = innerWidth, h = innerHeight;
    canvas.width = l * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const colonnes = Math.ceil(l / cote), lignes = Math.ceil(h / cote), n = colonnes * lignes;
    const ordre = new Uint32Array(n);
    for (let i = 0; i < n; i++) ordre[i] = i;
    for (let i = n - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [ordre[i], ordre[j]] = [ordre[j], ordre[i]]; }
    const fond = getComputedStyle(racine).getPropertyValue('--fond').trim();
    ctx.fillStyle = fond;
    if (sens === 'entree') ctx.fillRect(0, 0, l, h);
    canvas.classList.add('pret');
    let fait = 0; const debut = performance.now();
    (function pas(t) {
      const cible = Math.min(n, Math.floor(((t - debut) / duree) * n));
      for (; fait < cible; fait++) { // i18n-ok
        const c = ordre[fait], x = (c % colonnes) * cote, y = ((c / colonnes) | 0) * cote;
        if (sens === 'entree') ctx.clearRect(x, y, cote, cote); else ctx.fillRect(x, y, cote, cote);
      }
      if (fait < n) requestAnimationFrame(pas); else if (fini) fini(); // i18n-ok
    })(debut);
  }

  window.GMTR = { dissoudre, mouvementReduit, params };
})();
