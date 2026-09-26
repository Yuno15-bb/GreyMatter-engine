// OKLCh to sRGB, with a real gamut check.
//
// The earlier Brain conversion clipped channels internally (`min(1,max(0,u))`)
// before returning a color. A later gamut check therefore always said yes.
// Channel-by-channel clipping also shifts the hue: requested blue can turn
// green without any warning.
//
// This conversion returns unclipped linear values first (`versLineaire`), so
// gamut can be checked. `hex()` then binary-searches the greatest achievable
// chroma at the requested lightness, preserving hue by reducing chroma.

const M = [
  [+4.0767416621, -3.3077115913, +0.2309699292],
  [-1.2684380046, +2.6097574011, -0.3413193965],
  [-0.0041960863, -0.7034186147, +1.7076147010],
];

/** Unclipped linear sRGB; values outside [0,1] reveal a gamut mismatch. */
export function versLineaire(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  return M.map(([x, y, z]) => x * l + y * m + z * s);
}

export function tenable(L, C, hDeg, marge = 0.001) {
  return versLineaire(L, C, hDeg).every(u => u >= -marge && u <= 1 + marge);
}

const gamma = (u) => {
  u = Math.min(1, Math.max(0, u));
  return Math.round((u > 0.0031308 ? 1.055 * u ** (1 / 2.4) - 0.055 : 12.92 * u) * 255);
};

/**
 * Closest displayable hexadecimal color to (L,C,h).
 * Reduce excessive chroma at this lightness while preserving hue.
 */
export function hex(L, C, hDeg) {
  let c = C;
  if (!tenable(L, c, hDeg)) {
    let lo = 0, hi = C;
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2;
      if (tenable(L, mid, hDeg)) lo = mid; else hi = mid;
    }
    c = lo;
  }
  const [r, g, b] = versLineaire(L, c, hDeg).map(gamma);
  const d = (v) => v.toString(16).padStart(2, '0');
  return '#' + d(r) + d(g) + d(b);
}

/** Greatest displayable chroma for a given lightness and hue. */
export function chromaMax(L, hDeg) {
  let lo = 0, hi = 0.45;
  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) / 2;
    if (tenable(L, mid, hDeg)) lo = mid; else hi = mid;
  }
  return lo;
}
