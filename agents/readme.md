---
name: readme
description: Guide des 4 vaisseaux du système (NOSTROMO, NARCISSUS, SULACO, ANESIDORA) et des 8 missions qu'ils portent — rôles, frontières, lancement, seuils autonomes
metadata:
  type: reference
---

# 🤖 Agents du C Brain

## En clair

Le guide des agents qui entretiennent ce carnet, et surtout de leurs frontières.

Depuis le 20/09/2026, ils sont rangés en **quatre vaisseaux**. Un vaisseau est ce qu'on
appelle ; une **mission** est ce qu'il fait une fois réveillé. Les huit rôles d'origine
n'ont pas disparu — chacun garde son texte, ses outils et sa zone d'écriture — mais il n'y
a plus que quatre noms à retenir, et la consigne reçue dit laquelle des missions du
vaisseau doit tourner.

Chaque mission reste étroite, et ce qu'elle ne fait PAS compte autant que ce qu'elle fait.
Celle qui crée le savoir ne range pas l'arbre. Celle qui range ne crée rien. Celle qui
doute ne corrige rien — elle expose. Celle qui relie ne juge pas la véracité. Celle qui
archive ne supprime jamais seule.

Cette séparation n'est pas de la bureaucratie : empiler des rôles ne compose pas des
compétences, ça compose des taux d'erreur. Un rôle étroit a une surface d'erreur étroite,
et se vérifie séparément. Le regroupement en familles ne l'a pas relâchée : la table des
droits (`hooks/robots_permissions.py`) reste indexée par **mission**, si bien que le
challenger n'écrit toujours que `state/challenges.json` même s'il embarque sur le même
vaisseau que l'architecte.

Les noms sont ceux des vaisseaux de la saga *Alien*, choisis le 20/09/2026. Trois d'entre
eux viennent d'un seul écrivain, Joseph Conrad, comme dans les films. Ce sont des **noms
propres**, donc ils ne se traduisent pas : c'est exactement ce qu'exige l'ADR-0013, et
c'est la traduction de `distillateur` en `distiller` qui avait rendu cinq agents
introuvables le 19/08. Le raisonnement complet est dans
`projects/claude-brain/renommage-agents-familles-2026-09-20.md`.

Sous-agents Claude Code natifs. Fichiers canoniques **versionnés ici** ; le dossier
`~/.claude/agents/` pointe dessus pour la découverte par Claude Code.

## Les quatre vaisseaux

### 🛠 [NOSTROMO](nostromo.md) — la machine

Le remorqueur industriel : salle des machines, réacteur, câblage. En italien, *nostromo*
veut dire « maître d'équipage » — celui qui fait marcher le navire et ne décide jamais de
la cargaison. C'est sa frontière exacte.

- **`mecanicien`** — répare l'infra machine : hooks, câblage, symlinks, capsule. *Jamais
  le contenu des fiches.*
- **`machiniste`** — tient la machine physique froide : RAM, CPU, chaleur, autonomie,
  process abandonnés, animations permanentes. *Ne touche ni au savoir ni à l'infra
  logicielle du Brain.*

### ⚗️ [NARCISSUS](narcissus.md) — la fin de session

La navette où Ripley enregistre le dernier rapport de la mission avant de se mettre en
sommeil. C'est le métier de cette famille : consigner, puis ranger.

- **`distillateur`** — crée le savoir : transforme les sessions brutes
  (`sessions/archive/`, transcripts) en fiches et leçons propres, ou met à jour
  l'existant. *Ne range pas l'arbre globalement.*
- **`jardinier`** — range l'arbre : déduplique, garantit que chaque fiche est dans la
  carte (`MEMORY.md` + `lessons/INDEX.md`), tisse et répare les liens `[[...]]`
  **évidents**, masque les secrets, traite cohérence et utilité. *Ne crée pas de savoir.*

### 🔭 [SULACO](sulaco.md) — la veille du savoir

Le transport qui amène une équipe de spécialistes vérifier ce qui se passe vraiment sur
place, et qui n'en débarque qu'un groupe à la fois. C'est aussi sa mécanique réelle : la
veille ne réveille jamais qu'une mission par passage.

- **`challenger`** — met le savoir à l'épreuve : traque le périmé, le faux, le contredit,
  le survendu ; produit des doutes étayés dans `state/challenges.json`. *Ne corrige rien —
  il doute.*
- **`architecte`** — cohésion **globale** : lit toute la topologie du graphe
  (`hooks/brain_topology.py`) pour tisser les liens **manquants**, relier les fiches
  isolées, raccrocher les îlots détachés, privilégier les ponts inter-domaines. *Vue
  d'ensemble, là où le jardinier range fiche par fiche.*
- **`archiviste`** — gère le froid : fraîcheur, péremption, archivage du poids mort (via
  `state/utility.json`). *Propose, ne supprime jamais.*

### 🕸 [ANESIDORA](anesidora.md) — la synthèse à la demande

Le navire de récupération qui part chercher la boîte noire du Nostromo, la lit, et repart
de ce qu'elle contient. Son nom est une épithète grecque : « celle qui fait remonter les
cadeaux », depuis le sol. Il ne tourne sur aucun horaire et ne se lance qu'à la main.

- **`synthetiseur`** — savoir de second ordre : relie un thème transverse à travers
  plusieurs projets en un essai dense (`lessons/`). *Crée la vision d'ensemble qu'aucune
  fiche ne dit seule.*

> **Huit missions = une équipe (séparation des pouvoirs).** Le distillateur *écrit*, le
> jardinier *range* (local), l'architecte *relie* (global), le challenger *doute*, le
> synthétiseur *synthétise*, l'archiviste *élague*, le mécanicien *répare l'infra*, le
> machiniste *tient la machine*. Aucune ne fait le travail d'une autre — c'est ce qui
> garde le système sûr et auditable, et le regroupement en vaisseaux n'a rien changé à
> cette table-là.

## Comment les lancer

Dans n'importe quelle session Claude Code, en langage naturel :
- « **lance le NARCISSUS** sur ma dernière session » → distillation puis rangement.
- « **lance le SULACO** » → la veille du savoir passe sur l'arbre.

Ou en nommant le vaisseau comme sous-agent, avec la mission dans la consigne :
`--agent narcissus` + une consigne qui commence par la mission voulue. En lancement
automatique, le moteur n'envoie au modèle que la section `## MISSION — <nom>` demandée —
le fichier entier coûterait les autres missions à chaque réveil.

Flux type après une grosse session :
1. `narcissus` en mission `distillateur` extrait les fiches de la session,
2. `narcissus` en mission `jardinier` vérifie qu'elles sont rangées, liées, et dans la carte.

## Réinstaller la surface (autre machine / après git clone)

```bash
mkdir -p ~/.claude/agents
# symlinke TOUS les vaisseaux (sinon les non-listés restent muets après un git clone)
for a in ~/.c-brain/trunk/agents/*.md; do
  [ "$(basename "$a")" = "readme.md" ] && continue
  ln -sf "$a" ~/.claude/agents/"$(basename "$a")"
done
```

## Évolutions possibles

- Régler `model:` (sonnet par défaut pour le coût ; passer à opus pour un jardinage ou une
  distillation plus fins). Le modèle réel d'une passe automatique est choisi **par
  mission** au lancement, pas par le `model:` du vaisseau.
- ~~Un agent « tisseur » dédié aux liens inter-projets~~ → **fait** : c'est la mission
  `architecte` du SULACO (2026-06-24).
- ~~Brancher l'architecte dans l'orchestrateur autonome pour une veille de cohésion
  périodique~~ → **fait** : `hooks/brain_upkeep.py` (2026-06-24).

## Seconde couche autonome — la veille de cohésion

Au-delà du duo SessionEnd porté par le NARCISSUS (`distillateur → jardinier`), une
**seconde couche** entretient le tronc toute seule via `hooks/brain_upkeep.py`, appelé en
fin de chaque maintenance. Elle est portée par le SULACO et le NOSTROMO :

1. **régénère les capteurs mécaniques** (gratuits, zéro LLM) : `brain_topology.py`,
   `brain_utility.py` (+ `coherence.json` accumulé) ;
2. chaque mission de veille n'est **éligible** que si **son capteur dépasse un seuil**
   (vrai travail) **et** que son **cooldown** (12 h) est respecté ;
3. on réveille **au plus UNE mission par passage** (garantie de coût : ~1 run LLM en plus,
   seulement quand il y a matière), par priorité **challenger → architecte → archiviste →
   mécanicien** (`brain_upkeep.ORDER`).

C'est ce point 3 qui explique une observation de l'auteur le 20/09 : les agents « ne
fonctionnent pas ensemble ». Ce n'est pas une panne, c'est la règle — mesuré le même jour,
`challenger`, `architecte` et `mecanicien` étaient éligibles au même instant et un seul a
été réveillé.

Seuils : architecte (≥1 isolée OU ≥3 placements douteux OU ≥2 composantes OU ≥8 liens
manquants) · challenger (≥1 **paire `(a,b)`** à arbitrer dans `coherence.json` — les notes
d'arbitrage ne comptent pas) · archiviste (≥3 fiches en poids mort) · **mecanicien (≥1
défaut dans `doctor.json`)**. Sur la durée, toutes les dimensions finissent tendues à tour
de rôle. Best-effort : si une mission de veille échoue (quota/login), la passe est sautée —
aucune donnée perdue (≠ distillation). Debug à sec : `python3 hooks/brain_upkeep.py decide`.

> ⚠️ **La mission `mecanicien` EST branchée en autonome** (depuis 2026-06-24). Elle tourne
> en `sonnet` avec les outils `Edit/Write/Bash` : elle peut donc **modifier l'infra toute
> seule** quand `brain_doctor` signale un défaut. Sa consigne (`brain_upkeep.TASKS`) la
> borne aux défauts listés par le docteur et lui interdit de toucher hooks, settings ou
> symlinks sauf pointage explicite. C'est la seule mission de veille dont une passe ratée
> n'est pas rejouable à l'identique — la surveiller via `sessions/gardening.log`.

Reste optionnel : brancher l'ANESIDORA (`synthetiseur`) — pas de capteur, déclenché par
densité thématique, pas par défaut.

**Journal par mission** : chaque réveil écrit une ligne dans `state/agents.jsonl`, avec la
mission, le vaisseau, la couche et la durée. Depuis le 20/09/2026, la **couche 1** y écrit
aussi : avant cette date, seule la couche 2 journalisait, si bien que le distillateur et le
jardinier — les deux plus sollicités — n'apparaissaient nulle part.

**Garde mécanique post-jardinage** (zéro LLM) : `auto_maintain` relance
`brain_doctor --json` juste après la mission `jardinier` et trace
`[doctor] … post-jardinage: N defaut(s)` dans `sessions/gardening.log` si `N != 0`. Le
jardinier ne peut plus être seul juge de sa propre passe.

**Invariants** : `python3 tests/invariants_brain.py` — capteurs qui redescendent, tolérance
aux entrées legacy, doc↔code, modèle par mission, et le raccord entre les vaisseaux appelés
et ceux qui existent là où Claude Code les cherche. Lancé par `hooks/selftest.sh`.
