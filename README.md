# 🧠 C Brain

[![CI](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml/badge.svg?branch=fr)](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Yuno15-bb/c-brain?sort=semver&color=6b8afd)](https://github.com/Yuno15-bb/c-brain/releases/latest)
[![Licence](https://img.shields.io/github/license/Yuno15-bb/c-brain?color=8a8f98)](LICENSE)
[![Plateforme](https://img.shields.io/badge/plateforme-macOS-8a8f98)](#compatibilité)

> 🇫🇷 Ceci est la **branche française**. La version anglaise, celle que tout le
> monde installe par défaut, est sur [`main`](https://github.com/Yuno15-bb/c-brain).

<p align="center">
  <img src="docs/media/capsule.webp" alt="La capsule : une orbe de verre posée sur le bureau, dont la matière et la teinte changent au travail de chaque agent — distillation, jardinage, classement, correction, cartographie, architecture, contestation, archivage, synthèse, audit, sauvegarde — avec le code en train d'être écrit qui défile à l'intérieur" width="168">
</p>
<p align="center"><sub>Tes agents, au travail. En direct, dans le coin de ton écran.</sub></p>

**C Brain transforme chaque session avec ton agent CLI en mémoire réutilisable —
distillée en fiche, rangée, reliée, et rendue automatiquement la fois où ça
compte. Depuis n'importe quel projet, et sans quitter ta machine.**

Ton agent est excellent dans une session et amnésique entre deux. Tu résous
quelque chose lundi, tu le réexpliques jeudi. C Brain est la partie qui se
souvient.

Plus le travail s'accumule, plus l'arbre devient utile — l'inverse d'un
historique de conversation, qui ne fait que s'allonger.

---

## Ce que ça fait concrètement

**La mémoire elle-même** — c'est ça le produit, et ça suffit :

| | |
|---|---|
| 🌳 **Un tronc** | tes leçons, projets, méthode — en markdown, chez toi, versionnable |
| 🔎 **Rappel automatique** | à chaque question, les fiches pertinentes sont injectées dans le contexte |
| 📈 **Il apprend de l'usage** | ce qui t'a servi remonte — avec une place réservée aux fiches jamais vues, pour ne pas tourner en rond |
| 🕰️ **Il connaît son âge** | les fiches jamais revérifiées entrent dans une file de revue, datée par l'historique git |
| 🤖 **4 vaisseaux, 8 missions** | quatre noms à retenir ; derrière eux, huit rôles étroits qui distillent, rangent, relient, contestent, synthétisent, élaguent, réparent, surveillent la machine |
| 🔁 **Boucle fermée** | fin de session → archivage → distillation → rangement, sans rien demander |
| ⬆️ **Mises à jour** | le moteur s'actualise **tout seul** à chaque session ; **tes fiches ne sont jamais touchées** |

**Et deux façons de le regarder**, qui sont des extensions et s'installent à
part — `./install.sh --core-only` laisse les deux de côté :

| | |
|---|---|
| 🥚 **Une capsule** | petite fenêtre Electron qui montre les agents travailler, en direct |
| 🪐 **Une planète** | ton savoir en globe 3D navigable, régénéré à chaque lancement |

<p align="center">
  <img src="docs/media/architecture.png" alt="Comment une session devient de la mémoire : le tronc — ~/.c-brain/trunk, qui porte les fiches, MEMORY.md et l'état — est lu et écrit par trois étapes de hooks à l'intérieur de ta session. À chaque prompt, inject_recall se sert de BM25 et d'embeddings pour choisir les quelques fiches qui répondent à ta demande, et les colle dans le prompt. Pendant la session, post_diff, track_read, on_fiche_write et pre_snapshot enregistrent ce qui est écrit et lu. À la fin, archive_session et auto_maintain archivent la session puis réveillent les agents, en deux couches : la couche 1 lance toujours le distillateur puis le jardinier, ce dernier conditionné à la réussite réelle du premier ; la couche 2 ne réveille au plus qu'un agent parmi le challenger, l'architecte, l'archiviste et le mécanicien, et seulement si son capteur franchit un seuil et que douze heures ont passé. En bas, les trois façons de le regarder : la capsule qui lit state/status.json, la planète bâtie par graph_export, et le CLI brain — status, review, selftest, update — chaque étape automatique relançable à la main" width="900">
</p>

### Il est bon à quel point, ce rappel ?

Mesuré, pas affirmé — `tests/recall_benchmark.py`, sur un corpus synthétique où
trouver la réponse veut dire choisir **une** fiche parmi ~120 qui partagent son
sujet et l'essentiel de son vocabulaire :

| fiches | P@1 | P@3 | MRR | hors sujet dans ce qu'il injecte | par prompt |
|---|---|---|---|---|---|
| 100 | 0,94 | 0,98 | 0,96 | 35 % | 5 ms |
| 1000 | 0,79 | 0,93 | 0,86 | 24 % | 47 ms |
| 5000 | 0,46 | 0,83 | 0,64 | 39 % | — |

Il tient jusqu'à environ mille fiches et se dégrade nettement au-delà. Publié
ici parce qu'un outil de mémoire qui refuse de dire à quel point il se souvient
demande une confiance qu'il n'a pas gagnée. La CI tient ces chiffres comme des
seuils.

⚠️ **Ce banc ne mesure PAS tout.** Son corpus est synthétique, donc son
vocabulaire est cohérent : il ne dit rien de la morphologie (« ranger » contre
« rangement ») ni du mélange français/anglais, qui sont deux causes réelles de
fiche introuvable. Ses chiffres n'ont pas bougé quand ces deux points ont été
corrigés — c'est une limite du banc, pas l'absence d'effet.

### Et sur un vrai tronc, ça change quoi ?

Mesuré le 2026-08-12 sur le Brain vivant de l'auteur (312 fiches), 10 questions
portant sur des faits réels de son travail, 50 exécutions isolées les unes des
autres :

| ce dont dispose l'assistant | bonnes réponses | tokens par échange |
|---|---|---|
| rien | **0/10** | 178 k |
| le tronc + la carte, **sans** rappel automatique | **8/10** | 264 k |
| **le système complet** | **10/10** | **168 k** |

Le rappel automatique ne coûte pas de contexte, il en **économise** : sans
suggestion, l'assistant doit chercher, et chercher brûle des tours. Le détail du
protocole — et les trois campagnes qu'il a fallu jeter avant d'obtenir une mesure
honnête — est dans le tronc de l'auteur, pas ici.

## Installation

**En plugin Claude Code** — la voie courte, et celle qui se met à jour toute
seule (elle installe la version **anglaise** : le plugin suit `main`) :

```
/plugin marketplace add Yuno15-bb/c-brain
/plugin install c-brain@c-brain
```

Ça te donne toute la mémoire : le tronc, le rappel automatique, les quatre vaisseaux
et leurs huit missions,
la commande `brain`, et trois commandes que tu peux taper — `/c-brain:recall`,
`/c-brain:distill`, `/c-brain:doctor`. Le tronc `~/.c-brain/trunk` est créé à ta première
session, et on te le dit. Ça n'installe **pas** la capsule, la planète ni les
tâches planifiées — un plugin ne peut pas installer un service d'arrière-plan,
et prétendre le contraire te laisserait avec une fenêtre qui ne s'ouvre jamais.

**L'install complète, en français** — tout ce qui précède, plus la capsule, la
planète et la maintenance sans surveillance. Colle ceci dans ton CLI :

```
Installe C Brain : clone https://github.com/Yuno15-bb/c-brain dans ~/dev/c-brain
sur la branche fr, lis son INSTALL.md, puis exécute ./install.sh et montre-moi
le résultat de la vérification finale.
```

Ou à la main : `git clone -b fr … && cd c-brain && ./install.sh`

**La mémoire et rien d'autre** — pas de fenêtre Electron, pas de globe 3D, pas
de tâche de fond :

```bash
./install.sh --core-only
```

Détails, prérequis et désinstallation : **[INSTALL.md](INSTALL.md)**.

## L'idée qui tient tout

```
~/.c-brain/engine  ← le MOTEUR. Du code. Se met à jour, se remplace, se jette.
~/.c-brain/trunk     ← le TRONC. Tes fiches. Ne bouge que quand TU écris.
```

Les deux ne se mélangent jamais. C'est ce qui permet à une mise à jour d'arriver
sans le moindre risque pour ton travail — et à `uninstall.sh` de tout retirer en
laissant ta connaissance intacte.

Le point de `~/.c-brain` le **cache dans le Finder**. L'installation pose donc
un raccourci `C Brain` dans ton dossier personnel, tagué en rouge, qui ouvre ton
tronc — une mémoire qu'on ne peut pas voir est une mémoire à laquelle on ne
touche jamais (`--no-shortcut` si tu n'en veux pas).

<p align="center">
  <img src="docs/media/where-it-lands.png" alt="Un dossier personnel dans le Finder : les habituels Applications, Bureau, Documents, Téléchargements, Films, Musique et Images — plus un dossier C Brain tagué en rouge, désigné par une flèche" width="900">
</p>

## Ce que ça ne fait pas

- **Ça ne fait aucune requête de son côté.** Aucune télémétrie, aucun appel
  réseau hors `git pull`. Ce qui voyage, c'est ce que tes prompts emportent
  déjà : le hook de rappel ajoute le nom, la description et le chemin de deux ou
  trois fiches à un prompt que tu envoyais de toute façon, et les agents que tu
  lances lisent des fiches entières. Les deux partent chez ton fournisseur de
  modèle, comme le reste de ton message. [`SECURITY.md`](SECURITY.md) dit
  précisément où passe la ligne.
- **Ça se met à jour tout seul, et il faut le savoir.** Chaque démarrage de
  session installe la dernière version publiée, en arrière-plan — donc du code
  venu du dépôt tourne chez toi sans que tu l'aies demandé. Le tronc n'est
  jamais touché, une version dont le selftest est rouge est défaite
  automatiquement, et `brain update --auto-off` rend le comportement d'avant
  (signaler sans installer).
- **Ça ne livre aucun contenu.** Ton arbre démarre vide — voir
  [`skills/README.md`](skills/README.md) pour la philosophie : on transmet la
  méthode, pas le vécu de quelqu'un d'autre.

## Les extensions

Aucune des deux ci-dessous n'est le produit. Ce sont des façons de le *regarder*
— agréables, facultatives, et entièrement sautées par `./install.sh --core-only`.
L'installation en plugin ne les met jamais en place, parce qu'un plugin ne peut
pas installer un service d'arrière-plan.

### La capsule

<p align="center">
  <img src="docs/media/capsule.webp" alt="La capsule : une petite fenêtre qui parcourt tous les états des agents — distillation, jardinage, rangement, correction, cartographie, architecture, contestation, archivage, synthèse, audit, commit, puis retour au repos" width="190">
</p>
<p align="center"><sub>À sa taille réelle, un état par famille — puis le retour au repos.</sub></p>

### La planète

Ton savoir en globe 3D, régénéré à chaque lancement depuis les fiches. Les
continents sont les domaines, les arcs sont les liens `[[...]]` que les agents
ont tissés. Survoler une fiche allume ses connexions ; un double-clic l'épingle.

Deux vues, et c'est là qu'elle devient utile : `V` montre le **rangement** —
où tu as classé une fiche ; `S` montre le **sens** — ce à quoi elle ressemble,
dossiers ignorés. Une fiche seule dans son coin sur le globe mais collée à cinq
autres en vue *sens*, c'est un lien que tu n'as pas encore écrit.

Les points chauffent quand on les lit et s'éteignent tout seuls ; les pastilles
⚠ ✦ ↻ ▷ signalent ce qui est contesté, tenu pour acquis, resté ouvert, ou
rejouable en 3D.

📖 **[Documentation complète de la planète](docs/planete.md)** — les deux vues,
la lecture d'un point, les pastilles, et ce que la carte ne sait pas faire.

<p align="center">
  <img src="docs/media/planet.webp" alt="La planète de connaissance : le globe tourne, le curseur se pose sur une fiche, ses arcs de liens s'allument et un panneau s'ouvre montrant la région de la fiche, ses sept connexions, sa description et le chemin de son fichier" width="900">
</p>

## Commandes

<p align="center">
  <img src="docs/media/recall.png" alt="Terminal : brain demo pose trois fiches, brain recall les classe par pertinence, brain demo --remove les retire" width="820">
</p>

```bash
brain status          où en est le tronc
brain recall <mot>    chercher dans ta mémoire
brain doctor          santé de l'arbre (liens morts, incohérences)
brain review          audit global du tronc
brain next            tes points de reprise
brain selftest        vérifier l'installation
brain update          mettre à jour le moteur  (--check · --rollback)
                      automatique à chaque session : --auto-off / --auto-on
brain version         version installée
```

## Compatibilité

**macOS.** launchd, Electron et `open` sont utilisés.

**Linux n'est pas encore supporté, et l'écart est plus petit qu'il n'y paraît.**
En lisant le code plutôt qu'en devinant : macOS n'est supposé qu'à **quatre
endroits** — le contrôle de plateforme d'`install.sh`, les gabarits `launchd`, le
lanceur `.command` du Bureau, et le tag Finder `xattr`. Claude Code n'est supposé
que dans **un** fichier, `merge_settings.py`. Tout le reste — tronc, rappel,
agents, CLI `brain`, hooks — est déjà du Python et du shell portables.

C'est donc un cœur portable avec deux adaptateurs minces, pas un produit macOS.
L'ordre prévu : **des unités `systemd` à la place de `launchd`, une entrée
`.desktop` à la place du `.command`, pas de tag Finder, et `--core-only` comme
forme par défaut sous Linux.** Aucune date là-dessus : dire quels quatre endroits
doivent changer est plus utile qu'une promesse.

**Claude Code** pour l'expérience complète : c'est lui qui déclenche les hooks
(rappel, archivage, maintenance autonome, ligne d'état). Avec un autre agent CLI,
C Brain s'installe et fonctionne **à la demande** — tronc, agents, `brain`,
planète, capsule — mais sans boucle automatique. L'installeur le détecte et te le
dit plutôt que de faire semblant.

## Pour les curieux

- [`docs/cadrage-c-brain.md`](docs/cadrage-c-brain.md) — le design-doc : le
  problème, les alternatives rejetées, les pièges rencontrés et comment ils ont
  été refermés.
- `sync.sh` + `rules.json` + `leakcheck.py` — la chaîne qui extrait ce moteur
  d'un Brain réel sans en laisser fuir une ligne de vécu.

## Licence

**Apache 2.0** — voir [LICENSE](LICENSE).

Tu peux l'utiliser, l'étudier, le modifier, le redistribuer et construire dessus,
y compris commercialement. La licence inclut une clause de brevets, et demande
seulement de conserver l'attribution et d'indiquer tes modifications.

Tout ce que tu écris avec — tes notes, ton tronc, tes skills — t'appartient, et
cette licence n'en revendique rien.

