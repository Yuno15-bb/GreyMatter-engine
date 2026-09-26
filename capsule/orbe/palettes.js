// MEANING — work families, their colors, and their materials.
//
// This is the only file to change when connecting the orb to another project.
// The engine (`orbe.js`) knows no agents or families; it receives only a
// motion pattern and its settings.
//
// ── MODEL ─────────────────────────────────────────────────────────────────
// Three deliberately separate channels:
//   · HUE identifies the work family: four are easier to learn than thirteen.
//   · FLUID MOTION identifies the kind of activity, even without color.
//   · STEP INTENSITY changes speed, amplitude, and lightness, never hue.
import { hex, chromaMax } from './couleur.js';
// Import from `mecaniques.js`: importing the engine would load Three.js (1.27 MB)
// even when only the colors are needed.
import { MECANIQUES } from './mecaniques.js';

// Hues are chosen in OKLCh and checked visually after rendering. At 215°, a
// supposed blue becomes turquoise as chroma rises, merging with the green family.
export const FAMILLES = {
  repos: {
    // Chroma 0.16 made a gray ball: violet at 268° was outside the displayable
    // gamut at that level. Idle is the most common state and needs visible color.
    // Lower speed for subtlety, while keeping hue.
    // `respiration` replaces `interference`. The latter looked almost static
    // and could be confused with a low intensity Inspection. Breathing alone
    // has a pure, noiseless pulse, distinct even without color or a label.
    nom: 'Repos', meca: MECANIQUES.respiration, teinte: 288, chroma: 0.50,
    // `speed` sets the phase cadence and therefore breathing frequency. At
    // 0.10, a ~39 s cycle looked frozen; 0.50 makes a visible ~8 s breath.
    // The shader runs at 12 fps (see CADENCE in orbe.html), so each ~83 ms
    // displacement remains below one pixel. CSS breathing cost 17% idle CPU.
    lent: { disp: 0.085, freq: 0.55, speed: 0.42 },
    vif:  { disp: 0.100, freq: 0.65, speed: 0.52 },
  },
  inspection: {          // observes and judges without changing anything
    nom: 'Inspection', meca: MECANIQUES.houle, teinte: 252, chroma: 0.85,
    lent: { disp: 0.090, freq: 0.85, speed: 0.22 },
    vif:  { disp: 0.150, freq: 1.35, speed: 0.62 },
  },
  organisation: {        // sorts, classifies, and moves
    nom: 'Organisation', meca: MECANIQUES.balayage, teinte: 150, chroma: 0.85,
    lent: { disp: 0.120, freq: 0.90, speed: 0.28 },
    vif:  { disp: 0.230, freq: 1.60, speed: 0.80 },
  },
  transformation: {      // distills and produces
    nom: 'Transformation', meca: MECANIQUES.vortex, teinte: 300, chroma: 0.85,
    lent: { disp: 0.150, freq: 1.05, speed: 0.45 },
    vif:  { disp: 0.280, freq: 1.80, speed: 1.25 },
  },
  validation: {          // records and seals
    nom: 'Validation', meca: MECANIQUES.eclats, teinte: 50, chroma: 0.90,
    lent: { disp: 0.130, freq: 1.10, speed: 0.65 },
    vif:  { disp: 0.165, freq: 1.35, speed: 0.95 },
  },
};

// State → [family, intensity 0→1]. Map the host project's vocabulary here.
export const ETATS = {
  idle:         ['repos', 0.0],
  mapping:      ['inspection', 0.10],   auditing:    ['inspection', 0.40],
  architecting: ['inspection', 0.70],   challenging: ['inspection', 1.00],
  filing:       ['organisation', 0.10], archiving:   ['organisation', 0.40],
  gardening:    ['organisation', 0.70], correcting:  ['organisation', 1.00],
  working:      ['transformation', 0.15], distilling: ['transformation', 0.60],
  synthesizing: ['transformation', 1.00],
  committing:   ['validation', 1.00],
};

const entre = (a, b, k) => a + (b - a) * k;

// Within a family, vary lightness for visible contrast; chroma alone made four
// nearly identical blues. Deeper steps look darker and denser.
// `part` ∈ [0,1] is a fraction of the displayable maximum chroma. An absolute
// chroma would look saturated at one lightness and dull at another.
function nuancier(teinte, part, niv) {
  const L = 0.74 - 0.20 * niv;
  const vivacite = chromaMax(L, teinte) * part;
  return {
    c1:  hex(Math.min(0.97, L + 0.30), vivacite * 0.45, teinte),  // crest
    c2:  hex(L,                        vivacite,        teinte),  // body
    c3:  hex(0.10 + 0.06 * (1 - niv),  vivacite * 0.55, teinte),  // trough
    rim: hex(0.97,                     vivacite * 0.35, teinte),  // rim
    rimI: 1.05 + 0.35 * niv,
  };
}

/** Full state settings: colors, material, and motion. */
export function reglage(etat) {
  const [nomFam, niv] = ETATS[etat] || ETATS.idle;
  const f = FAMILLES[nomFam];
  // Keep separate scales for color and motion. At low intensity, the lightness
  // formula approaches 0.74 and made `working` look like washed-out lavender.
  // Color needs a floor to remain legible; motion still uses the true `niv`.
  const nivCouleur = Math.max(niv, 0.50);
  return {
    ...nuancier(f.teinte, f.chroma * (0.72 + 0.28 * nivCouleur), nivCouleur),
    disp:  entre(f.lent.disp,  f.vif.disp,  niv),
    freq:  entre(f.lent.freq,  f.vif.freq,  niv),
    speed: entre(f.lent.speed, f.vif.speed, niv),
    meca:  f.meca,
    famille: nomFam, nomFamille: f.nom, intensite: niv,
  };
}

export function listeEtats() { return Object.keys(ETATS); }
