/* Filme l'orbe pour la démo du README.

   ⚠ TROIS PIÈGES, tous payés une fois :
     · une fenêtre CACHÉE fige les couleurs — `document.hidden` coupe
       l'interpolation, la mécanique change mais jamais la teinte ;
     · un fond en DÉGRADÉ dessine un carré visible autour de la vignette une
       fois posée dans la page — il faut la couleur exacte du fond, à plat ;
     · une étape plus courte que DEUX FOIS le fondu (1,4 s) ne montre jamais
       l'objet stable, seulement des transitions enchaînées.
   Encodage : img2webp -d 50 -lossy -q 88 -sharp_yuv -m 6. En dessous de q≈88,
   les dégradés du verre et le texte de 5 px repartent en macro-blocs.
*/
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path'), cp = require('child_process');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const OUT = process.env.FILM_OUT || '/tmp/film';
// ⚠ LE PAVÉ SE NOURRIT PAR SON ENTRÉE, PAS PAR UNE POIGNÉE. Première tentative :
//   une fonction exposée sur `window` pour poser les lignes. Elle a écrasé
//   `window.__orbe`, déjà pris par l'objet orbe (planche.cjs et silhouette.cjs
//   s'en servent), puis elle s'est fait repeindre par le lecteur de flux une
//   seconde plus tard. On écrit donc un VRAI fichier de session, au format que
//   la page lit déjà : même chemin de code que sur un vrai bureau, rien à
//   maintenir dans la page, et le tournage prouve du même coup que ce chemin
//   marche. Le fichier est supprimé à la fin.
//
//   Pourquoi c'est nécessaire : le pavé montre le code RÉELLEMENT écrit par la
//   session en cours. Parfait sur le bureau de quelqu'un, impubliable dans un
//   README — la vignette en ligne a montré pendant deux semaines du français
//   tiré des fichiers de l'auteur.
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
  // ⚠ LE RYTHME DU FILM N'EST PAS LE RYTHME DE L'ORBE. Première version : douze
  //   états à 1,4 s. Or le FONDU de mécanique dure 1,4 s à lui seul — on ne
  //   voyait donc jamais un état stable, seulement des transitions enchaînées.
  //   Règle : une étape doit durer AU MOINS deux fois le fondu.
  //   Le budget se prend sur le NOMBRE d'états, jamais sur leur durée.
  // ⚠ `synthesizing` écarté à la demande de l'auteur.
  // Le troisième champ est le DÉTAIL affiché sous l'état : il vaut un sujet
  // fictif, pas « demo ». Un mot de débogage sous une vignette de README se lit
  // comme un oubli, et c'est ce qu'il est.
  // ⚠ LA DURÉE SE PAIE EN OCTETS, ET LA QUALITÉ N'EST PAS NÉGOCIABLE : le verre
  //   repart en macro-blocs sous q≈88 (voir l'en-tête). À 45 i/s et q90, chaque
  //   seconde coûte ~300 Ko dans le README — donc on coupe des SECONDES, jamais
  //   la qualité. Le plancher reste « deux fois le fondu », soit 3 s.
  ['idle',        'idle', 2000, ''],
  ['gardening',   'busy', 3200, 'filing three new notes'],
  ['committing',  'busy', 3200, 'one zone per commit'],
  ['idle',        'idle', 2200, ''],
];
// ⚠ LE PLAN DE TOURNAGE SE DÉPLACE, LE PLANCHER NON. `FILM_ETATS` remplace la
//   liste ci-dessus, au format `etat:millisecondes:detail|…` — il sert aux
//   formats de plateforme (15 s pour LinkedIn/GitHub/portfolio, 20/09) sans
//   toucher à la démo du README, qui reste le défaut. Le plancher de 3 s est
//   REFUSÉ à l'exécution, pas commenté : une étape plus courte que deux fondus
//   ne montre jamais l'objet stable, et c'est exactement l'erreur que l'en-tête
//   raconte avoir déjà payée une fois.
if (process.env.FILM_ETATS) {
  ETATS.length = 0;
  for (const bloc of process.env.FILM_ETATS.split('|')) {
    const [etat, ms, ...reste] = bloc.split(':');
    const duree = Number(ms);
    if (!Number.isFinite(duree) || duree < 3000) {
      console.error(`⛔ ${etat} : ${ms} ms — sous le plancher de 3000 ms (deux fondus).`);
      process.exit(4);
    }
    ETATS.push([etat, etat === 'idle' ? 'idle' : 'busy', duree, reste.join(':')]);
  }
}
// ⚠ ET ON PART D'UNE FORME POSÉE. Sans ça, la première image du film est un
//   fondu depuis l'état que la session avait laissé dans status.json — sur une
//   boucle, ce raccord se voit. `FILM_PRE` pose l'état d'ouverture AVANT le
//   chargement : les 4,3 s d'attente qui suivent dépassent les 2,6 s de pose.
const PRE = process.env.FILM_PRE || '';

// ⚠ NI `PAS`, NI `capturePage()`. Un aller-retour de capture coûte ~50 ms : la
//   boucle plafonnait à 20 i/s, et l'auteur l'a vue saccader à côté de la carte,
//   filmée à 45. On passe par le SCREENCAST du protocole de débogage, qui pousse
//   les images au rythme du rendu au lieu de les demander une par une.
// ⚠ ET ON SUR-ÉCHANTILLONNE : fenêtre 3× plus grande + `setZoomFactor(3)`, donc
//   la mise en page reste 150×150 en pixels CSS mais elle est RENDUE en 450×450.
//   Réduite ensuite à 336 px, elle est lissée. Sans ça, le bord du verre sort en
//   marches d'escalier — « pixélisé sur les bords », constaté sur la vignette
//   publiée, qui était captée à la taille d'affichage.
// ⚠ LE ZOOM EST UN RÉGLAGE, PAS UNE CONSTANTE. Par défaut 3 : on sur-échantillonne
//   pour que le bord du verre reste lisse une fois la vignette réduite. Mais quand
//   on filme POUR LE POSER SUR UN VRAI BUREAU à taille réelle, il faut `FILM_ZOOM=1` :
//   l'orbe est alors rendue exactement comme sur le bureau (150 pt, 300 px en rétine),
//   et le fond découpé du bureau est utilisé au pixel près, sans ré-échantillonnage.
const ZOOM = Number(process.env.FILM_ZOOM || 3);
const COTE = 150;

app.setPath('userData', '/private/tmp/claude-orbe-film');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  // ⚠ `show: false` FIGE LES COULEURS. La page saute son interpolation quand
  //   `document.hidden` est vrai — c'est voulu, on ne peint pas pour personne.
  //   Mais en tournage ça donne une orbe grise : la mécanique change, la teinte
  //   jamais. Il faut donc une fenêtre RÉELLEMENT visible pour filmer.
  const w = new BrowserWindow({
    width: COTE * ZOOM, height: COTE * ZOOM, show: true, frame: false, x: 60, y: 120,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false, zoomFactor: ZOOM },
  });
  // ⚠ ON OUVRE LA PAGE SUR UN ÉTAT OCCUPÉ, TOUJOURS. Le pavé de code ne se
  //   peint que si l'orbe travaille (`if (occupe)` dans orbe.html) : ouvrir sur
  //   « repos » le laisse vide, et le garde ci-dessous refuse alors de filmer —
  //   constaté le 20/09 en posant `FILM_PRE=idle` avant le chargement. On amorce
  //   donc en occupé, on contrôle le pavé, ET SEULEMENT APRÈS on pose l'état
  //   d'ouverture voulu. Sans cette amorce explicite, le tournage dépendait de
  //   ce que la session avait laissé dans status.json — vrai par accident.
  cp.execFileSync('python3', [STATUS, 'busy', 'working', 'film']);
  poserFluxFictif();          // AVANT le chargement : la page lit dès sa première passe
  await w.loadFile(PAGE);
  w.webContents.setZoomFactor(ZOOM);
  await new Promise(r => setTimeout(r, 2500));

  await w.webContents.executeJavaScript(`(() => {
    const bg = document.createElement('div');
    bg.style.cssText = 'position:fixed;inset:0;z-index:-1;'
      // ⚠ FOND PLAT, ET EXACTEMENT celui de la page. Un dégradé, même discret,
      //   dessine un CARRÉ visible autour de la démo une fois posée dans le
      //   README : le centre est plus clair que la page, les bords non. Le
      //   raccord se voit, et c'est ce qui fait « bâclé ». #0d1117 = le fond de
      //   GitHub en thème sombre, donc la vignette disparaît dans la page.
      // ⚠ FILM_FOND pose une IMAGE à la place du fond plat. C'est le seul moyen
      //   honnête de filmer le verre au-dessus d'un vrai bureau : le verre est
      //   RÉELLEMENT transparent, il réfracte ce qu'il y a derrière. Composer le
      //   fond après coup donnerait un disque opaque collé sur une photo.
      //   L'image doit être la découpe exacte de la zone où vit la capsule,
      //   à la résolution du tournage (COTE * ZOOM * 2 en rétine).
      + (${JSON.stringify(process.env.FILM_FOND || '')}
          ? 'background:url("file://' + ${JSON.stringify(process.env.FILM_FOND || '')} + '") center/cover no-repeat'
          : 'background:#0d1117');
    document.body.prepend(bg);
    /* ⚠ MÊME PIÈGE QUE planche.cjs, trouvé le 2026-08-04 : monter #scene en
       z-index:1 fait passer le canvas DEVANT le pavé de code et le libellé.
       La vignette publiée jusqu'ici montrait donc une orbe MUETTE — le
       défilement du code, qui est la moitié de l'intérêt, n'y a jamais été
       filmé. Le fond suffit avec son z-index:-1 ; on remonte explicitement
       les deux surcouches. */
    document.getElementById('scene').style.zIndex = '0';
    document.getElementById('pave').style.zIndex = '2';
    document.getElementById('dit').style.zIndex = '2';
    return true; })()`);

  // ⚠ L'ORBE ÉCONOMISE SES IMAGES, ET ÇA SE VOIT AU FILM. Sur le bureau elle
  //   tourne à 12 i/s au repos, 30 au travail, 60 pendant un fondu (CADENCE dans
  //   orbe.html, remise toutes les 200 ms) — un compagnon permanent ne peut pas
  //   payer 60 à vie. Filmée telle quelle, la prise du 20/09 comptait 152 images
  //   identiques à la précédente sur 862 et 226 sauts : « un peu de saccade »,
  //   mot pour mot. On fige donc 60 i/s en rendant `setCadence` muet : le
  //   minuteur de la page continue d'appeler, plus rien ne bouge.
  await w.webContents.executeJavaScript(
    `window.__orbe.setCadence(60); window.__orbe.setCadence = () => {}; true`);

  // ⚠ LE SEUL TÉMOIN QUI COMPTE EST LE TEXTE À L'ÉCRAN. La valeur rendue par
  //   l'injection a été un `NaN` inexplicable pendant trois essais, et pendant ce
  //   temps la vraie question — « qu'est-ce qui est écrit dans le pavé ? » — avait
  //   une réponse simple et directe. On lit les fentes, on cherche du français, on
  //   cherche un mot qu'on vient d'injecter. Ni l'un ni l'autre ne se devine.
  await new Promise(r => setTimeout(r, 1800));    // le rouleau doit avoir défilé
  const lu = await w.webContents.executeJavaScript(
    `[...document.querySelectorAll('#pave .l')].map(e=>e.textContent).join(' ')`);
  if (/[àâçéèêëîïôùûœ]/i.test(lu)) {
    console.error(`⛔ du français dans le pavé : « ${lu.replace(/\s+/g,' ').trim().slice(0, 90)} »`);
    app.exit(5); return;
  }
  if (!/rank|bm25|recall|store|search/i.test(lu)) {
    console.error(`⛔ les lignes du banc ne sont pas à l'écran : « ${lu.replace(/\s+/g,' ').trim().slice(0, 90)} »`);
    app.exit(6); return;
  }
  console.log(`  pavé : en anglais, lignes du banc — « ${lu.replace(/\s+/g,' ').trim().slice(0, 46)}… »`);

  // ⚠ L'ÉTAT D'OUVERTURE SE POSE ICI, PAS AVANT : le pavé vient d'être
  //   contrôlé, on peut maintenant redescendre au repos. Les 2,6 s sont celles
  //   du banc — en dessous, la première image du film est une forme
  //   intermédiaire qui n'existe dans aucun état.
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
    // ⚠ PAS À PAS, SUR UNE HORLOGE VIRTUELLE — c'est le seul tournage qui ne
    //   PEUT PAS saccader. Le screencast ci-dessous filme en temps réel : chaque
    //   reconstruction du pavé au changement d'état (78–85 ms), chaque lecture
    //   du statut toutes les 0,7 s (~28 ms) et chaque hoquet de la machine
    //   deviennent une image manquante, donc un à-coup — mesuré le 20/09 sur la
    //   prise 4 : 26 trous de plus de 25 ms sur 912 images, dont un à chaque
    //   changement d'état, là où l'œil regarde. Ici on GÈLE l'horloge de la page
    //   (Emulation.setVirtualTimePolicy), on l'avance de 16,667 ms, on laisse
    //   la boucle rendre une image, on la capture, et on recommence. Le temps de
    //   capture ne coûte plus rien à l'animation : une image = un soixantième de
    //   seconde de l'orbe, EXACTEMENT, quelle que soit la charge de la machine.
    //   La vitesse au film est donc la vitesse réelle des états (l'auteur, 20/09 :
    //   « la vitesse des animations doit être la vitesse réelle des états »).
    // ⚠ MAIS L'HORLOGE DES ANIMATIONS CSS NE SUIT PAS. Mesuré : sous temps
    //   virtuel, performance.now, Date.now et les minuteurs avancent du budget
    //   demandé ; document.timeline, elle, avance du temps RÉEL écoulé (983 ms
    //   réelles pour 2 000 ms virtuelles). Les trois points qui clignotent sous
    //   le libellé et les fondus d'opacité du pavé et du libellé tourneraient
    //   donc trois fois trop lentement au film. On les prend en main : chaque
    //   animation est mise en pause dès qu'elle apparaît et son curseur avance
    //   du même pas que l'horloge virtuelle.
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
    // Un pas : l'horloge avance, les animations CSS suivent, la boucle de rendu
    // (qui tourne sur le vrai rAF de l'écran) peint une fois avec ce temps-là.
    const pas = async () => {
      const p = expire();
      await dbg.sendCommand('Emulation.setVirtualTimePolicy', { policy: 'advance', budget: PAS });
      await p;
      await w.webContents.executeJavaScript(
        `window.__pas(${PAS}); new Promise(r => requestAnimationFrame(() => r()))`);
    };
    // Le plan, joué image par image. Le changement d'état est lu par la page
    // sur-le-champ (`lire()`), pas au prochain tour de son minuteur de 700 ms :
    // chaque état occupe ainsi exactement le même nombre d'images.
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
    // ⚠ UN TOUR À BLANC AVANT LE TOUR FILMÉ, POUR LE RACCORD DE BOUCLE. Les
    //   couleurs voyagent par lissage (4,5 % par tick à 30 Hz) : trois secondes
    //   après le dernier changement, il reste ~11 % du chemin vers la teinte du
    //   repos. La première image, elle, part d'un repos posé à 100 %. Sur une
    //   boucle, ce raccord teinte-à-teinte se voit. Joué deux fois, le plan
    //   commence exactement dans l'état où il finit.
    if (process.env.FILM_BLANC) await jouer(false);
    // ⚠ LA VITESSE AU FILM DOIT ÊTRE LA VITESSE RÉELLE DE L'ORBE (l'auteur, 20/09).
    //   Elle se prouve sur l'horloge de l'animation elle-même : `uTime` est le
    //   temps que le shader a vu passer. S'il avance d'autant de secondes que le
    //   film en dure, l'orbe tourne à sa vitesse — ni ralenti ni accéléré. On ne
    //   se fie pas au fait que « le temps virtuel a l'air de marcher ».
    const horloge = () => w.webContents.executeJavaScript('window.__orbe._u.uTime.value');
    const tA = await horloge();
    await jouer(true);
    const tB = await horloge();
    const duFilm = images.length / 60, deLOrbe = tB - tA;
    console.log(`  vitesse : ${deLOrbe.toFixed(3)} s d'animation pour ${duFilm.toFixed(3)} s de film ` +
                `(écart ${((deLOrbe / duFilm - 1) * 100).toFixed(2)} %)`);
    if (Math.abs(deLOrbe / duFilm - 1) > 0.02) {
      console.error(`⛔ l'orbe n'avance pas à sa vitesse réelle — le film serait ${deLOrbe < duFilm ? 'ralenti' : 'accéléré'}.`);
      app.exit(7); return;
    }
    await dbg.sendCommand('Emulation.setVirtualTimePolicy', { policy: 'advance', budget: 1e9 });
  } else {
  // Le screencast : on attache le débogueur, on écoute, on acquitte chaque image.
  // Sans l'acquittement, Chromium cesse d'en envoyer au bout de quelques-unes.
  dbg.on('message', (_e, methode, params) => {
    if (methode !== 'Page.screencastFrame') return;
    // L'horodatage vient du compositeur : c'est lui qui dit QUAND l'image a
    // existé. Sans lui, on attribue une cadence constante à des images qui ne
    // le sont pas, et le film accélère ou freine au gré des trous de capture.
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
  // Liste pour le démultiplexeur `concat` de ffmpeg : chaque image porte sa
  // vraie durée, et `fps=60` recale ensuite sur une cadence constante.
  const liste = [];
  images.forEach((img, i) => {
    const nom = String(i).padStart(4, '0') + '.png';
    fs.writeFileSync(path.join(OUT, nom), Buffer.from(img.d, 'base64'));
    const suiv = images[i + 1];
    const duree = suiv ? Math.max(0.001, suiv.t - img.t) : 1 / 60;
    liste.push(`file '${nom}'`, `duration ${duree.toFixed(5)}`);
  });
  liste.push(`file '${String(images.length - 1).padStart(4, '0')}.png'`);   // concat : la dernière se répète
  fs.writeFileSync(path.join(OUT, 'liste.txt'), liste.join('\n') + '\n');
  // Régularité de la prise : le seul chiffre qui prédit la saccade.
  const dts = images.slice(1).map((img, i) => (img.t - images[i].t) * 1000);
  const trous = dts.filter(x => x > 25).length;
  const doublons = images.slice(1).filter((img, i) => img.d === images[i].d).length;
  console.log(`  intervalles : médiane ${dts.sort((a, b) => a - b)[dts.length >> 1].toFixed(1)} ms, ` +
              `max ${Math.max(...dts).toFixed(1)} ms, trous > 25 ms : ${trous}, images en double : ${doublons}`);
  fs.rmSync(FLUX_FAUX, { force: true });
  if (process.env.FILM_PAS) {
    console.log(`${images.length} images pas à pas = ${(images.length / 60).toFixed(2)} s d'orbe à 60 i/s exact ` +
                `(tournées en ${secondes.toFixed(1)} s réelles), dans ${OUT}`);
  } else {
    const ips = Math.round(images.length / secondes);
    console.log(`${images.length} images en ${secondes.toFixed(1)} s → ${ips} i/s, ${COTE * ZOOM}px, dans ${OUT}`);
    // Un film de 20 i/s à côté d'une carte à 45 se voit tout de suite : on refuse.
    if (ips < 35) console.error(`⛔ ${ips} i/s — trop lent. La fenêtre est-elle vraiment visible ?`);
  }
  app.quit();
});
app.on('window-all-closed', () => app.quit());
