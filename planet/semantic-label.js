/* semantic-label.js — ce que la carte a le DROIT de dire d'elle-même.
 *
 * L'INCIDENT (mesuré le 2026-08-19, remesuré À L'ÉCRAN le 2026-09-19). La carte s'ouvre sur la
 * vue « sens » — c'est la vue principale, choix de l'auteur. Sur le paquet livré, elle annonçait
 * « ✦ SENS EN VOLUME — proximité = sens, toutes les fiches » avec 0 fiche sur 10 portant un
 * vecteur, et 0 sur 36 dans un tronc installé. Toutes les fiches étaient posées à leur place
 * STRUCTURELLE par un repli prévu pour « une fiche qui n'a pas encore de vecteur » et appliqué
 * là à 100 % d'entre elles. Le moteur 3D est identique des deux côtés : rien n'était « en 2D »,
 * c'est la donnée qui manquait — et l'écran affirmait le contraire, sans une ligne d'erreur.
 *
 * CE QUI N'EST PAS LE DÉFAUT. Les embeddings sont OPTIONNELS PAR DESSEIN (docs/design-doc.md), et
 * l'installeur ne pose ni venv ni pip. La capacité absente est légitime ; l'AFFICHAGE qui la
 * présente comme présente ne l'est pas. On ne répare donc pas en ajoutant un venv, on répare en
 * disant la vérité sur ce qui est montré.
 *
 * POURQUOI UN FICHIER À PART. Tout le reste de la page vit dans la portée d'un
 * `<script type="module">`, derrière un moteur 3D : pour vérifier une phrase il faudrait un
 * navigateur. Ici, un contrôle l'importe sous `node` et compare des CHAÎNES — les quatre états
 * se lisent en une seconde, partout, y compris là où aucun Chrome n'est installé.
 */

/** Ce que l'exporteur n'a pas dit, on le DÉDUIT DES FICHES — jamais on ne suppose « tout va bien ».
 *  Un graph.json d'avant ce jour n'a pas de bloc `semantic` ; le lire comme « prêt » ramènerait
 *  exactement le mensonge qu'on retire. */
export function capaciteSemantique(data) {
  if (data && data.semantic && typeof data.semantic.state === 'string') return data.semantic;
  const noeuds = (data && data.nodes) || [];
  const couverts = noeuds.filter(n => n && n.embed2).length;
  return {
    state: couverts === 0 ? 'absent' : couverts === noeuds.length ? 'ready' : 'partial',
    covered: couverts, total: noeuds.length,
    detail: 'graph.json est antérieur à la déclaration sémantique — état déduit des fiches',
  };
}

/** → { titre, bandeau } pour la vue SENS. Un seul endroit décide, donc les deux ne peuvent pas
 *  diverger : le titre a déjà annoncé « LE SENS » pendant que la vue montrait autre chose, et
 *  c'est précisément comme ça qu'un libellé faux survit (index.html, 2026-08-15). */
export function etiquetteSens(sem) {
  const c = sem || { state: 'absent', covered: 0, total: 0 };
  const n = c.covered, t = c.total;
  switch (c.state) {
    case 'ready':
      return { titre: '[ CARTE DU TRONC — LE SENS ]',
               bandeau: '✦ SENS EN VOLUME — proximité = sens, toutes les fiches · S structure' };
    case 'partial':
      return { titre: `[ CARTE DU TRONC — LE SENS, ${n}/${t} ]`,
               bandeau: `◐ INDEXATION — ${n} fiches sur ${t} posées par le sens, les autres restent en structure · S structure` };
    case 'broken':
      return { titre: '[ CARTE DU TRONC — SENS INDISPONIBLE ]',
               bandeau: `⚠ CARTE SÉMANTIQUE ILLISIBLE — on montre la structure${c.detail ? ' — ' + c.detail : ''} · S structure` };
    default:   // 'absent' et tout état inconnu : on dit ce qu'on montre, pas ce qu'on voudrait
      return { titre: '[ CARTE DU TRONC — STRUCTURE, PAS ENCORE DE SENS ]',
               bandeau: "▦ VUE STRUCTURELLE (sans embeddings) — aucune fiche n'est posée par le sens ici · S structure" };
  }
}

/** La même promesse, un clic en amont. Depuis le globe, le bandeau invitait à « S pour le sens » :
 *  sans vecteurs, cette touche ne donne pas du sens, elle donne la carte à plat. Une invitation
 *  fausse est un libellé faux — même famille, même correction. */
export function etiquette3d(sem, region) {
  if (region) return `◉ ${region} EN VOLUME — glisser pour tourner · Échap pour ressortir`;
  const c = sem || { state: 'absent' };
  return (c.state === 'ready' || c.state === 'partial')
    ? '◉ 3D — S pour le sens'
    : '◉ 3D — S pour la carte à plat';
}
