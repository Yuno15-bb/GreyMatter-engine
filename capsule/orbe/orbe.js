// The orb renders living material with ten mechanics. Mechanics and speed
// convey the activity; colour conveys the family of work. State meaning lives
// in palettes.js. Keep frame rate low at rest and high for visible motion.
import * as THREE from './vendor/three.module.js';

export { MECANIQUES } from './mecaniques.js';

export const PHYSIQUES = [
  { id: 0,  nom: 'Swell',       desc: 'a single scale, slow and round' },
  { id: 1,  nom: 'Sweep',       desc: 'bands crossing over, sonar-like' },
  { id: 2,  nom: 'Plates',      desc: 'crisp steps that slide' },
  { id: 3,  nom: 'Boil',        desc: 'three octaves, sharp crests' },
  { id: 4,  nom: 'Shockwave',   desc: 'a front leaves the pole and travels' },
  { id: 5,  nom: 'Cells',       desc: 'bubbles pushing each other, soap-like' },
  { id: 6,  nom: 'Vortex',      desc: 'the material turns on itself' },
  { id: 7,  nom: 'Breath',      desc: 'no noise at all, the sphere swells and hollows' },
  { id: 8,  nom: 'Interference',desc: 'two crossed wave trains' },
  { id: 9,  nom: 'Shards',      desc: 'rare hard needles on a smooth surface' },
];

const CHAMP = `
float champUn(vec3 p, float uMode){
  float t = uPhase;
  float F = uFreq;

  vec3 flux = vec3(0.0, -t*0.55, 0.0);
  if(uMode<0.5){
    return snoise(p*F*0.55 + flux)*0.9;
  }
  if(uMode<1.5){
    float onde = sin(p.y*F*5.0 + t*3.2);
    return onde*0.72 + snoise(p*F*1.1 + flux)*0.28;
  }
  if(uMode<2.5){
    float n = snoise(p*F*0.9 + flux);
    return mix(floor(n*4.0)/4.0, n, 0.25);
  }
  if(uMode<3.5){
    return abs(snoise(p*F     + flux))*0.55
         + abs(snoise(p*F*2.7 + flux*1.3))*0.30
         + abs(snoise(p*F*5.3 + flux*2.1))*0.15 - 0.45;
  }
  if(uMode<4.5){
    float d = acos(clamp(p.y,-1.0,1.0))/3.14159;
    float front = fract(t*0.30);
    return exp(-pow((d-front)*18.0, 2.0))*1.2 - 0.15;
  }
  if(uMode<5.5){
    float mind = 1e9;
    for(int i=0;i<6;i++){
      float fi = float(i);
      vec3 g = normalize(vec3(sin(fi*2.1+t*0.7), cos(fi*1.7+t*0.5), sin(fi*3.3+t*0.6)));
      mind = min(mind, distance(p, g));
    }
    return (0.9 - mind*0.9)*1.4;
  }
  if(uMode<6.5){
    float a = p.y*1.9 + t*0.55;
    float c = cos(a), s = sin(a);
    vec3 q = vec3(p.x*c - p.z*s, p.y, p.x*s + p.z*c);
    return snoise(q*F*0.95 + flux*0.7)*0.95;
  }
  if(uMode<7.5){
    return sin(t*1.6)*0.55 + sin(p.y*1.8 + t*0.9)*0.35;
  }
  if(uMode<8.5){
    float a = sin(p.x*F*4.5 + t*2.0);
    float b = sin(p.z*F*4.5 + t*1.6);
    float c = sin(p.y*F*3.0 + t*2.4);
    return (a*b + c*0.5)*0.7;
  }
  float n = snoise(p*F*0.95 + flux*1.8);
  float pic = pow(max(n,0.0), 3.0);
  float fond = snoise(p*F*0.5 + flux)*0.30;
  return pic*1.5 + fond - 0.16;
}

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
    uVerre:{value:couleurs.verre != null ? couleurs.verre : 1.0},
    uC1:{value:new THREE.Color(couleurs.c1)}, uC2:{value:new THREE.Color(couleurs.c2)},
    uC3:{value:new THREE.Color(couleurs.c3)}, uRim:{value:new THREE.Color(couleurs.rim)},
  };

  const core = new THREE.Mesh(
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

          const float BRILLANCE = 0.26;
          const float REFLET    = 0.34;
          const float COEUR     = 0.78;
          const float BORD      = 0.30;

          float ep=pow(1.0-d,1.55);
          ep=clamp(ep+smoothstep(0.10,-0.75,vDisp)*0.16,0.0,1.0);
          ep=clamp(ep*(0.90+0.26*smoothstep(-0.9,0.9,vDisp)),0.0,1.0);

          vec3 teinte=mix(uC3*0.60,uC2*1.30,clamp(ep*1.30,0.0,1.0));

          vec3 R=reflect(-V,N);
          float ciel=smoothstep(-0.10,0.30,R.y);
          vec3 env=mix(vec3(0.05,0.06,0.09),vec3(0.52,0.57,0.66),ciel);
          float fres=(0.04+0.62*pow(1.0-d,4.0))*REFLET;

          vec3 H=normalize(L+V);
          float dur  =pow(max(dot(N,H),0.0), 80.0)*uSweep*BRILLANCE;
          float large=pow(max(dot(N,H),0.0), 10.0)*uSweep*BRILLANCE;

          float tranche=smoothstep(0.90,0.999,1.0-d);
          vec3 verre=teinte + env*fres + uRim*f*0.42
                     + (uRim*0.55+vec3(0.10))*tranche*0.45
                     + vec3(large)*0.10 + vec3(dur)*0.45;
          float a=clamp(COEUR + BORD*ep + dur*0.45 + large*0.06
                        + tranche*0.22,0.0,1.0);

          gl_FragColor=vec4(mix(plein,verre,uVerre), mix(1.0,a,uVerre)); }`,
    }));
  scene.add(core);

  const fit=()=>{ const el=canvas.parentElement; const s=Math.min(el.clientWidth, el.clientHeight);
    if(s>0){ renderer.setSize(s,s,false); } };
  fit(); new ResizeObserver(fit).observe(canvas.parentElement);

  let api;
  let t=0;
  let fpsCourant = 60, dernierT = performance.now();
  // Tempo changes the orb's simulated time independently of drawing cadence.
  // One frame per second at normal tempo would jump visibly at rest.
  let tempo = 1;
  const TRAME = 1000 / 60;
  let dernierRendu = 0;
  const boucle=()=>{
    const now = performance.now();
    // Above 10 fps, follow rAF and draw on evenly spaced display frames.
    // A timer followed by rAF alternates short and long intervals near 30 fps.
    if (fpsCourant >= 10) {
      requestAnimationFrame(boucle);
      if (fpsCourant < 55 && now - dernierRendu < 1000/fpsCourant - TRAME/2) return;
    } else setTimeout(()=>requestAnimationFrame(boucle),
                      Math.max(0, 1000/fpsCourant - TRAME));
    dernierRendu = now;
    globalThis.__imagesOrbe = (globalThis.__imagesOrbe || 0) + 1;
    const plafond = Math.max(0.05, 3 / Math.max(1, fpsCourant));
    const dt = tempo * Math.min(plafond, (now-dernierT)/1000); dernierT = now;
    t += dt; U.uTime.value=t;
    U.uPhase.value += dt * U.uSpeed.value;
    if(api&&api._maj) api._maj();
    if(api&&api.surImage) api.surImage(dt);
    core.rotation.y+=dt*0.24; core.rotation.x+=dt*0.09;
    renderer.render(scene,camera); };
  const MIX_MS = 1400;
  let mixT0 = 0, enTransition = false;
  const majMix = () => {
    if(!enTransition) return;
    const k = Math.min(1, (performance.now()-mixT0)/MIX_MS);
    U.uMix.value = k<0.5 ? 4*k*k*k : 1-Math.pow(-2*k+2,3)/2;
    if(k>=1){ U.uModeA.value=U.uModeB.value; U.uMix.value=0; enTransition=false; }
  };
  api = {
    setDisp:(v)=>{ U.uDisp.value=v; }, setSpeed:(v)=>{ U.uSpeed.value=v; },

    setMecanique:(m)=>{
      if(m===U.uModeB.value) return;
      if(enTransition){ U.uModeA.value = U.uModeB.value; }
      U.uModeB.value = m; U.uMix.value = 0;
      mixT0 = performance.now(); enTransition = true;
    },
    setCadence:(f)=>{ fpsCourant = f; },
    setTempo:(k)=>{ tempo = k; },

    setVerre:(v)=>{ U.uVerre.value = Math.max(0, Math.min(1, v)); },
    enTransition:()=>enTransition,
    _maj: majMix, _u: U,
  };
  boucle();
  return api;
}
