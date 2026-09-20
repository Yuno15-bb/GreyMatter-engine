#!/bin/bash
# CYCLE COMPLET — fait passer l'orbe VIVANTE par tous ses états, dans l'ordre
# des familles, pour la regarder sur le vrai bureau.
#
# ⚠ CE CYCLE SE FAUSSE TOUT SEUL SI ON TRAVAILLE PENDANT. Chaque appel d'outil
#   de Claude repose `status.json` en « busy / working » via hooks/brain_battement.py :
#   l'orbe affiche alors WORKING au lieu de l'état du cycle, et la démonstration
#   ment. Le lancer DÉTACHÉ, puis ne plus rien exécuter jusqu'à la fin.
#
# ⚠ Il pilote l'orbe DÉJÀ LANCÉE — il n'en ouvre pas une. Vérifier avant :
#     pgrep -f "$BRAIN/capsule" | wc -l          (0 = rien à regarder)
#   ⚠️ le motif s'ancre sur la racine, il ne la nomme pas : écrit en dur, il ne
#      matcherait que ce tronc-ci et rendrait 0 sur la capsule d'un arbre voisin.
#
# Usage :  ./banc/cycle.sh [secondes par état]     (défaut 4)
set -u
PAUSE="${1:-4}"
BRAIN="${BRAIN_HOME:-$HOME/.c-brain/trunk}"
STATUS="$BRAIN/hooks/brain_status.py"

# L'ordre suit les FAMILLES, pas l'alphabet : on voit chaque mécanique monter en
# intensité, puis basculer dans la suivante. Un ordre alphabétique ferait sauter
# la couleur à chaque pas et le fondu de 1,4 s n'aurait plus rien à raconter.
ETATS=(
  mapping auditing architecting challenging      # Inspection   — houle
  filing archiving gardening correcting          # Organisation — balayage
  working distilling synthesizing                # Transformation — vortex
  committing                                     # Validation   — eclats
  idle                                           # Repos        — respiration
)

# Une liste d'états peut suivre la durée :  ./banc/cycle.sh 3 challenging gardening idle
# Elle sert aux TOURNAGES. Quinze secondes ne portent pas treize états : le fondu de
# mécanique dure 1,4 s, si bien qu'un état a besoin d'environ 3 s pour se montrer
# proprement. Quinze secondes = cinq états, soit un par famille — tout le vocabulaire
# de l'orbe, sans en bâcler un seul. (l'auteur, 20/09 : « chaque état doit tenir proprement
# sur les 15 secondes ».)
CONNUS=" ${ETATS[*]} "
if [ "$#" -gt 1 ]; then
  shift
  for e in "$@"; do
    case "$CONNUS" in
      *" $e "*) ;;
      # Sans ce garde, un état mal orthographié ne lève rien : brain_status.py l'accepte,
      # l'orbe ne le connaît pas et retombe sur « repos ». On filmerait un état muet en
      # croyant filmer l'autre.
      *) echo "état inconnu : $e" >&2; echo "connus : ${ETATS[*]}" >&2; exit 1 ;;
    esac
  done
  ETATS=("$@")
fi

echo "cycle : ${#ETATS[@]} états × ${PAUSE}s ≈ $(( ${#ETATS[@]} * PAUSE ))s"
for e in "${ETATS[@]}"; do
  if [ "$e" = "idle" ]; then python3 "$STATUS" idle >/dev/null
  else                       python3 "$STATUS" busy "$e" cycle >/dev/null; fi
  printf '%s ' "$e"
  sleep "$PAUSE"
done
echo
echo "fin du cycle — l'orbe est revenue au repos"
