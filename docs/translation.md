# Two branches, one engine

`main` is **English**. `fr` is **French**, and it is the branch the engine is
extracted onto.

```
~/claude-brain (French)  ──sync.sh──▶  fr  ──translation──▶  main (English)
     the living Brain                                         what people install
```

## Why this direction and not the other

The source Brain is written in French: its hooks, its agent prompts, its
comments. `sync.sh` copies from it and `generalize.py` rewrites it with rules
that **match French strings**. Neither can run against English files.

So English cannot be the sync target. It is derived from `fr`, one step later.

## The guard

`./sync.sh` **refuses to run on `main`**. Without that guard, one sync would
silently overwrite every translated file with its French original — and nothing
would catch it: no test reads prose. Only a reader would notice, much later.

```
❌ ./sync.sh runs on the `fr` branch, not on `main`.
```

`CBRAIN_ALLOW_SYNC_ON_MAIN=1` forces it, for the rare case where you know why.

## What the sync does NOT take

Some files live **only in the package** and are excluded from the sync, because
`rsync --delete` would wipe them on the first pass:

Private corpus witnesses and the optional embedding sample removed during the
cleanup are excluded in the other direction: they must not re-enter the package
from the living Brain. The public test suite does not consume those files.

| File | Why it is not in the living Brain |
|---|---|
| `hooks/hooks.json` | the Claude Code plugin's hook manifest |
| `tests/plugin_manifest.py` | checks the package's own manifests |
| `tests/plugin_install.sh` | installs the package as a plugin, end to end |
| `tests/english_only.py` | watches the translation, on `main` only |
| `tests/update_tag_family.sh` | the tag families a user can be updated across |
| `tests/update_rollback.sh` | a bad update, and the way back |
| `tests/recall_benchmark.py` | recall speed, held to a number |
| `tests/recall_cache.py` | the recall cache invalidates when it should |
| `tests/docs_aligned.py` | has the code a doc describes moved since it was written |
| `tests/e2e_occupied_surfaces.sh` | installing over surfaces somebody else already holds |
| `capsule/test_lock_speaks.sh` | measures the package's own `capsule/main.js`, in English. The author's trunk has a French twin, `test_verrou_parle.sh`, measuring the author's own `main.js`: two benches, not one file translated, so both are excluded — one so the copy cannot overwrite the English bench, the other so `--delete` cannot erase it |
| `capsule/main.js`, `index.html`, `dock-geometry.js`, `test_dock_geometry.js` | the capsule as the package ships it, frozen on both sides |

This is the worst failure mode available here: an erased `hooks.json` does not
crash — the plugin simply **stops recording**.

**The list only grows, and every addition has to be made twice** — once as an
`rsync --exclude`, once in the fingerprint that `--check` compares. A file
excluded on one side only never moves but still counts as changed, so the drift
report stays red forever and says nothing useful about why.

## Workflow when the Brain evolves

**Two working copies, not one branch you keep switching.** `sync.sh` refuses to
run anywhere but `fr`; the working copy you edit sits on `main`; and switching
branches under someone who is mid-edit is worse than doing nothing. So `fr` gets
a working copy of its own, where the guard is already satisfied — satisfied, not
bypassed:

```bash
git worktree add ~/c-brain-fr fr     # once
```

```bash
cd ~/c-brain-fr
./sync.sh                  # copy + generalize, French
python3 leakcheck.py       # must be green
git commit -am "sync: <what moved>"

cd ~/c-brain            # the `main` working copy — no branch switching
git diff fr@{1} fr -- .    # what actually changed
# port those changes, translated, onto main
python3 leakcheck.py --history
./publish.sh v1.2.0 "..."
```

Read the diff before translating. Most syncs move a handful of lines; a blind
`git merge fr` would drag the whole French tree back onto `main`.

**The first half now runs on its own** (2026-08-15). At session end the author's
machine copies, leak-checks, commits and pushes `fr` without being asked. The
tool that does it is not in this package on purpose: it pushes, and it knows this
repository's branches. A user who added a remote to their own trunk never asked
for their private notes to be pushed at the end of every session.

**The second half — translating onto `main` — stays manual, and cannot be
automated.** It is the step that needs someone to read.

## `main` is the product, `fr` is a staging buffer (2026-08-13)

`fr` used to be a released product of its own, with a `-fr` tag family. It is not
any more. It stays exactly what it always really was: **the French landing strip
of the sync**, read by nobody but the translation step.

Two costs decided it, both measured the same day:

- **The tag families collide by sorting.** `sort -V` places `v1.27.0-fr` AFTER
  `v1.27.0`, so any "latest tag" selector scanning every tag moves an English
  install onto the French tree — no error, the tool just starts speaking another
  language. It stayed invisible only while `fr` lagged behind; bringing the two
  level is what ARMED it.
- **`fr` cannot ship without a clean sync.** Publishing from `fr` requires the
  author's living Brain to match the package. Unfinished work on that machine
  therefore blocks a release that has nothing to do with it.

`publish.sh` now refuses to tag from `fr` (`CBRAIN_ALLOW_TAG_ON_FR=1` forces it,
for the rare case where you know why). Published tags stay published — moving one
breaks the fetch of anyone still on it — so the `-fr` family simply stops growing
at `v1.27.0-fr`.

**What does NOT change**: the direction of the pipeline. The living Brain is
French and `generalize.py` matches French strings, so the sync still lands on
`fr` first and `main` is still translated from it by a human reading a diff.
`fr` is a step, no longer a destination.

## Tags

| Branch | Tags | Who installs it |
|---|---|---|
| `main` | `v1.2.0` | everyone, by default |
| `fr` | `v1.2.0-fr` | French speakers who ask for it |

⚠ **This used to be stated the wrong way round, and it was a real bug.** The
earlier text claimed each install stayed in its own language "as long as each
clone tracks its own branch". That reasoning does not hold: `update.sh` never
looked at a branch. It ran `git tag -l 'v*' | sort -V | tail -1`, and **tags are
not scoped to a branch** — so it saw both families at once. Since `sort -V`
places `v1.18.0-fr` **after** `v1.18.0`, the global maximum was the French tag,
and an English installation would have moved onto the French tree the moment
`fr` caught up. No error: the tag exists, the checkout succeeds, the tool just
starts speaking another language.

It stayed invisible only because `fr` lagged eight versions behind. Bringing it
level is what armed it.

`update.sh` now reads the family off what is installed — the suffix of the
checked-out tag, or the tracked branch when there is none — and filters the tag
list to that family before sorting. `tests/update_tag_family.sh` builds a
throwaway repository with both branches and holds it down in CI.

## What is not translated, on purpose

Three files need special handling when the English branch is updated:

| File | Why |
|---|---|
| `sync.sh` | its interface and comments are English on `main`; the source matching rules and package-only exclusions must be preserved |
| `rules.json` | match patterns and replacement data remain French where they must match the French source; explanations are English |
| `.sync-manifest` | a fingerprint of the source, with English package exclusions retained |

`rules.json` is inert on `main` but remains auditable. It is merged, not copied
blindly: `main` has package rules absent from `fr`. `generalize.py` checks Python
syntax after substitutions, and `sync.sh` excludes private benches and local
results from the source fingerprint. Translate explanatory text while keeping
the French match data exact. Exact private source strings are stored only as
salted digests in `digest_replacements`, matched on windows of one to three
words; a rule that needs a pattern describes the shape of the text, never the
names it replaces. No rule holds a private name in any reversible form. Until
2026-09-26 some patterns were stored as base64 (`pattern_b64`,
`replace_map_b64`): that hid the names from a text search and from nobody else,
since base64 decodes in one line. They were rewritten, and `leakcheck.py` now
decodes any `*_b64` value in `rules.json` before scanning it, so an encoded name
is refused like a name in clear.

## The glossary — what the translation renames

The engine is translated, and so is the vocabulary it writes to disk. A port
that renames one side and not the other leaves the branch reading a file nobody
writes. These are the pairs; extend the table rather than deciding again.

| on `fr` | on `main` | what it is |
|---|---|---|
| `base_sur` / `contredit` / `remplace` | `based_on` / `contradicts` / `replaces` | typed relations in a note's front matter |
| `recall-utilite.json` | `recall-utility.json` | state written by `recall_feedback.py` |
| `souvent-proposee-jamais-ouverte.json` | `often-suggested-never-opened.json` | state, same writer |
| `inacheves.json` | `unfinished.json` | state written by `brain_guard.py` |
| `a-revalider.json` | `to-revalidate.json` | state written by `fraicheur_fiches.py` |
| `SEUIL_JOURS` | `THRESHOLD_DAYS` | environment variable |
| `brain_guard.py inacheves --reenfiler` | `brain_guard.py unfinished --requeue` | subcommand |

**What is NOT renamed**: hook FILE names (`fraicheur_fiches.py`, `on_fiche_write.py`
— `sync.sh` copies them by name and `hooks/hooks.json` lists them), and the front
matter keys that were already English (`name`, `description`, `born_from`,
`redirectsTo`, `last_validated`). Agent files keep their names on both sides:
the four ships (`nostromo.md`, `narcissus.md`, `sulaco.md`, `anesidora.md`) are
proper nouns and are never translated. The missions inside them are
(`## MISSION — jardinier` → `## MISSION — gardener`), and so is the guide's
file name (`readme.md` → `README.md`).

## Two tools, one guarantee — and the gap between them

`generalize.py` REWRITES what should not ship; `leakcheck.py` REFUSES what still
should not. They are not redundant, and neither covers the other:

- A rewrite rule can damage what it touches. An earlier owner-name rule also
  rewrote Apache copyright headers. The rule now excludes the full legal
  signature, and the leak check still catches accidental owner-name mentions
  elsewhere. Copyright lines retain the legally required holder name.
- **Removing a rule leaves no red trace.** `banc-chemins-shell` was dropped, and
  `capsule/banc/cycle.sh` immediately shipped with `$HOME/claude-brain/` again —
  the author's private path. No test reads a path inside a comment, no counter
  moves. When you delete a rule, check by hand what it was holding.

## Porting glossary added after the first translation

These are source identifiers and stored values from `fr`, followed by their `main` equivalents. The `<owner>` placeholder stands for the private owner token in source filenames and topic IDs. The French strings below are data to match, not copy for user-facing output.

```text
mecanicien	mechanic
machiniste	machinist
distillateur	distiller
jardinier	gardener
challenger	challenger
architecte	architect
archiviste	archivist
synthetiseur	synthesizer
debut	start
fin	end
couche=	layer=
modele=	model=
duree_s=	duration_s=
recall-utility.json key: dernier→last
agents.jsonl keys: vaisseau→ship, raison→reason, activite→activity, modele→model, debut→start, duree_s→duration_s, cout_usd→cost_usd, jetons_sortie→output_tokens, erreur→error; phase values debut/fin→start/end
agents.jsonl verdicts: droits-indisponibles→permissions-unavailable, interrompu→interrupted, echec-code-N→failed-code-N, quota-ou-login→quota-or-login
relation types (ADR-0019): precise→refines, lie_a→related_to (joins base_sur/contredit/remplace)
state/vocabulaire-a-l-ecriture.jsonl→state/vocabulary-at-write.jsonl ; keys champ→field, ecart→gap, valeur→value, cible→target ; values sujet→topic, absent→missing, dedouble→duplicated, hors-vocabulaire→off-vocabulary, type-hors-vocabulaire→type-off-vocabulary, lie_a-sans-raison→related_to-without-reason
NOT renamed: state/a-classer.md, state/a-valider.md (main's agents and lot 1's orbe.html already use them)
generated dashboard: projects/ETAT-DES-PROJETS.md→projects/PROJECT-STATUS.md (compared lowercased)
forme_requete (recall_log keys): n_uniques→n_unique, classe_longueur→length_class, ecart_abs→gap_abs, ecart_rel→gap_rel, exaequo→ties
frontmatter key: topics_secondaires→secondary_topics
registre_ecritures: state/ecritures-fiches.jsonl→state/note-writes.jsonl, .jalon→note-writes.mark; keys ecart_s→gap_s, outil→tool; inconnu→unknown
i2_profil: state/i2-profils.jsonl→state/i2-profiles.jsonl; recall-utilite.json→recall-utility.json (main name)
capteur_depots: tag <depots-non-sauvegardes>→<unsaved-repos>; env DEPOTS_RACINES/PROFONDEUR→REPOS_ROOTS/REPOS_DEPTH; --notifier→--notify; json keys depot/chemin/niveau/sale/age_j/quand/constats/rouges→repo/path/level/dirty/age_d/when/findings/reds; rouge/vert→red/green
topics (meta/topics.json ids): preuve-et-verification→proof-and-verification, projets-clients→client-projects, le-brain→the-brain, interfaces-et-rendu→interfaces-and-rendering, machine-et-processus→machine-and-process, git-et-travail-a-plusieurs→git-and-teamwork, mise-en-ligne-et-services→deployment-and-services, travailler-avec-<owner>→working-with-the-owner, agents-et-sessions→agents-and-sessions, vie-et-carriere→life-and-career, documents-et-livrables→documents-and-deliverables, securite-et-confidentialite→security-and-privacy ; retired methodes-de-fabrication→making-methods
git_guard: CLI etat→state, journal→log ; journal keys evenement→event, quand→when ; events refus_identite_absente→refused_missing_identity, acquis→acquired, recuperation_zombie→zombie_recovery, refuse→refused, libere→released ; lock acteur→actor, demarrage→started, perimetre→scope, head_avant→head_before ; diag etat→state (libre/tenu/recuperable→free/held/recoverable), raison→reason, proprietaire→owner, pid_vivant→pid_alive, ttl_depasse→ttl_exceeded ; proprietaire_retire→removed_owner, proprietaire_actuel→current_owner, age_du_verrou_s→lock_age_s ; head_apres→head_after, head_a_bouge→head_moved, fichiers_commites→committed_files, hors_perimetre→out_of_scope, resultat_annonce→announced_result, verrou_etait_le_notre→lock_was_ours ; extra origine→origin
brain_battement: flag --fin→--end
etat_projets: projects/etat-des-projets.md→projects/project-status.md ; projects/decisions-<owner>.json→projects/owner-decisions.json (keys depuis→since, projet→project, texte→text) ; state/etat-projets.json→state/project-status.json (keys mesure_le→measured_at, depots→repos, depots_max→repos_max ; repo keys nom→name, chemin→path, dernier→last, jours→days, sale→dirty, non_pousse→unpushed, sujet→subject) ; flags --annonce→--announce, --notifier→--notify ; "## En clair" heading KEPT (data format, i18n-ok)
ronde_annonce: state/ronde-a-annoncer.json→state/round-to-announce.json (keys texte→text, ecrit_le→written_at, annonce_le→announced_at, raison→reason ; values périmée→expired, affichée→shown) ; tag <ronde-etat-projets>→<project-status-round>
commit_par_zone: commit_par_zone()→commit_by_zone() (main's name), modifies→changed ; zone values moteur/savoir/archives/racine→engine/knowledge/archives/root (main's) — tests/commit_par_zone_gouverne.py, zones_de_commit.py and the pre-commit hook table must follow
state/requete-forme.jsonl → state/query-shape.jsonl · injecte→injected · affiche→shown · seuil→threshold · demande→requested
MARQUEUR→MARKER · DEMANDES→DEMANDS · MIN_SCORE_DEMANDE→MIN_SCORE_DEMAND · demande_explicite→explicit_request · auto_arme→auto_armed · nettoyer→clean_query · journaliser_forme→log_shape · capturer_heldout→capture_heldout · humain/autre→human/other
--lignes→--lines · ouvertures_apres_suggestion→opens_after_suggestion · dernier(e)→last · classer→rank
base_sur→based_on · precise→refines · contredit→contradicts · remplace→replaces · lie_a→related_to · relations_brutes→raw_relations · topics.json nom→name
journal start/end · layer · model · duration_s · INBOX → file state/a-classer.md
carte: exclue → map: excluded
doctor keys: relations_type_inconnu→unknown_relation · relations_cible_morte→relation_dead_target · lie_a_sans_raison→related_to_without_reason · sujet_invalide/absent→topic_invalid/missing · representations_concurrentes→competing_representations · memory_trop_de_lignes→memory_too_many_lines · carte_plafond_non_remesure→map_ceiling_not_remeasured · ronde_perimee→status_round_stale · INFORMATIFS→INFORMATIONAL · ZONES_FICHES→NOTE_ZONES
state/etat-projets.json mesure_le → state/project-status.json measured_at
fixtures_conflits.json → authority_conflicts.json; fixture keys cas/chaines → cases/chains, domaine → domain, attendu → expected, pourquoi/quoi → why/description
fixture values factuelle → factual, valide/refuse → valid/rejected, synthese/reecriture → synthesis/rewrite
propagation fixture keys racine/etapes/profondeur → root/steps/depth, origine_externe → external_origin, sources_conservees → preserved_sources, web_toujours_present → web_still_present
```

The English branch also checks JSON, JSONL, TXT, CJS, YAML, TOML, and CSS for
French display text. The French retrieval queries in `tests/banc-retrieval/cas.json`
remain benchmark input. Private corpus measurements and the dated sabotage
register have been removed from the public package because no public test reads
them. The three provenance and authority fixtures remain public test inputs;
their schemas and readers use the English names above.
