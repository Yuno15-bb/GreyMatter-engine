// ORBE — une matière vivante qui dit ce qu'un système est en train de faire.
//
// Dérivé du moteur de VoiceShell (Three.js + bruit simplex 3D + Fresnel), puis
// étendu pour porter DIX MÉCANIQUES DE FLUIDE distinctes et FONDRE de l'une à
// l'autre sans rupture.
//
// L'idée : deux canaux séparés.
//   · la MÉCANIQUE et la vitesse disent la NATURE et l'INTENSITÉ de l'activité,
//     et se lisent SANS couleur ;
//   · la COULEUR dit la FAMILLE de travail.
//
// Ce fichier ne connaît aucun projet : il rend un orbe et expose son pilotage.
// Le sens à donner aux états vit dans `palettes.js`.
//
// USAGE
//   import { creerOrbe } from './orbe.js';
//   const orbe = creerOrbe(canvas, MECANIQUES.houle, snoiseSrc, reglageInitial);
//   orbe.setMecanique(MECANIQUES.vortex);   // fondu de 1,4 s
//   orbe.setCadence(8);                     // i/s — voir la note sur le coût
//
// ⚠ COÛT, MESURÉ (orbe de 140 px, macOS, fenêtre transparente au-dessus) :
//   60 i/s → ~12 %   ·   20 i/s → ~8,7 %   ·   12 i/s → ~5,4 %   ·   2 i/s → 0,6 %
// Le coût suit la CADENCE, presque pas le nombre de triangles (detail 12 et 96
// donnent le même pourcentage). Pour un compagnon permanent : cadence basse au
// repos, haute pendant les transitions et le travail.
import * as THREE from './vendor/three.module.js';

// Les constantes vivent dans `mecaniques.js` — un module SANS Three.js, pour
// que `palettes.js` (les couleurs) n'ait pas à charger le moteur 3D pour dix
// nombres. Réexportées ici : les appelants historiques ne changent pas.
export { MECANIQUES } from './mecaniques.js';

export const PHYSIQUES = [
  { id: 0,  nom: 'Houle',        desc: 'une seule échelle, lente et ronde' },
  { id: 1,  nom: 'Balayage',     desc: 'bandes qui traversent, comme un sonar' },
  { id: 2,  nom: 'Plaques',      desc: 'paliers nets qui glissent' },
  { id: 3,  nom: 'Ébullition',   desc: 'trois octaves, crêtes vives' },
  { id: 4,  nom: 'Onde de choc', desc: 'un front part du pôle et traverse' },
  { id: 5,  nom: 'Cellules',     desc: 'bulles qui se poussent, façon savon' },
  { id: 6,  nom: 'Vortex',       desc: 'la matière tourne sur elle-même' },
  { id: 7,  nom: 'Respiration',  desc: 'aucun bruit, la sphère enfle et se creuse' },
  { id: 8,  nom: 'Interférence', desc: 'deux trains d’ondes croisés' },
  { id: 9,  nom: 'Éclats',       desc: 'aiguilles rares et dures sur surface lisse' },
];

const CHAMP = `
float champUn(vec3 p, float uMode){
  // ⚠ LA PHASE EST ACCUMULÉE CÔTÉ JS, pas calculée ici.
  // Avant : t = uTime*uSpeed. Comme uTime grandit sans fin, la moindre
  // variation de vitesse faisait SAUTER la phase (uTime=50, vitesse
  // 0,45 -> 0,75 : la phase bondit de 22 à 37). D'où l'accélération frénétique
  // en changeant d'agent dans une même famille. Maintenant la vitesse ne
  // change que la CADENCE d'avancement, jamais la position dans le cycle.
  float t = uPhase;
  float F = uFreq;

  // ⚠ TOUTES LES MÉCANIQUES PARTAGENT LE MÊME SENS : la matière descend du
  // pôle nord vers le sud (terme -t sur p.y) et tourne dans le sens horaire
  // autour de Y. Sans ça, chaque famille avait sa direction propre et le
  // passage de l'une à l'autre ressemblait à un changement de sujet, pas à une
  // même matière qui change d'humeur.
  vec3 flux = vec3(0.0, -t*0.55, 0.0);        // le courant commun
  if(uMode<0.5){                                   // 0 — HOULE
    return snoise(p*F*0.55 + flux)*0.9;
  }
  if(uMode<1.5){                                   // 1 — BALAYAGE
    float onde = sin(p.y*F*5.0 + t*3.2);      // + t : le front DESCEND
    return onde*0.72 + snoise(p*F*1.1 + flux)*0.28;
  }
  if(uMode<2.5){                                   // 2 — PLAQUES
    float n = snoise(p*F*0.9 + flux);
    return mix(floor(n*4.0)/4.0, n, 0.25);
  }
  if(uMode<3.5){                                   // 3 — ÉBULLITION
    return abs(snoise(p*F     + flux))*0.55
         + abs(snoise(p*F*2.7 + flux*1.3))*0.30
         + abs(snoise(p*F*5.3 + flux*2.1))*0.15 - 0.45;
  }
  if(uMode<4.5){                                   // 4 — ONDE DE CHOC
    float d = acos(clamp(p.y,-1.0,1.0))/3.14159;
    float front = fract(t*0.30);
    return exp(-pow((d-front)*18.0, 2.0))*1.2 - 0.15;
  }
  if(uMode<5.5){                                   // 5 — CELLULES
    // Approche « worley » bon marché : on cherche la plus courte distance à
    // quelques germes qui dérivent. Donne des bulles qui se poussent.
    float mind = 1e9;
    for(int i=0;i<6;i++){
      float fi = float(i);
      vec3 g = normalize(vec3(sin(fi*2.1+t*0.7), cos(fi*1.7+t*0.5), sin(fi*3.3+t*0.6)));
      mind = min(mind, distance(p, g));
    }
    return (0.9 - mind*0.9)*1.4;
  }
  if(uMode<6.5){                                   // 6 — VORTEX
    // On tord les coordonnées autour de l'axe Y avant d'échantillonner :
    // la matière semble tourner sur elle-même, pas se déplacer.
    // torsion RALENTIE (1,2 -> 0,55) : à pleine vitesse la spirale tournait si
    // vite que le motif crénelait. On garde le geste, on enlève le vrombissement.
    float a = p.y*1.9 + t*0.55;                // rotation horaire, comme le reste
    float c = cos(a), s = sin(a);
    vec3 q = vec3(p.x*c - p.z*s, p.y, p.x*s + p.z*c);
    return snoise(q*F*0.95 + flux*0.7)*0.95;   // motifs plus larges
  }
  if(uMode<7.5){                                   // 7 — RESPIRATION
    // Zéro bruit : une pulsation pure, plus deux lobes très lents.
    return sin(t*1.6)*0.55 + sin(p.y*1.8 + t*0.9)*0.35;
  }
  if(uMode<8.5){                                   // 8 — INTERFÉRENCE
    // les trois trains descendent ensemble : même sens que les autres familles
    float a = sin(p.x*F*4.5 + t*2.0);
    float b = sin(p.z*F*4.5 + t*1.6);
    float c = sin(p.y*F*3.0 + t*2.4);
    return (a*b + c*0.5)*0.7;
  }
                                                   // 9 — ÉCLATS
  // Bruit élevé à une puissance : les creux s'aplatissent, les crêtes
  // survivent → la surface se DURCIT par endroits.
  // ⚠ Exposant 6 et gain 3,2 au départ : le champ valait zéro partout sauf sur
  // quelques aiguilles très hautes. À mi-fondu on voyait donc des pointes
  // SURGIR d'une sphère lisse, au lieu d'une matière qui se cristallise — c'est
  // la transition que l'utilisateur a rejetée. Exposant 3,2 et une base continue sous
  // les pointes : il reste du relief partout, le fondu a de quoi s'accrocher.
  // ⚠ Les pointes DOIVENT VOYAGER, pas clignoter sur place. Avec une fréquence
  // élevée elles apparaissaient et disparaissaient au même endroit — un
  // scintillement, pas un mouvement. Fréquence abaissée (1,6 -> 0,95) et
  // courant renforcé : les éclats naissent en haut et descendent avec le reste.
  float n = snoise(p*F*0.95 + flux*1.8);
  float pic = pow(max(n,0.0), 3.0);
  // une respiration lente sous les pointes : la matière vit entre deux éclats
  float fond = snoise(p*F*0.5 + flux)*0.30;
  return pic*1.5 + fond - 0.16;
}

// ── LA TRANSITION ENTRE DEUX PHYSIQUES ──────────────────────────────────
// On ne BASCULE pas d'une mécanique à l'autre : on calcule les DEUX champs et
// on les fond. Une bascule sèche se voit — la matière change de nature d'une
// image à l'autre, et ça se lit comme un défaut d'affichage.
// Le second champ n'est calculé que PENDANT le fondu : hors transition,
// 'uMix' vaut 0 et le coût est celui d'une seule mécanique.
float champ(vec3 p){
  float f = champUn(p, uModeA);
  if(uMix > 0.001) f = mix(f, champUn(p, uModeB), uMix);
  return f;
}`;

export function creerOrbe(canvas, mode, snoiseSrc, couleurs) {
  const lerp = (a,b,t)=>a+(b-a)*t;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias:true, alpha:true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1, 2));
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.z = 4.6;

  const U = {
    uTime:{value:0}, uPhase:{value:0}, uDisp:{value:couleurs.disp}, uFreq:{value:couleurs.freq},
    uSpeed:{value:couleurs.speed}, uRimI:{value:couleurs.rimI},
    uModeA:{value:mode}, uModeB:{value:mode}, uMix:{value:0},
    uSweep:{value:1.0},
    // Verre par défaut. `setVerre(0)` rend la matière pleine d'origine.
    uVerre:{value:couleurs.verre != null ? couleurs.verre : 1.0},
    uC1:{value:new THREE.Color(couleurs.c1)}, uC2:{value:new THREE.Color(couleurs.c2)},
    uC3:{value:new THREE.Color(couleurs.c3)}, uRim:{value:new THREE.Color(couleurs.rim)},
  };

  const core = new THREE.Mesh(
    // ⚠ 40 -> 88. Ce n'est PAS une question de cadence : mesuré, la transition
    // tient 60 i/s sans perdre une image. C'est du CRÉNELAGE — le relief est
    // échantillonné aux SOMMETS, et un motif fin qui tourne vite saute d'un
    // sommet à l'autre. L'œil lit ça comme une saccade alors que rien ne
    // ralentit. Mesuré par ailleurs : le coût ne dépend quasiment pas du nombre
    // de triangles (detail 12 et 96 donnaient le même %), il est ailleurs.
    new THREE.IcosahedronGeometry(1, 88),
    new THREE.ShaderMaterial({ uniforms:U, transparent:true,
      vertexShader:`uniform float uTime,uPhase,uDisp,uFreq,uSpeed,uModeA,uModeB,uMix;
        varying vec3 vNormal,vView; varying float vDisp; ${snoiseSrc} ${CHAMP}
        vec3 deplace(vec3 sp){ return sp + sp*champ(sp)*uDisp; }
        void main(){
          vec3 sp=normalize(position);
          vec3 T=normalize(cross(sp, abs(sp.y)<0.99?vec3(0.0,1.0,0.0):vec3(1.0,0.0,0.0)));
          vec3 Bn=cross(sp,T); float e=0.012;
          vec3 p0=deplace(sp), p1=deplace(normalize(sp+T*e)), p2=deplace(normalize(sp+Bn*e));
          vec3 n=normalize(cross(p1-p0,p2-p0)); if(dot(n,sp)<0.0) n=-n;
          vDisp=champ(sp);
          vec4 mv=modelViewMatrix*vec4(p0,1.0);
          vNormal=normalize(normalMatrix*n); vView=normalize(-mv.xyz);
          gl_Position=projectionMatrix*mv; }`,
      // ── LE VERRE ────────────────────────────────────────────────────────────
      // `uVerre` = 0 rend exactement la matière pleine d'origine, 1 le verre.
      // Un interrupteur plutôt qu'une réécriture : la forme et les couleurs sont
      // le fruit de plusieurs passes de réglage, et un verre raté ne doit pas
      // les emporter avec lui. Comparer les deux rendus reste possible.
      //
      // ⚠ IL N'Y A PAS DE FOND À RÉFRACTER. La fenêtre est transparente et
      //   WebGL ne voit pas le bureau derrière : impossible de le déformer comme
      //   le ferait un vrai verre. Ce qui fait lire « verre » ici, ce sont donc
      //   les trois signaux qu'on peut produire sans fond :
      //     · l'ÉPAISSEUR — le bord vu en biais traverse plus de matière, donc
      //       il est dense ; le centre, vu de face, est presque vide ;
      //     · la LUMIÈRE PIÉGÉE — une lueur interne, teintée de la couleur du
      //       corps, qui se concentre là où la matière est épaisse ;
      //     · le REFLET — il reste opaque. Un reflet translucide se lit comme
      //       une tache de peinture, pas comme une surface.
      fragmentShader:`uniform vec3 uC1,uC2,uC3,uRim; uniform float uRimI,uTime,uSweep,uVerre;
        varying vec3 vNormal,vView; varying float vDisp;
        void main(){
          vec3 N=normalize(vNormal), V=normalize(vView);
          float d=clamp(dot(N,V),0.0,1.0);
          float f=pow(1.0-d,2.4)*uRimI;
          vec3 base=mix(uC3,uC2,smoothstep(-0.6,0.9,vDisp));
          base=mix(base,uC1,pow(d,3.0)*0.75);
          vec3 L=normalize(vec3(0.6,0.8,0.7));
          float spec=pow(max(dot(reflect(-L,N),V),0.0),34.0)*uSweep;
          vec3 plein=base + uRim*f*0.85 + vec3(spec)*0.55;

          // ── LE VERRE, DEUXIÈME MODÈLE (2026-08-04) ────────────────────────
          // Le premier posait une opacité PLANCHER de 0,42 sur tout le corps et
          // gardait 'base' — donc le creux sombre 'uC3' — au centre. Résultat vu
          // sur planche : une pâte translucide tachée de sombre, et rien à voir
          // au travers. Deux changements de principe :
          //   · la couleur ne RECOUVRE plus, elle s'ACCUMULE avec l'épaisseur
          //     traversée (Beer-Lambert) — le cœur est presque vide, le bord
          //     porte la teinte. C'est ce qui permet d'être franchement
          //     transparent SANS perdre le canal « qui » : la famille se lit
          //     désormais sur la tranche, pas sur la surface pleine ;
          //   · le relief ne se dit plus par des taches sombres mais par la
          //     LUMIÈRE qui glisse dessus (horizon réfléchi + deux spéculaires).
          // ── DOSAGES DE MATIÈRE (2026-08-08) ──────────────────────────────
          // Demande de l'auteur, mot à mot : « les bordures sont transparentes,
          // j'aimerais que ce le soit moins et plus organique, moins brillant,
          // moins de reflets, qu'on voit mieux le milieu et le texte qui
          // défile ». Quatre curseurs NOMMÉS plutôt qu'une réécriture : le
          // réglage se refait en changeant quatre nombres, et le modèle de
          // verre de la version précédente reste lisible dessous.
          // ⚠ Ceci REVIENT EN PARTIE sur la note du 2026-08-04 qui rejetait
          //   « la pâte translucide tachée de sombre » et son opacité plancher
          //   de 0,42. La raison de ce rejet tenait : un cœur sombre OPAQUE
          //   cachait le fond ET n'avait rien à montrer. Ce n'est plus le cas —
          //   le pavé de code vit au centre depuis, et un cœur presque vide le
          //   laisse tomber directement sur le bureau, où il devient illisible.
          //   Le cœur porte donc à nouveau de la matière, mais SOMBRE et
          //   modérée : elle sert de fond au texte vert, elle ne le recouvre pas.
          const float BRILLANCE = 0.26;   // 1.0 = le verre poli d'avant
          const float REFLET    = 0.34;   // part d'environnement réfléchi
          const float COEUR     = 0.78;   // alpha au centre — porte le texte
          const float BORD      = 0.30;   // ce que l'épaisseur ajoute par-dessus

          float ep=pow(1.0-d,1.55);
          // Le relief garde sa part d'épaisseur — sinon la mécanique, seul canal
          // lisible sans couleur, disparaît sous la transparence.
          ep=clamp(ep+smoothstep(0.10,-0.75,vDisp)*0.16,0.0,1.0);
          // ⚠ ORGANIQUE = LE BORD SUIT LE RELIEF. Le liseré net d'avant dessinait
          //   le même cercle quelle que soit la matière dessous : ça se lit comme
          //   un contour d'interface posé sur l'objet. En modulant l'épaisseur
          //   par le champ, la densité du bord ondule avec la mécanique.
          ep=clamp(ep*(0.90+0.26*smoothstep(-0.9,0.9,vDisp)),0.0,1.0);

          // TEINTE : le creux sombre revient AU CENTRE (fond du texte), la
          // couleur de famille reste portée par l'épaisseur du bord.
          vec3 teinte=mix(uC3*0.60,uC2*1.30,clamp(ep*1.30,0.0,1.0));

          // ⚠ IL N'Y A PAS DE FOND À RÉFLÉCHIR (fenêtre transparente, WebGL ne
          //   voit pas le bureau). On en FABRIQUE un : ciel clair en haut, sol
          //   sombre en bas, horizon net. C'est cette LIGNE d'horizon qui fait
          //   lire « surface polie » — elle glisse sur le relief quand la
          //   matière bouge, là où un simple point spéculaire reste collé.
          vec3 R=reflect(-V,N);
          float ciel=smoothstep(-0.10,0.30,R.y);
          // Ciel ASSOURDI (0,88→0,52) : à pleine clarté, l'horizon réfléchi
          // repeignait la moitié haute de l'objet en blanc laiteux et mangeait
          // le texte par transparence.
          vec3 env=mix(vec3(0.05,0.06,0.09),vec3(0.52,0.57,0.66),ciel);
          // ⚠ LA LUCARNE EST RETIRÉE — c'était le carré de lumière au zénith,
          //   le signal le plus « bille de verre sous un spot » de tout le
          //   rendu, et le premier que l'auteur désigne en disant « trop de reflet ».
          // Fresnel : un verre ne réfléchit presque rien de face, tout en biais.
          float fres=(0.04+0.62*pow(1.0-d,4.0))*REFLET;

          // DEUX SPÉCULAIRES, pas un. Le dur donne le point de lumière qui dit
          // « poli » ; le large donne le vernis sur toute la face éclairée. Un
          // seul lobe étroit se lit comme du plastique.
          // ⚠ Exposants ABAISSÉS en même temps que les gains : un lobe très
          //   étroit (200) très atténué reste un point dur qui accroche l'œil.
          //   Élargi et affaibli, il devient un lustre de matière mate.
          vec3 H=normalize(L+V);
          float dur  =pow(max(dot(N,H),0.0), 80.0)*uSweep*BRILLANCE;
          float large=pow(max(dot(N,H),0.0), 10.0)*uSweep*BRILLANCE;

          // LA TRANCHE — un liseré FIN sur les tout derniers degrés avant la
          // silhouette. Sans lui le bord s'éteint en dégradé mou et l'objet a
          // l'air flou ; avec, il a une arête, comme un bord de verre poli.
          // ⚠ Il doit rester dans les 0,03 dernier de 'd' : plus large, il se
          //   lit comme un contour d'interface, pas comme une épaisseur.
          // ⚠ Le liseré est désormais TEINTÉ (uRim domine, le blanc ne fait plus
          //   qu'un appoint) : un liseré blanc sur les 360° du contour, c'est
          //   exactement ce qui donnait l'arête de verre taillé.
          float tranche=smoothstep(0.90,0.999,1.0-d);
          vec3 verre=teinte + env*fres + uRim*f*0.42
                     + (uRim*0.55+vec3(0.10))*tranche*0.45
                     + vec3(large)*0.10 + vec3(dur)*0.45;
          // L'ALPHA : le cœur n'est plus vide (COEUR), l'épaisseur du bord
          // achève de le rendre franchement matiéré (BORD). Les reflets ne
          // poussent presque plus l'opacité — ils ne doivent plus faire le
          // volume à la place de la matière.
          float a=clamp(COEUR + BORD*ep + dur*0.45 + large*0.06
                        + tranche*0.22,0.0,1.0);

          gl_FragColor=vec4(mix(plein,verre,uVerre), mix(1.0,a,uVerre)); }`,
    }));
  scene.add(core);

  const fit=()=>{ const el=canvas.parentElement; const s=Math.min(el.clientWidth, el.clientHeight);
    if(s>0){ renderer.setSize(s,s,false); } };
  fit(); new ResizeObserver(fit).observe(canvas.parentElement);

  let api;                       // rempli plus bas ; la boucle le teste
  let t=0;
  // ── CADENCE ADAPTATIVE ────────────────────────────────────────────────────
  // Le fondu de mécanique DOIT être à 60 i/s : à 24 il avance par crans, et on
  // lit une saccade là où on voulait de la fluidité. Mais tenir 60 en
  // permanence coûte cher (mesuré : ~12 % pour un orbe de 140 px).
  // On monte donc à 60 pendant la transition et quand ça travaille, on
  // redescend au repos. La fluidité est payée là où elle se voit.
  let fpsCourant = 60, dernierT = performance.now();
  // ⚠ `setTimeout(1000/fps)` PUIS `rAF` ADDITIONNE LES DEUX ATTENTES.
  //   Le minuteur attend l'intervalle voulu, puis rAF attend encore le prochain
  //   rafraîchissement de l'écran (~16,7 ms). On demandait 60 i/s et on en
  //   obtenait 32 ; 30 demandés donnaient 22. MESURÉ, pas supposé — et c'est
  //   exactement ce qui faisait avancer les fondus « par crans » alors que le
  //   code disait 60. Deux corrections :
  //     · au-delà de ~55 i/s on ne veut RIEN attendre : rAF seul, cadence écran ;
  //     · en dessous, on retire une image d'écran du délai, puisque rAF la
  //       rajoutera de toute façon.
  const TRAME = 1000 / 60;
  const boucle=()=>{
    if (fpsCourant >= 55) requestAnimationFrame(boucle);
    else setTimeout(()=>requestAnimationFrame(boucle),
                    Math.max(0, 1000/fpsCourant - TRAME));
    const now = performance.now();
    // ⚠ CE PLAFOND ÉTAIT UN FREIN CACHÉ. Il existe pour qu'un long gel (onglet
    //   masqué, machine en veille) ne fasse pas SAUTER l'animation au réveil.
    //   Mais 0,05 s = 3 images à 60 i/s… et 1/5 d'image à 4 i/s. Au repos, où
    //   l'orbe tourne justement à 4 i/s, CHAQUE image était donc tronquée : le
    //   temps avançait cinq fois moins vite que la réalité, et l'orbe paraissait
    //   presque immobile. Personne ne pouvait le voir — rien n'est en retard,
    //   rien ne saute, tout est simplement au ralenti.
    //   Le plafond doit se mesurer en IMAGES, pas en secondes absolues.
    const plafond = Math.max(0.05, 3 / Math.max(1, fpsCourant));
    const dt = Math.min(plafond, (now-dernierT)/1000); dernierT = now;
    // ⚠ le temps avance en SECONDES RÉELLES, pas en «1/FPS» : sinon changer de
    // cadence change aussi la vitesse apparente du fluide.
    t += dt; U.uTime.value=t;
    // la phase avance à la vitesse COURANTE : accélérer ne téléporte plus rien
    U.uPhase.value += dt * U.uSpeed.value;
    if(api&&api._maj) api._maj();
    // ce que la page veut mettre à jour DANS la même image (sinon une image de plus)
    if(api&&api.surImage) api.surImage(dt);
    core.rotation.y+=dt*0.24; core.rotation.x+=dt*0.09;
    renderer.render(scene,camera); };
  // Pilotage de la transition, côté JS. `uMix` avance à cadence fixe et, une
  // fois arrivé, la cible devient la source : on n'accumule jamais de fondus.
  const MIX_MS = 1400;                     // durée du morphing de mécanique
  let mixT0 = 0, enTransition = false;
  const majMix = () => {
    if(!enTransition) return;
    const k = Math.min(1, (performance.now()-mixT0)/MIX_MS);
    // adoucissement aux deux bouts : ni départ ni arrivée brusques
    U.uMix.value = k<0.5 ? 4*k*k*k : 1-Math.pow(-2*k+2,3)/2;
    if(k>=1){ U.uModeA.value=U.uModeB.value; U.uMix.value=0; enTransition=false; }
  };
  api = {
    setDisp:(v)=>{ U.uDisp.value=v; }, setSpeed:(v)=>{ U.uSpeed.value=v; },
    /* On ne coupe JAMAIS un fondu en cours : si une transition est déjà en
       route, on fige l'état courant comme nouvelle source avant de repartir.
       Sans ça, deux changements rapprochés font sauter la matière — le défaut
       qu'on cherchait justement à supprimer. */
    setMecanique:(m)=>{
      if(m===U.uModeB.value) return;
      if(enTransition){ U.uModeA.value = U.uModeB.value; }
      U.uModeB.value = m; U.uMix.value = 0;
      mixT0 = performance.now(); enTransition = true;
    },
    setCadence:(f)=>{ fpsCourant = f; },
    /* 1 = verre, 0 = matière pleine d'origine. Interrupteur, pas réécriture. */
    setVerre:(v)=>{ U.uVerre.value = Math.max(0, Math.min(1, v)); },
    enTransition:()=>enTransition,
    _maj: majMix, _u: U,
  };
  boucle();
  return api;
}
