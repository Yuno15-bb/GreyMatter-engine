// THE TEN FLUID MECHANICS — nothing but constants.
//
// WHY THIS FILE EXISTS, GIVEN THAT IT IS TEN NUMBERS
//   `palettes.js` needs only this to say which family moves how.
//   But these constants used to live in `orbe.js`, which imports Three.js — so
//   any page that only wanted to KNOW THE COLOURS downloaded 1.27 MB of 3D
//   engine before it could show a single one.
//   Invisible on the desktop (everything is on disk), very visible on a phone
//   over 4G: the author saw the orb's tinted background arrive "well late" —
//   it was waiting on Three.
//   `orbe.js` RE-EXPORTS them: any code that imported them from there keeps
//   working, no caller to change.
export const MECANIQUES = { houle:0, balayage:1, plaques:2, ebullition:3,
  ondeDeChoc:4, cellules:5, vortex:6, respiration:7, interference:8, eclats:9 };
