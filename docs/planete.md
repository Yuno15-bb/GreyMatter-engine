# La planète

Une carte en trois dimensions de tout ce que ton tronc sait. Chaque point est une
fiche, chaque trait un lien `[[...]]` que tu as écrit.

Elle n'est pas là pour décorer. Elle répond à trois questions qu'aucune liste de
fichiers ne sait poser :

- **où est-ce que je travaille en ce moment ?** — les points lus récemment
  chauffent, le reste s'éteint ;
- **qu'est-ce qui est relié à quoi sans que je l'aie décidé ?** — la vue *sens*
  place les fiches par ressemblance de contenu, pas par dossier ;
- **qu'est-ce qui traîne ?** — les fiches contestées, tenues pour acquises, ou
  restées ouvertes portent une pastille.

---

## Lancer

```bash
planet/launch.sh          # http://localhost:8765
planet/launch.sh 8770     # un autre port, si 8765 est pris
```

Le lanceur reconstruit le graphe **avant** d'ouvrir la page — la carte ne montre
donc jamais un état périmé. Rien n'est stocké entre deux lancements : ferme
l'onglet, tout repart du tronc la fois suivante.

---

## Les deux vues, et ce que chacune dit

| Touche | Vue | Ce que la POSITION signifie |
|---|---|---|
| `V` | **globe 3D** | le **rangement** — région = dossier, ville = projet |
| `S` | **sens** | la **ressemblance** — deux fiches proches parlent de la même chose, même sans lien entre elles |

C'est l'intérêt de garder les deux. Le globe dit où tu as *rangé* une fiche ;
la carte du sens dit ce à quoi elle *ressemble*. Une fiche isolée dans son dossier
mais collée à cinq autres en vue *sens*, c'est un lien que tu n'as pas encore écrit.

`Échap` ressort d'une région dans laquelle on est entré.

---

## Lire un point

- **La couleur** dit la région : leçons, méta, vie, agents, projets.
- **Le halo orangé** dit la chaleur — à quel point la fiche a été activée
  récemment. Il décroît tout seul ; une fiche jamais relue s'éteint.
- **L'anneau** signale les fiches réellement **lues** dans les dernières minutes,
  pas celles que le rappel a simplement proposées. La distinction compte : la
  première version comptait tout ce qui était proposé sur une session entière et
  allumait un tiers de la carte en permanence.

### Les pastilles, à côté du point

| Pastille | Sens | D'où ça vient |
|---|---|---|
| ⚠ | **avis du challenger** — cette fiche a été contestée | la mission `challenger`, à bord du SULACO |
| ✦ | **conviction** — une position tenue, pas un simple fait | convictions curées |
| ↻ | **à reprendre** — un fil resté ouvert dans la fiche | marqueurs de reprise |
| ▷ | **rejouable** — la fiche porte une capture 3D | `.glb` associé |

Un ▷ clignote doucement : **double-clic** ouvre la capture, qu'on peut alors
tourner à la main (glisser) et zoomer (molette). `Échap` revient à la carte.

### Le panneau de survol

Pointe un point : ses liens s'allument, et le panneau donne sa région, ses
voisines, sa description et le fichier où elle vit. Les connexions sont **en fin
de panneau**, après le texte — on lit d'abord ce que dit la fiche, on regarde
ensuite à quoi elle est reliée.

---

## Le bandeau du haut

- `◉ N points actifs` — ce qui est réellement lu, sur une fenêtre courte. Tombe à
  zéro tout seul, et c'est voulu : un compteur qui ne redescend jamais ne dit rien.
- `◉ en direct dans : …` — les régions où la session en cours travaille.
- `✦ +N fiches` — ce que le tronc a gagné.
- `⚠ N contestées` — ce que le challenger a mis en doute.

---

## Ce que la carte ne sait pas faire

Écrit ici plutôt que découvert à l'usage.

- **Les liens ne sont pas occultés.** Les traits de la face arrière sont peints
  par-dessus la face avant. Sur un tronc dense, presque un lien sur deux traverse
  le globe de part en part et le nuage gris vient d'une poignée de très gros nœuds.
- **Une région peut écraser les autres.** Si l'essentiel de ton savoir est en
  leçons transverses, cette région pèsera la moitié de la carte et le code couleur
  perdra de sa force.
- **Les toutes petites régions s'éteignent.** Une région à une ou deux fiches
  occupe une couleur de légende pour presque rien ; c'est assumé.
- **La vue *sens* est un nuage réagencé**, pas des paquets nets. Les fiches
  courtes se ressemblent trop pour se séparer franchement. La valeur est dans le
  réagencement — les voisinages inattendus — pas dans l'esthétique des amas.

---

## D'où viennent les données

| Fichier | Ce qu'il porte |
|---|---|
| `planet/index.html` | toute la carte : rendu, vues, panneaux |
| `hooks/graph_export.py` | construit le graphe depuis le tronc, à chaque lancement |
| `hooks/coactivation.py` | la chaleur et la session en cours |

Aucun `.json` de planète n'est livré avec le paquet : ils contiendraient le texte
de tes fiches. Ils se reconstruisent au lancement, chez toi, et n'en sortent pas.
