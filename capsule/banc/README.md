# Banc de vérification de l'orbe

Regarder le rendu, jamais le déduire du code. Ces scripts existaient dans `/tmp`
pendant la session du 2026-08-03 — ils y auraient disparu au prochain redémarrage,
alors qu'ils sont la seule façon honnête de juger une modification de l'orbe.

## Les scripts

| Script | Ce qu'il fait |
|---|---|
| `planche.cjs` | capture `orbe.html` état par état, sur un faux bureau coloré |
| `silhouette.cjs` | relève les bornes du mesh sur le canal alpha, état par état |
| `film.cjs` | filme la démo du README — voir ses trois pièges en tête de fichier |
| `glisse.cjs` | prouve que `mousedown` au centre déplace la fenêtre, et qu'un coin ne fait rien |
| `cycle.sh` | fait passer l'orbe **vivante** par ses 13 états, pour la regarder sur le vrai bureau |

Tous se lancent avec l'Electron du dossier parent :

```sh
cd ~/claude-brain/capsule
./node_modules/.bin/electron banc/planche.cjs
```

## Les pièges qui ont coûté du temps

- **Le verre ne se juge pas sur fond noir.** Un objet transparent y est
  indiscernable d'un objet opaque. `planche.cjs` pose donc un dégradé et du
  texte derrière — sans ça la planche ne prouve rien.
- **La démo de `~/Desktop/Orbe` rétrécit l'orbe à 69 px** dans une fenêtre de
  150 : sa mise en page réserve la place d'un panneau. On mesure sur
  `orbe.html`, la vraie page de la capsule.
- **Les bornes sortent en pixels d'ÉCRAN, pas en pixels CSS** : la capture est
  en retina 2×, donc une fenêtre de 150 rend un bitmap de 300. Les lire tels
  quels place un élément au double de la bonne distance.
- **Attendre 2,6 s après un changement d'état** : le fondu de mécanique dure
  1,4 s, et capturer avant donne une forme intermédiaire qui n'existe jamais.
- **Tuer par chemin complet ET vérifier le compte** avant toute mesure :
  `pgrep -f "claude-brain/capsule" | xargs kill -9` puis recompter. Un motif
  approximatif échoue en silence et on mesure une instance périmée.

## Piège du 20/09 — l'état est PARTAGÉ entre toutes les sessions Claude
`film.cjs` et `cycle.sh` pilotent l'orbe par `state/status.json`. Or chaque session Claude
ouverte (quatre en parallèle ce jour-là) y estampille `busy / working` à chacun de ses appels
d'outil, via le hook `brain_battement.py`. Un tournage s'est fait polluer à 13,7 s : WORKING
s'est invité dans les trois secondes de repos. « Ne rien exécuter pendant » ne suffit donc
pas — les autres sessions, on ne les contrôle pas. **Tourner dans un tronc miroir** :
`HOME=<miroir> BRAIN_HOME=<miroir>/claude-brain`, où le miroir symlinke tout le tronc sauf
`state/`, qui est à nous. `orbe.html` résout tout par `os.homedir()` et `brain_status.py`
par `BRAIN_HOME` : les deux suivent, et le bureau de l'auteur ne clignote même plus.
