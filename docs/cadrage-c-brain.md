# Cadrage — C Brain (Claude Brain installable et auto-mis-à-jour)

**Niveau de dosage : C léger.** Justification : la cible est privée-sur-invitation, mais un clone
est irréversible (retirer l'accès ne reprend pas ce qui est déjà cloné), et la source du paquet
est un système qui contient des PII réelles de tiers — cf. `pii-reelle-dans-brain-decouverte-anonymisation`.
La mise à jour automatique ajoute un second risque de niveau C : **du code qui s'installe tout seul
chez quelqu'un d'autre**.

**TL;DR** — Extraire du `~/claude-brain` vivant un paquet **C Brain** installable en une commande
sur une autre machine macOS, au fonctionnement **identique** à celui de Dylan, avec toutes ses
dérivées (hooks, agents, capsule, planète, companion, statusline, CLI, launchd), et **capable de
se mettre à jour tout seul** chez chaque utilisateur.

**Décisions Dylan actées (2026-07-26)** : nom **C Brain** · privé sur invitation · nouveau repo
propre · socle + planète + companion + **statusline** · **pas** les skills ·
`Yuno15-bb/bbly-agents` **supprimé une fois C Brain en ligne et vérifié**.

---

## Pour qui, et pour quoi

**Public** : les utilisateurs d'un agent en ligne de commande — Claude Code d'abord, mais aussi
tout autre modèle qui tourne dans un CLI — qui veulent **plus de mémoire, plus de contexte, et un
arbre de connaissance qui grandit avec le temps et la masse de travail** accumulée avec leur agent.

Ce n'est pas un outil de plus : c'est ce qui fait qu'une session ne repart pas de zéro, et que ce
qui a été compris une fois reste trouvable depuis n'importe quel autre projet.

**Installation** : l'utilisateur ne suit pas une procédure. Il donne **une commande à l'agent qui
tourne déjà dans son CLI**, et l'agent installe. C'est le mode d'emploi le plus court possible, et
il correspond à la façon dont ce public travaille déjà.

**Contrainte honnête, à ne pas maquiller** : le tronc, les agents, la CLI, la planète et la capsule
sont portables partout. En revanche le **câblage automatique** (hooks `SessionStart` /
`SessionEnd` / `PostToolUse`, statusline) passe par `~/.claude/settings.json` et n'existe que dans
Claude Code. Sur un autre CLI, C Brain fonctionne **à la demande** (`brain recall`, `brain status`,
les agents invoqués explicitement) mais **pas en boucle fermée automatique**. L'installeur doit le
détecter et le dire, jamais laisser croire à un système autonome qui ne l'est pas.

## Problème (le besoin, pas la solution)

Le Brain ne fonctionne aujourd'hui que sur **cette** machine, et son installation n'est pas un
artefact : c'est une suite de gestes manuels reconstituée de mémoire.

- La restauration du 2026-07-22 sur le Mac neuf l'a prouvé : le symlink `~/.claude/agents`
  n'a jamais été recréé → **7 agents invisibles, boucle autonome à vide pendant 24 h**, sans
  aucune erreur visible (`capsule-clignote-agents-non-resolus`).
- Le `.plist` de reprise portait `/Users/<ancien-nom>` en dur → planificateur mort silencieusement.
- Personne d'autre ne peut faire tourner le système, donc il n'est ni montrable ni transmissible.
- Et une fois installé chez quelqu'un, **il se fige** : les corrections faites ici ne l'atteignent
  jamais. Un système figé chez un tiers est pire qu'absent — il porte les bugs déjà réparés.

Le besoin : **qu'une autre personne obtienne le même système en marche, que ça se prouve, et que
ça reste à jour sans qu'elle ait rien à faire.**

## Succès mesurable

Sur un `HOME` isolé (test) puis une machine tierce :

| Critère | Seuil |
|---|---|
| Installation | `git clone && ./install.sh` — **0 geste manuel** hors mot de passe admin, < 10 min |
| Santé | `brain selftest` **vert**, `brain doctor` sans erreur |
| Hooks actifs | une session Claude Code de test déclenche recall + archivage (prouvé par `state/`, pas par la doc) |
| Agents résolus | les 4 vaisseaux listés par Claude Code (le piège du 22/07 est détecté par l'installeur) |
| Capsule | fenêtre Electron qui s'anime sur un changement de `state/status.json` |
| Planète | double-clic sur le `.command` → globe servi sur `localhost:8765` |
| Statusline | ligne d'état visible dans Claude Code, même rendu que chez Dylan |
| Idempotence | 2ᵉ exécution de `install.sh` = 0 dégât, `settings.json` non écrasé |
| **Mise à jour** | une correction poussée ici arrive chez l'utilisateur **au démarrage de session suivant**, sans intervention, **sans toucher une seule de ses fiches** |
| **Rollback user** | `brain update --rollback` restaure la version précédente en 1 commande |
| Fuite | `leakcheck` : **0 marqueur** PII/secret dans le repo, historique git compris |

## Non-Goals (bornes explicites)

- **Aucun contenu de fiches.** Le paquet livre un tronc **vide**. Personne ne clone le cerveau de Dylan.
- **Pas les skills** (`~/.claude/skills`) — trop personnels. Vérifié le 2026-07-26 : **20 skills
  sur 20** contiennent des marqueurs perso (client, personnes, cadre d'accompagnement). Aucun n'est
  transférable. Ce qui est livré à la place : `skills/` **vide** + `skills/README.md`, la doc du
  **standard de fabrication** (9 exigences, forge-sur-blocage, frontière skill/agent, gabarit).
  On transmet la méthode qui fabrique le skill, pas le skill.
- **Pas `desktop_sync.py`** ni son plist : sauvegarde du Bureau de Dylan vers *son* GitHub,
  strictement perso et dangereux chez un tiers (`--delete` sur une destination inconnue).
- **Pas de publication publique**, pas de listing GitHub, pas de vitrine marketing.
- **macOS uniquement** (launchd, Electron, `open`). Pas de Linux/Windows.
- **Pas de télémétrie.** La mise à jour est un `git pull`, elle ne remonte **rien**.
- **Pas de migration forcée du Brain de Dylan** vers la nouvelle disposition (voir « Impact »).
- **Pas le corpus froid ni le venv embeddings** : optionnels, BM25 suffit par défaut.

## Approche

### 1. La décision structurante : séparer le MOTEUR du TRONC

C'est ce qui rend la mise à jour automatique possible **sans risque pour les données**.

Aujourd'hui `~/claude-brain` mélange le code (hooks, agents, capsule, planète) et le contenu
(fiches). Un `git pull` sur un dépôt où l'utilisateur commite ses propres fiches finirait
inévitablement en conflit — ou en perte.

```
~/.c-brain/engine/     ← clone de C Brain. Code SEUL. git pull sans conflit possible.
~/.c-brain/trunk/     ← tronc de l'utilisateur. Ses fiches, son git à lui. JAMAIS touché.
    hooks/  → symlink vers ~/.c-brain/engine/hooks
    agents/ → symlink vers ~/.c-brain/engine/agents
    capsule/ planet/ companion/ → symlinks
    lessons/ projects/ meta/ life/ sessions/ state/ → RÉELS, à l'utilisateur
```

Les chemins deviennent `~/.c-brain/trunk/hooks/...` : **aucun hook, aucun agent, aucun chemin n'est
modifié**. Le fonctionnement est identique, seule la provenance des fichiers change.

### 2. La mise à jour automatique

- `brain update` : `git pull` dans `~/.c-brain/engine`, puis **re-joue `install.sh`** (idempotent
  par construction — il sait déjà ne rien écraser). Les symlinks rendent la propagation immédiate.
- **Déclenchement auto** : un hook `SessionStart` vérifie au plus **1×/24 h** (throttle sur un
  fichier d'horodatage) s'il existe un tag plus récent. Vérification en tâche de fond, jamais
  bloquante, échec silencieux si pas de réseau.
- **Versions taguées, pas `main`** : l'utilisateur suit les tags `vX.Y.Z`, pas la branche de
  travail. Un commit de brouillon ne part chez personne.
- **Migrations** : un dossier `migrations/` numéroté, chaque script idempotent et **jamais
  destructif** sur `lessons|projects|meta|life|sessions`. Un compteur dans `~/.c-brain/state`.
- **Rollback** : `brain update --rollback` fait un `git checkout` du tag précédent + re-`install.sh`.

### 3. La généralisation est déclarative, pas manuelle

`sync.sh` recopie le moteur depuis le Brain vivant à chaque passe : **une correction faite à la
main serait écrasée**, et la fuite reviendrait au commit suivant sans que rien ne le signale.
D'où `rules.json` + `generalize.py`, **enchaîné automatiquement après chaque copie**, avec une
garde : une règle qui trouve moins d'occurrences que prévu fait **échouer** le script — un
compteur qui baisse veut dire que la source a changé de formulation, pas que le problème a disparu.

### Ce que la séparation moteur/tronc a cassé (trouvé en exécutant, pas en relisant)

Deux fois le même piège : du code qui dérive ses chemins de `__file__` au lieu de `$HOME`.
Sous symlink, il pointe alors dans le **moteur** au lieu du **tronc**.

- `tests/invariants_brain.py` écrivait `state/coherence.json` **dans le dépôt installé** → 3 tests
  en erreur. Corrigé par une règle : deux racines distinctes, `CODE` (suit le fichier) et `BRAIN`
  (dérive de `$HOME`). Les 22 autres usages de `__file__` servent à localiser du **code** voisin —
  eux sont corrects et le restent.
- `planet/graph.json` est régénéré **dans le moteur**. Toléré : il est gitignoré et reconstruit à
  chaque lancement. À ne jamais étendre à des données de l'utilisateur.

### Ce que le L2 a rattrapé (deux échecs silencieux)

- **Statusline installée et invisible** : le fichier était copié dans `~/.claude` mais la clé
  `statusLine` n'était jamais écrite dans `settings.json`. Rien n'aurait signalé l'erreur — juste
  une ligne d'état absente. Corrigé, et posée **seulement** si l'utilisateur n'en a pas déjà une.
- **`brain update` annoncé mais inexistant** : le récapitulatif d'installation le listait alors
  que la commande arrive au L6. Retiré du message plutôt que promis à vide.

### Alternatives rejetées

| Alternative | Pourquoi non |
|---|---|
| **Un seul dépôt code+contenu, `git pull` dessus** | L'utilisateur commite ses fiches dans le même repo → conflit garanti au 1ᵉʳ update, perte de fiches au pire. C'est le cœur du problème, pas un détail. |
| **Mettre à jour `bbly-agents`** | Son historique (3 commits, juin) a porté du contenu perso ; `git log -p` le ressort même après nettoyage. → nouveau repo, et **`bbly-agents` supprimé** une fois C Brain vérifié. |
| **Publier le Brain lui-même avec un `.gitignore`** | Une liste noire laisse passer par défaut. Un seul fichier oublié = fuite de PII client. La liste blanche refuse par défaut. |
| **Copie des fichiers au lieu de symlinks** | Chaque update devrait re-copier et deviner ce que l'utilisateur a modifié localement. Le symlink rend la frontière code/contenu **physique**, donc non-négociable. |
| **Mise à jour silencieuse sur `main`** | Du code non relu s'installe chez un tiers. Les tags forcent une décision explicite de publication. |
| **Installeur en Python / Makefile** | Le point d'entrée doit tourner sur un Mac neuf **avant** toute installation ; `bash` est garanti, un venv Python ne l'est pas. |
| **Copie manuelle à chaque mise à jour** | Dérive garantie entre le Brain vivant et le paquet, sans signal — `contrat-copie-entre-repos-derive-silencieuse`. D'où `sync.sh --check` qui échoue si le paquet a divergé. |

## Contrat (ce sur quoi le reste s'appuie)

```
c-brain/
  install.sh          # point d'entrée unique, idempotent, backup avant tout écrasement
  uninstall.sh        # retour à l'état d'avant, en 1 commande
  sync.sh             # ~/claude-brain → repo, liste blanche ; --check = diff seul
  generalize.py       # applique rules.json APRÈS la copie (enchaîné par sync.sh)
  rules.json          # 20 règles déclaratives : 3 blocs de code + 17 substitutions
  leakcheck.py        # 0 marqueur, sinon exit 1 (bloque le commit)
  brain               # CLI (status|doctor|audit|review|recall|next|selftest|update|push…)
  hooks/              # 28 hooks + .plist.template  (desktop-sync EXCLU)
  agents/             # 4 vaisseaux .md + le guide, 8 missions dedans, généralisés
  capsule/            # Electron, sans node_modules, sans assets morts
  planet/             # index.html, launch.sh, graph_export.py, media/  (graph.json EXCLU)
  companion/          # panneau live des diffs
  statusline.py       # ligne d'état Claude Code
  migrations/         # 001-*.sh … numérotées, idempotentes, non destructives
  skeleton/           # tronc VIDE à créer chez l'utilisateur (.gitkeep)
  skills/             # VIDE + README.md = le standard de fabrication (aucun skill livré)
  docs/               # ce cadrage + README d'installation
  VERSION             # tag courant, lu par brain update
```

**Invariants du contrat** (vérifiés par `selftest`, pas par la relecture) :
- aucun chemin absolu `/Users/<qqn>` dans un fichier exécuté — tout dérive de `$HOME` ;
- `state/`, `planet/graph.json`, `capsule/node_modules/`, `corpus/`, `.venv/` jamais commités ;
- `install.sh` relancé 2× donne le même état ;
- **aucun script du moteur n'écrit dans `lessons|projects|meta|life`** — sauf les agents, seul
  chemin d'écriture légitime, qui passent par le tronc de l'utilisateur.

## Impact & risques

- **Risque n°1 — fuite de PII de tiers.** `planet/graph.json` (1,4 Mo) contient le **texte
  intégral des fiches**, noms de clients compris ; il est régénéré à chaque lancement. Exclu par
  la liste blanche *et* par `.gitignore` *et* attrapé par leakcheck. Triple filet.
- **Risque n°2 — l'auto-update est un canal d'exécution de code chez un tiers.** Parades :
  tags uniquement, jamais `main` ; migrations non destructives par construction ; rollback en
  1 commande ; le hook ne bloque jamais la session s'il échoue.
- **Risque n°3 — le moteur nomme encore son auteur et ses clients.** Mesuré après le L0 :
  **50 occurrences sur 16 fichiers**. Ce n'est pas cantonné aux agents — `hooks/archive_session.py`
  porte une table de mots-clés → projets perso (8 occurrences), `capsule/index.html` cite le
  propriétaire 5×, `hooks/brain_review.py` 5×, `graph_export.py` 6×. C'est le vrai contenu de L1.
- **La machine de Dylan reste la source de vérité** et **ne migre pas** vers la disposition
  moteur/tronc dans un premier temps : son Brain est en production avec 10 hooks actifs, on ne
  le refactore pas pour livrer. `sync.sh` pousse son état vers C Brain. Migration éventuelle
  ensuite, une fois C Brain éprouvé sur une machine tierce.
- **Poids mort** : `capsule/assets/UAL.glb` (7,3 Mo) n'est référencé ni par `index.html` ni par
  `main.js` — même constat qu'en juin, l'asset est revenu. À ne pas embarquer.
- **Dette connue** : `hooks/brain_paths.py` (helper d'extraction créé en juin) n'existe plus dans
  le Brain courant ; les hooks dérivent correctement de `$HOME` via `expanduser`, donc acceptable.
- **Piège outillage (rencontré au L0)** : macOS 27 fournit **openrsync**, pas GNU rsync. Sur un
  fichier *seul*, `--dry-run --itemize-changes` signale toujours un transfert → fausse divergence
  permanente. `sync.sh` compare les fichiers isolés avec `cmp`, jamais avec rsync.
- **Poids mort confirmé** : `capsule/assets/` (7,4 Mo) est **entièrement mort** — le sprite de la
  créature est inline dans `index.html` (grille `BODY`), aucun fichier de `assets/` n'est
  référencé par le code. Même constat qu'en juin ; exclu par la liste blanche.
- **TCC macOS** : tout ce qui passe par launchd et lit `~/Desktop` sera refusé sans Accès complet
  au disque — action GUI non scriptable, à écrire dans la procédure d'installation
  (`launchd-tcc-desktop-operation-not-permitted`).
- **Coût** : nul (repo privé, pas de serveur, l'update est un `git pull`).

## Réversibilité / kill-switch

- **Avant le 1ᵉʳ push** : tout est local, `rm -rf` suffit.
- **Après invitation** : retirer l'accès collaborateur **ne reprend pas** ce qui est cloné →
  le kill-switch réel, c'est le leakcheck **avant** le push, pas après.
- **Update foireux** : `brain update --rollback` (tag précédent + re-install). Et retirer le tag
  côté GitHub stoppe la propagation aux utilisateurs qui n'ont pas encore tiré.
- **Côté machine invitée** : `uninstall.sh` + backup horodaté de `settings.json` → retour à l'état
  d'avant en 1 commande. Le tronc de l'utilisateur n'est jamais supprimé.
- **Côté machine de Dylan** : aucun risque — le pipeline est en lecture seule sur `~/claude-brain`.

## Découpage (lots mergeables, chacun testable seul)

| Lot | Contenu | Fini quand |
|---|---|---|
| **L0** ✅ | `sync.sh` (liste blanche) + `leakcheck.py` + `.gitignore` + `skills/` | outils livrés et **exécutés** : `sync --check` prouvé sur 3 divergences simultanées, leakcheck rouge à 50 (= il voit) |
| **L1** ✅ | `generalize.py` + `rules.json` (20 règles) + `skeleton/` | **leakcheck vert** (50 → 0) ; `selftest` + `doctor` + `recall` + `graph_export` **verts en HOME isolé** |
| **L2** ✅ | `install.sh` + `uninstall.sh` + `merge_settings.py` + `INSTALL.md` | cycle complet prouvé en HOME isolé : 2ᵉ passe = 0 changement ; `settings.json` revient **sémantiquement identique** après désinstallation — toutes tes clés reviennent, aucune des nôtres ne reste. Pas à l'octet près : la désinstallation réécrit le fichier via le sérialiseur JSON de Python, donc une mise en forme à la main revient reformatée (corrigé en v1.13.0) ; fiche utilisateur intacte |
| **L3** ✅ | Capsule + statusline | capture d'écran : `DISTILLING` puis `IDLE` sur changement de `status.json` ; 3 composants alignés sur le même chemin |
| **L4** ✅ | Planète + `.command` Bureau | `launch.sh` → `200` sur index/graph/glb ; capture headless du globe + légende |
| **L5** ✅ | Companion | hooks pre/post rejoués : `+3 −1` agrégé, statusline à **2 lignes** |
| **L6** ✅ | `brain update` + `check_update.py` + `migrations/` + `VERSION` | dépôt distant factice, 2 tags : mise à jour, migration jouée 1× seule, rollback, fiche intacte à chaque étape |
| **L7** ✅ | README + `docs/verification.md` + `publish.sh` + dépôt en ligne | `Yuno15-bb/c-brain` **privé**, `v1.0.2` publiée · clone depuis GitHub → `install.sh` → selftest + doctor **verts** |

**Reste un seul geste, non scriptable** : la suppression de `bbly-agents` exige le droit
`delete_repo`, accordé par une authentification interactive (`gh auth refresh -h github.com -s
delete_repo`), puis `gh repo delete Yuno15-bb/bbly-agents --yes`.

Chemin critique : **L0 → L1 → L2 → L6**. L3/L4/L5 se parallélisent après L2.
`bbly-agents` n'est supprimé qu'**après** C Brain en ligne et vérifié — jamais avant.

## Open Questions (non tranchées)

1. **Signature des tags** : GPG (`~/.gnupg` existe déjà) ou simple tag annoté ? Le premier prouve
   que la mise à jour vient bien de toi, le second est plus simple.
2. **`brain_paths.py`** : réintroduire le helper dans le Brain courant (une seule source de vérité)
   ou laisser chaque hook faire son `expanduser` ? Impacte le Brain réel → hors périmètre par défaut.
3. **Cadence de `sync.sh`** : à la main, ou un hook qui alerte quand le paquet a divergé du Brain
   de plus de N jours ?
4. **Le tronc vide est-il vraiment vide ?** Un `MEMORY.md` d'exemple et 2-3 fiches de démonstration
   aideraient un nouvel utilisateur à comprendre le format — mais il faut les **écrire**, pas les
   extraire des tiennes.

---

*Cadré le 2026-07-26. À relire à froid avant d'écrire la première ligne de L0.*
