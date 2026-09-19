#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# sync.sh — ~/claude-brain (Brain vivant de l'auteur, source de vérité) → dépôt C Brain.
#
# PRINCIPE : liste blanche. Ce qui n'est pas listé ici ne sort pas, point.
# Une liste noire laisserait passer par défaut ; un seul oubli = fuite de PII.
#
# Sens UNIQUE : ce script LIT ~/claude-brain et n'y écrit jamais rien.
#
# Usage :
#   ./sync.sh            copie effective
#   ./sync.sh --check    n'écrit rien, signale la divergence (sortie 1 si divergé)
set -euo pipefail

SRC="${CBRAIN_SRC:-$HOME/claude-brain}"
DEST="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CBRAIN_CLAUDE_DIR:-$HOME/.claude}"

MODE="copy"
[ "${1:-}" = "--check" ] && MODE="check"

# --itemize-changes dans les DEUX modes : le rapport doit dire ce qui a bougé,
# pas seulement ce qui aurait bougé.
# `*.bak` exclu GLOBALEMENT : une sauvegarde d'édition est, par définition, une
# version ANTÉRIEURE d'un fichier vivant — donc du code mort, et surtout du code
# qui n'est jamais repassé par generalize.py au fil des versions. Le 2026-08-15,
# `capsule/orbe.html.bak` est arrivé dans le paquet avec 5 occurrences du nom du
# propriétaire, que le leakcheck a arrêtées. Git tient déjà l'historique.
RSYNC_FLAGS=(-a --delete --itemize-changes --exclude '*.bak')
[ "$MODE" = "check" ] && RSYNC_FLAGS+=(--dry-run)

# ⚠️ GARDE-FOU DE BRANCHE — il était DOCUMENTÉ dans docs/translation.md et n'existait
# PAS dans le code. Mesuré le 2026-08-13 : un sync lancé depuis `main` a écrasé 89
# fichiers traduits par leurs originaux français et supprimé les 7 agents anglais.
# Aucun test ne lit de la prose : rien ne l'aurait signalé, seul un lecteur l'aurait vu,
# bien plus tard. Une protection écrite dans la doc mais pas dans le code n'existe pas.
BRANCHE="$(git -C "$DEST" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
if [ "$BRANCHE" = "main" ] && [ "${CBRAIN_ALLOW_SYNC_ON_MAIN:-}" != "1" ]; then
  echo "❌ ./sync.sh tourne sur la branche \`fr\`, pas sur \`main\`."
  echo "   main est la TRADUCTION : un sync l'écraserait avec le français de la source."
  echo "   → git checkout fr    (ou CBRAIN_ALLOW_SYNC_ON_MAIN=1 si tu sais pourquoi)"
  exit 1
fi

[ -d "$SRC" ] || { echo "❌ Source introuvable : $SRC"; exit 1; }
[ "$SRC" = "$DEST" ] && { echo "❌ Source et destination identiques."; exit 1; }

# --- EMPREINTE DE LA SOURCE ------------------------------------------------
# `--check` ne peut PAS comparer le paquet à la source : generalize.py réécrit
# les fichiers juste après la copie, donc ils diffèrent par construction et la
# comparaison serait rouge à jamais.
#
# La bonne question est « la SOURCE a-t-elle bougé depuis la dernière copie ? ».
# On y répond avec une empreinte des fichiers sources au moment du sync.
#
# ⚠ TOUTE exclusion posée sur un `sync_dir` plus bas DOIT être répétée ici.
# Sinon le fichier n'est jamais copié mais compte quand même dans l'empreinte :
# la source reste « changée » pour toujours et publish.sh refuse de tagger,
# sans jamais dire quoi corriger.
#
# ⚠⚠ ET ELLE DOIT ÊTRE ANCRÉE PAR `-path`, JAMAIS PAR `-name`.
# `-name` ne connaît pas de dossier : il frappe partout sous les six racines
# scannées. `! -name "index.html"`, posé le 2026-08-03 pour sortir la capsule,
# a du même coup rendu `planet/index.html` INVISIBLE à l'empreinte — le fichier
# principal de la planète. Conséquence mesurée le 2026-08-15 : la refonte
# MOTHER (122 Ko d'écart, « phosphore » 4 fois contre 0) ne faisait pas broncher
# `--check`, qui répondait « rien n'a bougé ». Le paquet public est resté sur
# une planète du 13/08 pendant que le capteur affirmait le contraire.
# Un fichier exclu à tort ici ne rougit jamais : il disparaît, en silence.
MANIFEST="$DEST/.sync-manifest"

empreinte_source() {
  {
    shasum -a 256 "$SRC/brain" "$CLAUDE_DIR/statusline.py" 2>/dev/null
    find "$SRC/hooks" "$SRC/agents" "$SRC/capsule" "$SRC/planet" \
         "$SRC/companion" "$SRC/tests" -type f \
         ! -path "*/node_modules/*" ! -name "*.pyc" ! -name ".DS_Store" \
         ! -name "*.bak" \
         ! -name "desktop_sync.py" \
         ! -name "capteur_fraicheur.py" \
         ! -name "com.dgc.fraicheur.plist.template" \
         ! -name "com.dylan.desktop-sync.plist.template" \
         ! -name "com.claudebrain.resume.plist" \
         ! -path "*/capsule/assets/*" \
         ! -path "*/capsule/lottie/*" \
         ! -path "*/capsule/hand/*" \
         ! -path "*/capsule/index.html" ! -path "*/capsule/index-v2.html" \
         ! -path "*/capsule/dock-geometry.js" \
         ! -path "*/capsule/test_dock_geometry.js" \
         ! -path "*/capsule/test_verrou_parle.sh" \
         ! -path "*/capsule/main.js" \
         ! -path "*/planet/*.json" \
         ! -path "*/planet/launch-mother.sh" \
         ! -path "*/planet/archive/*" 2>/dev/null \
      | sort | xargs shasum -a 256 2>/dev/null
  } | sed "s|$SRC/||; s|$CLAUDE_DIR/||" | sort -k2
}

if [ "$MODE" = "check" ]; then
  echo "🔄 C Brain — le Brain vivant a-t-il bougé depuis la dernière copie ?"
  if [ ! -f "$MANIFEST" ]; then
    echo "  ⚠️  aucune empreinte enregistrée — lance ./sync.sh une fois."
    exit 1
  fi
  DIFF="$(diff <(cat "$MANIFEST") <(empreinte_source) || true)"
  if [ -z "$DIFF" ]; then
    echo "  ✅ inchangé — le paquet est à jour."
    exit 0
  fi
  # Le total AVANT la troncature. Sans lui, `head -20` cachait le reste sans
  # le dire : le 2026-08-15, `planet/index.html` était bien détecté comme
  # changé mais tombait au-delà de la 20ᵉ ligne, et on lisait la sortie comme
  # « la planète, elle, n'a pas bougé ». Une liste coupée doit dire qu'elle coupe.
  CHANGES="$(printf '%s\n' "$DIFF" | grep -E '^[<>]' | awk '{print "      " $1 " " $3}' | sort -u)"
  N_CHANGES="$(printf '%s\n' "$CHANGES" | wc -l | tr -d ' ')"
  echo "  ⚠️  la source a changé — $N_CHANGES entrée(s) :"
  printf '%s\n' "$CHANGES" | head -20
  if [ "$N_CHANGES" -gt 20 ]; then
    echo "      … et $((N_CHANGES - 20)) autre(s), non affichée(s)."
  fi
  echo
  echo "  → ./sync.sh pour reporter les changements, puis relis le diff git."
  exit 1
fi

DIVERGED=0
report() {  # report <étiquette> <sortie rsync>
  if [ -n "$2" ]; then
    DIVERGED=1
    echo "  ~ $1"
    printf '%s\n' "$2" | sed 's/^/      /'
  else
    echo "  = $1"
  fi
}

sync_dir() {  # sync_dir <sous-chemin> <exclusions...>
  local rel="$1"; shift
  local excludes=()
  for e in "$@"; do excludes+=(--exclude "$e"); done
  mkdir -p "$DEST/$rel"
  local out
  # ${a[@]+"${a[@]}"} : bash 3.2 (celui de macOS) traite un tableau vide comme
  # une variable non définie sous `set -u`. Cette forme le protège.
  out="$(rsync "${RSYNC_FLAGS[@]}" ${excludes[@]+"${excludes[@]}"} \
        "$SRC/$rel/" "$DEST/$rel/" 2>/dev/null || true)"
  report "$rel/" "$out"
}

sync_file() {  # sync_file <source absolue> <destination relative>
  # PAS de rsync ici. macOS 27 fournit openrsync, qui sur un fichier SEUL en
  # --dry-run signale toujours un transfert, même à contenu identique → fausse
  # divergence permanente en mode --check. `cmp` est déterministe.
  local src="$1" dst="$DEST/$2"
  if [ ! -f "$src" ]; then
    DIVERGED=1; echo "  ! $2 — source absente ($src)"; return
  fi
  if cmp -s "$src" "$dst" 2>/dev/null; then
    report "$2" ""
  else
    report "$2" ">f  contenu différent"
    # `[ … ] && { … }` en DERNIÈRE instruction renvoie 1 quand le test est faux :
    # sous `set -e`, ça tuait le script au 1ᵉʳ fichier divergent en mode --check,
    # SANS message — on croyait le reste à jour alors que rien n'avait été scanné.
    # Le `if/fi` + `return 0` explicite ferme le trou.
    if [ "$MODE" = "copy" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$src" "$dst"
    fi
  fi
  return 0
}

echo "🔄 C Brain — synchronisation depuis $SRC"
[ "$MODE" = "check" ] && echo "   (mode --check : rien n'est écrit)"
echo

# --- 1. CLI ---------------------------------------------------------------
sync_file "$SRC/brain" "brain"

# --- 2. Hooks -------------------------------------------------------------
# EXCLUS : desktop_sync.py + son plist (sauvegarde du Bureau de l'auteur vers SON
# GitHub — perso, et destructeur chez un tiers), et le .plist non-template qui
# porte /Users/mac en dur (seul le .template part).
#
# EXCLU AUSSI : hooks.json. Il n'existe QUE dans le paquet — c'est le manifeste
# de hooks du plugin Claude Code, pas un fichier du Brain vivant. rsync tourne
# avec --delete : sans cette exclusion, le premier sync venu l'effacerait, et
# le plugin cesserait d'enregistrer QUOI QUE CE SOIT sans une seule erreur.
sync_dir hooks \
  'desktop_sync.py' \
  'capteur_fraicheur.py' \
  'com.dgc.fraicheur.plist.template' \
  'com.dylan.desktop-sync.plist.template' \
  'com.claudebrain.resume.plist' \
  'hooks.json' \
  '__pycache__' '*.pyc'

# --- 3. Agents ------------------------------------------------------------
sync_dir agents

# --- 4. Capsule -----------------------------------------------------------
# EXCLUS : node_modules (282 Mo, réinstallé par install.sh) et assets/ (7,4 Mo
# de poids MORT — vérifié le 2026-07-26 : le sprite est inline dans index.html,
# aucun fichier de assets/ n'est référencé par le code).
# EXCLUS : lottie/, index-v2.html ET main.js — la refonte V2 de la capsule
# (avatar Lottie) est un CHANTIER dans le Brain vivant, pas une fonctionnalité
# livrable. main.js y est DÉJÀ passé en V2 (il lance index-v2.html et cache la
# fenêtre au repos), donc le synchroniser publierait la V2 par la bande, sans
# les fichiers qu'elle charge. Le paquet garde la V1, qui marche.
# ⚠ Gèle aussi toute correction NON-V2 de main.js : la lever demande de porter
# la V2 en entier, pas de retirer une ligne.
# À retirer le jour où la V2 remplace vraiment index.html.
# ⚠ `hand` EXCLU — 40 Mo de MediaPipe (WASM + modèle) vendorisés pour le module
# XR expérimental. Le dossier vit sur le disque de l'auteur même quand la branche
# qui l'utilise n'est pas sortie, et rsync copie le SYSTÈME DE FICHIERS, pas ce
# que git suit : un .gitignore côté source ne protège rien ici. Sans cette
# exclusion, chaque publication embarquerait 40 Mo de binaires tiers dans un
# dépôt fait pour être cloné.
# ⚠ Posée DES DEUX CÔTÉS — ici pour la copie, et dans `source_fingerprint` pour
# l'empreinte. Un fichier exclu d'un seul côté ne bouge jamais mais compte comme
# « modifié » : le contrôle de dérive resterait rouge pour toujours.
# ⚠ `index.html`, `dock-geometry.js` et son test EXCLUS depuis le 2026-08-03 :
# la capsule du paquet, c'est l'ORBE (`orbe.html`). L'ancienne créature en pixels
# et la géométrie du Dock qui la faisait s'asseoir dessus ne sont plus chargées
# par personne ici — les garder, c'était publier du code mort, et le traduire à
# chaque version. Elles restent vivantes dans le tronc de l'auteur.
# ⚠ Le banc du verrou d'instance unique est exclu DANS LES DEUX SENS, et c'est
# deux noms différents pour une seule raison. `test_verrou_parle.sh` est celui
# de l'auteur : il mesure SON main.js, en français, avec la créature et l'orbe.
# `test_lock_speaks.sh` est celui d'ici : il mesure le main.js du paquet, en
# anglais, avec l'orbe seul. Un test suit le fichier qu'il mesure ; main.js
# étant gelé des deux côtés, son banc l'est aussi. Sans la première exclusion,
# la copie écraserait le banc anglais par le français ; sans la seconde,
# `--delete` l'effacerait purement et simplement, puisqu'il n'existe pas dans
# le tronc source. Même piège que `test_dock_geometry.js` au-dessus.
sync_dir capsule 'node_modules' 'assets' 'lottie' 'index-v2.html' 'main.js' 'hand' \
                 'index.html' 'dock-geometry.js' 'test_dock_geometry.js' \
                 'test_verrou_parle.sh' 'test_lock_speaks.sh'

# --- 5. Planète -----------------------------------------------------------
# EXCLU : *.json — TOUTES les données régénérées de la planète, pas seulement
# celles qui existaient le jour où cette ligne a été écrite.
#
# Historique, et pourquoi la règle est passée d'un NOM à un MOTIF : la ligne
# excluait `graph.json` (1,4 Mo, texte intégral des fiches, noms de clients
# compris). Le 2026-08-14, la refonte de la planète a créé `textes.json` —
# 1,5 Mo du MÊME contenu, sous un nom neuf. Il tombait hors de la règle, hors
# du .gitignore, et serait parti sur le dépôt PUBLIC au premier sync.
# C'est le motif `le-premier-fichier-d-un-type-nouveau-tombe-hors-des-regles` :
# un filtre par liste ne protège que ce qui existait quand on l'a écrit.
#
# Le paquet n'embarque AUCUN .json de planète, par construction : le globe se
# reconstruit au lancement (graph_export.py). Un .json ici est donc toujours
# une donnée du tronc de l'auteur, jamais un fichier du produit.
#
# EXCLU aussi : launch-mother.sh — un alias vers launch.sh qui n'existe que
# pour ne pas casser un raccourci du Bureau de l'auteur. Rien à en faire ici.
sync_dir planet '*.json' 'launch-mother.sh' 'archive'

# --- 6. Companion ---------------------------------------------------------
sync_dir companion '__pycache__' '*.pyc'

# --- 7. Tests --------------------------------------------------------------
# EXCLUS : les tests propres au PAQUET (manifeste de plugin, anglais seul).
# Ils n'ont pas d'équivalent dans le Brain vivant ; --delete les emporterait.
sync_dir tests 'plugin_manifest.py' 'english_only.py' 'update_tag_family.sh' \
  'recall_benchmark.py' 'recall_cache.py' 'update_rollback.sh' 'plugin_install.sh' \
  '__pycache__' '*.pyc'

# --- 8. Statusline (vit dans ~/.claude, pas dans le tronc) ----------------
sync_file "$CLAUDE_DIR/statusline.py" "statusline.py"

echo
# --- 9. Généralisation ----------------------------------------------------
# ENCHAÎNÉE, jamais optionnelle : la copie qui vient d'avoir lieu a RÉINTRODUIT
# les noms de l'auteur, de ses clients et de ses projets. Un sync sans
# généralisation laisse le paquet en état de fuite, et rien ne le signalerait
# avant le leakcheck.
echo "───"
python3 "$DEST/generalize.py"

# Empreinte écrite APRÈS la généralisation : elle atteste « voici l'état de la
# source que ce paquet reflète ». L'écrire avant laisserait croire le paquet à
# jour si la généralisation venait d'échouer.
empreinte_source > "$MANIFEST"

echo
echo "✅ Synchronisé et généralisé. Contrôle final : python3 leakcheck.py"
