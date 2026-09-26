/* semantic-label.js — what the map can truthfully claim about itself.
 *
 * INCIDENT (measured 2026-08-19, checked on screen again 2026-09-19). The map
 * opens in its main meaning view. The shipped package claimed proximity meant
 * meaning, but 0 of 10 notes had vectors (0 of 36 in an installed trunk).
 * Every note used the structural fallback intended for a note without a vector.
 * The 3D engine was the same; the vector data was missing, with no error shown.
 *
 * Embeddings are optional by design (docs/design-doc.md); the installer adds
 * neither a venv nor pip. The label must state which layout is actually shown.
 *
 * This separate module lets a Node check import the four labels directly.
 * Checking equivalent code inside index.html would require a browser and 3D
 * engine, including in CI where Chrome may be unavailable.
 */

/** Infer missing exporter metadata from the notes. Older graph.json files have
 *  no `semantic` block; assuming they are ready would restore the false label. */
export function capaciteSemantique(data) {
  if (data && data.semantic && typeof data.semantic.state === 'string') return data.semantic;
  const noeuds = (data && data.nodes) || [];
  const couverts = noeuds.filter(n => n && n.embed2).length;
  return {
    state: couverts === 0 ? 'absent' : couverts === noeuds.length ? 'ready' : 'partial',
    covered: couverts, total: noeuds.length,
    detail: 'graph.json predates the semantic declaration — state inferred from the notes',
  };
}

/** Return { titre, bandeau } for the meaning view. One function keeps the title
 *  and banner in agreement (the old title and banner diverged on 2026-08-15). */
export function etiquetteSens(sem) {
  const c = sem || { state: 'absent', covered: 0, total: 0 };
  const n = c.covered, t = c.total;
  switch (c.state) {
    case 'ready':
      return { titre: '[ TRUNK MAP — MEANING ]',
               bandeau: '✦ MEANING IN VOLUME — proximity = meaning, every note · S structure' };
    case 'partial':
      return { titre: `[ TRUNK MAP — MEANING, ${n}/${t} ]`,
               bandeau: `◐ INDEXING — ${n} of ${t} notes placed by meaning, the rest kept in structure · S structure` };
    case 'broken':
      return { titre: '[ TRUNK MAP — MEANING UNAVAILABLE ]',
               bandeau: `⚠ SEMANTIC MAP UNREADABLE — showing structure${c.detail ? ' — ' + c.detail : ''} · S structure` };
    default:   // For absent or unknown states, describe the displayed structure.
      return { titre: '[ TRUNK MAP — STRUCTURE, NO MEANING YET ]',
               bandeau: '▦ STRUCTURAL VIEW (no embeddings) — no note is placed by meaning here · S structure' };
  }
}

/** Keep the globe's S-key invitation accurate too: without vectors, it opens
 *  the flat structural map rather than a meaning map. */
export function etiquette3d(sem, region) {
  if (region) return `◉ ${region} IN VOLUME — drag to turn · Esc to come back out`;
  const c = sem || { state: 'absent' };
  return (c.state === 'ready' || c.state === 'partial')
    ? '◉ 3D — S for meaning'
    : '◉ 3D — S for the flat map';
}
