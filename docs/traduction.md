# Deux branches, un moteur

`main` est en **anglais**. `fr` est en **français**, et c'est la branche sur
laquelle le moteur est extrait.

```
~/claude-brain (français)  ──sync.sh──▶  fr  ──traduction──▶  main (anglais)
     le Brain vivant                                    ce que les gens installent
```

## Pourquoi ce sens et pas l'autre

Le Brain source est écrit en français : ses hooks, les prompts de ses agents,
ses commentaires. `sync.sh` copie depuis lui et `generalize.py` le réécrit avec
des règles qui **matchent des chaînes françaises**. Ni l'un ni l'autre ne peut
tourner contre des fichiers anglais.

L'anglais ne peut donc pas être la cible du sync. Il en dérive, un cran plus loin.

## Le garde-fou

`./sync.sh` **refuse de tourner sur `main`**. Sans ce garde-fou, un seul sync
écraserait en silence chaque fichier traduit par son original français — et rien
ne l'attraperait : aucun test ne lit de la prose. Seul un lecteur le
remarquerait, bien plus tard.

```
❌ ./sync.sh tourne sur la branche `fr`, pas sur `main`.
```

`CBRAIN_ALLOW_SYNC_ON_MAIN=1` le force, pour le cas rare où tu sais pourquoi.

## Ce que le sync ne prend PAS

Trois fichiers vivent **uniquement dans le paquet** et sont exclus du sync,
parce que `rsync --delete` les effacerait à la première passe :

| Fichier | Pourquoi il n'est pas dans le Brain vivant |
|---|---|
| `hooks/hooks.json` | manifeste de hooks du plugin Claude Code |
| `tests/plugin_manifest.py` | vérifie les manifestes du paquet |
| `tests/english_only.py` | surveille la traduction, sur `main` seulement |

C'est le pire défaut possible ici : un `hooks.json` effacé ne plante pas, le
plugin **arrête simplement d'enregistrer**.

## Enchaînement quand le Brain évolue

```bash
git checkout fr
./sync.sh                  # copie + généralisation, français
python3 leakcheck.py       # doit être vert
git commit -am "sync : <ce qui a bougé>"

git checkout main
git diff fr@{1} fr -- .    # ce qui a réellement changé
# porter ces changements, traduits, sur main
python3 leakcheck.py --history
./publish.sh v1.2.0 "..."
```

Lis le diff avant de traduire. La plupart des syncs déplacent une poignée de
lignes ; un `git merge fr` aveugle ramènerait tout l'arbre français sur `main`.

## Ce qui n'est PAS traduit, volontairement

Trois fichiers sont **identiques octet pour octet sur les deux branches** et
restent en français :

| Fichier | Pourquoi |
|---|---|
| `sync.sh` | il lit le Brain vivant de l'auteur, qui est en français |
| `rules.json` | les motifs français SONT son métier, et sa prose les documente |
| `.sync-manifest` | une empreinte de la SOURCE, pas du paquet |

`rules.json` est inerte sur `main` ; il y est gardé pour que le dépôt reste
complet et auditable, et identique pour que le porter soit un simple
`git checkout fr --`.

## Le glossaire — ce que la traduction renomme

Le moteur est traduit, et le vocabulaire qu'il ÉCRIT SUR LE DISQUE aussi. Un
portage qui renomme un côté et pas l'autre laisse la branche lire un fichier que
personne n'écrit. Voici les paires ; on complète le tableau, on ne re-tranche pas.

| sur `fr` | sur `main` | ce que c'est |
|---|---|---|
| `base_sur` / `contredit` / `remplace` | `based_on` / `contradicts` / `replaces` | relations typées du frontmatter |
| `recall-utilite.json` | `recall-utility.json` | état écrit par `recall_feedback.py` |
| `souvent-proposee-jamais-ouverte.json` | `often-suggested-never-opened.json` | état, même écrivain |
| `inacheves.json` | `unfinished.json` | état écrit par `brain_guard.py` |
| `a-revalider.json` | `to-revalidate.json` | état écrit par `fraicheur_fiches.py` |
| `SEUIL_JOURS` | `THRESHOLD_DAYS` | variable d'environnement |
| `brain_guard.py inacheves --reenfiler` | `brain_guard.py unfinished --requeue` | sous-commande |

**Ce qui n'est PAS renommé** : les noms de FICHIER des hooks
(`fraicheur_fiches.py`, `on_fiche_write.py` — `sync.sh` les copie par leur nom et
`hooks/hooks.json` les liste), et les clés de frontmatter déjà anglaises
(`name`, `description`, `born_from`, `redirectsTo`, `last_validated`). **Les
fichiers d'agents ne sont plus renommés non plus.** Ils l'étaient
(`jardinier.md` → `gardener.md`) jusqu'au 20/09/2026, et ça a coûté cher : le
19/08, cent dix-huit lancements d'agents ont échoué sans un mot parce que
`distillateur` et `distiller` étaient deux identifiants pour la même chose.
Depuis, les quatre vaisseaux portent des NOMS PROPRES — NOSTROMO, NARCISSUS,
SULACO, ANESIDORA — et un nom propre ne se traduit pas. C'est la règle posée
par l'ADR-0013 : seule la présentation dépend de la langue, jamais
l'identifiant.

## Deux outils, une garantie — et le trou entre les deux

`generalize.py` RÉÉCRIT ce qui ne doit pas sortir ; `leakcheck.py` REFUSE ce qui
ne doit toujours pas sortir. Ils ne sont pas redondants, et aucun ne couvre
l'autre :

- Une règle de réécriture peut ABÎMER ce qu'elle touche. Le filet sur le nom du
  propriétaire, un `Dylan` nu, a transformé deux en-têtes de copyright Apache en
  `(c) 2026 l'auteur Peellaert`. leakcheck ne pouvait pas le voir : il exempte
  justement les lignes de copyright de ce marqueur. Le motif est désormais
  `Dylan(?! Peellaert)`, et leakcheck couvre ce que ce négatif laisse passer
  partout ailleurs.
- **Retirer une règle ne laisse aucune trace rouge.** `banc-chemins-shell` a été
  supprimée, et `capsule/banc/cycle.sh` est aussitôt reparti en public avec
  `$HOME/claude-brain/` — le chemin privé de l'auteur. Aucun test ne lit un
  chemin dans un commentaire, aucun compteur ne bouge. Quand tu supprimes une
  règle, vérifie à la main ce qu'elle tenait.

## `main` est le produit, `fr` est une soute (2026-08-13)

`fr` était publiée comme un produit à part, avec sa famille de tags `-fr`. Ce
n'est plus le cas. Elle redevient ce qu'elle a toujours vraiment été : **la piste
d'atterrissage française du sync**, lue par personne d'autre que l'étape de
traduction.

Deux coûts l'ont décidé, mesurés le même jour :

- **Les familles de tags se percutent au tri.** `sort -V` place `v1.27.0-fr`
  APRÈS `v1.27.0` : tout sélecteur « dernière version » qui ratisse tous les tags
  fait basculer une installation anglaise sur l'arbre français — aucune erreur,
  l'outil se met simplement à parler une autre langue. Ça n'est resté invisible
  que tant que `fr` traînait derrière ; les mettre à niveau l'a ARMÉ.
- **`fr` ne peut pas sortir sans un sync propre.** Publier depuis `fr` exige que
  le Brain vivant de l'auteur colle au paquet. Un chantier en cours sur cette
  machine bloque donc une publication qui n'a rien à voir avec lui.

`publish.sh` refuse désormais de tagger depuis `fr` (`CBRAIN_ALLOW_TAG_ON_FR=1`
force le passage, pour le cas rare où tu sais pourquoi). Les tags publiés restent
publiés — en déplacer un casse le fetch de qui est encore dessus — donc la
famille `-fr` cesse simplement de grandir à `v1.27.0-fr`.

**Ce qui ne change PAS** : le sens de la chaîne. Le Brain vivant est en français
et `generalize.py` matche des motifs français, donc le sync atterrit toujours sur
`fr` d'abord, et `main` en est toujours la traduction faite par un humain qui lit
le diff. `fr` est une étape, plus une destination.

## Tags

| Branche | Tags | Qui l'installe |
|---|---|---|
| `main` | `v1.2.0` | tout le monde, par défaut |
| `fr` | `v1.2.0-fr` | les francophones qui le demandent |

⚠ **Ceci a d'abord été écrit à l'envers, et c'était un vrai bug.** Le texte
précédent affirmait que chaque install restait dans sa langue « tant que chaque
clone suit sa propre branche ». Ce raisonnement ne tient pas : `update.sh` n'a
jamais regardé la moindre branche. Il lançait
`git tag -l 'v*' | sort -V | tail -1`, et **les tags ne sont pas rangés par
branche** — il voyait donc les deux familles d'un coup. Comme `sort -V` place
`v1.18.0-fr` **après** `v1.18.0`, le maximum global était le tag français, et
une installation anglaise aurait basculé sur l'arbre français dès que `fr`
rattrapait son retard. Aucune erreur : le tag existe, le checkout réussit,
l'outil se met simplement à parler une autre langue.

Ça n'est resté invisible que parce que `fr` traînait huit versions derrière.
La remettre à niveau est ce qui l'a armé.

`update.sh` lit désormais la famille sur ce qui est installé — le suffixe du tag
posé, ou la branche suivie quand il n'y en a pas — et filtre la liste des tags
avant de trier. `tests/update_tag_family.sh` construit un dépôt jetable avec les
deux branches et le tient en CI.
