#!/bin/zsh
# C Brain — capsule : le refus de la 2ᵉ instance doit SE NOMMER.
#
# CE QUE CE BANC MESURE. Pas un code de sortie — la SORTIE IMPRIMÉE. Le constat
# A3 du backlog C bis disait : « lancer une 2ᵉ instance → stderr nomme l'instance
# qui tient le verrou ». Mesuré le 2026-09-19 avant réparation : exit 0, 0 octet
# sur stdout, 0 octet sur stderr. Une capsule qui refuse sans rien dire est
# indiscernable d'une capsule cassée.
#
# POURQUOI ÇA NE TOUCHE PAS LA CAPSULE DE DYLAN. Le verrou d'Electron est posé
# dans `userData`, et `--user-data-dir` déplace ce dossier : le témoin et le
# refusé partagent un verrou JETABLE, dans un dossier temporaire. La capsule
# vivante garde le sien et n'est jamais ni tuée ni interrogée. (Vérifié : sous
# `--user-data-dir`, `app.getPath('userData')` suit le drapeau et le verrou
# aussi — sans quoi tout ce banc parlerait de la mauvaise instance.)
#
# ⚠️ CE BANC FAIT APPARAÎTRE UNE 2ᵉ CAPSULE À L'ÉCRAN pendant quelques secondes.
#    C'est le prix de tester la VRAIE capsule et pas une copie de sa logique :
#    le témoin doit être `main.js` lui-même, puisque c'est lui qui écrit le
#    marqueur d'identité que le refusé va lire.
#
# Lancer : ./capsule/test_verrou_parle.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ELECTRON="$HERE/node_modules/.bin/electron"
TMP="$(mktemp -d)"
ECHECS=0
PID_NODE=""; PID_APP=""

nettoie() {
  [ -n "$PID_APP" ] && kill "$PID_APP" 2>/dev/null
  [ -n "$PID_NODE" ] && kill "$PID_NODE" 2>/dev/null
  rm -rf "$TMP"
}
trap nettoie EXIT

verifie() {  # $1 = intitulé, $2 = 1 si tenu, $3 = ce qu'on a vu
  if [ "$2" = "1" ]; then print -r -- "  ✅ $1"
  else print -r -- "  ❌ $1"; print -r -- "       vu : $3"; ECHECS=$((ECHECS+1)); fi
}

# ─── le témoin : une vraie capsule qui prend le verrou jetable ───────────────
temoin() {  # $1 = script à lancer
  "$ELECTRON" "$1" --user-data-dir="$TMP/ud" >/dev/null 2>"$TMP/temoin.err" &
  PID_NODE=$!
  local i
  for i in $(seq 1 60); do
    [ -s "$TMP/ud/instance.json" ] && { PID_APP=$(sed -n 's/.*"pid":\([0-9]*\).*/\1/p' "$TMP/ud/instance.json"); return 0; }
    sleep 0.3
  done
  return 1
}

refuse() {  # $1 = script à lancer ; imprime son stderr, pose EXIT_B
  "$ELECTRON" "$1" --user-data-dir="$TMP/ud" >"$TMP/b.out" 2>"$TMP/b.err"
  EXIT_B=$?
}

[ -x "$ELECTRON" ] || { print -r -- "⏭️  electron absent — banc sauté"; exit 0; }

print -r -- "── A. le refus parle, et il nomme qui tient le verrou ──"
temoin "$HERE/main.js" || { print -r -- "❌ le témoin n'a pas pris le verrou en 18 s"; exit 1; }
refuse "$HERE/main.js"
MSG="$(cat "$TMP/b.err")"
PID_DIT="$(print -r -- "$MSG" | sed -n 's/.*pid \([0-9][0-9]*\).*/\1/p' | head -1)"

verifie "le refus n'est plus muet : stderr a quelque chose à dire" \
        "$([ -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(wc -c < "$TMP/b.err") octets"
verifie "…et rien ne part sur stdout (la sortie normale reste propre)" \
        "$([ ! -s "$TMP/b.out" ] && echo 1 || echo 0)" "$(head -c 120 "$TMP/b.out")"
verifie "…il nomme un pid, et ce pid tourne VRAIMENT une capsule" \
        "$([ -n "$PID_DIT" ] && ps -p "$PID_DIT" -o command= 2>/dev/null | grep -q capsule && echo 1 || echo 0)" \
        "pid annoncé « $PID_DIT » → $(ps -p "${PID_DIT:-0}" -o command= 2>/dev/null | head -c 90)"
verifie "…il nomme le DOSSIER d'où elle tourne (le verrou est commun à tout le Mac)" \
        "$(print -r -- "$MSG" | grep -qF "$HERE" && echo 1 || echo 0)" "$MSG"
verifie "…et il dit quoi faire pour la remplacer" \
        "$(print -r -- "$MSG" | grep -q "kill $PID_DIT" && echo 1 || echo 0)" "$MSG"
print -r -- "     (code de sortie : $EXIT_B — informatif : un refus n'est pas un échec,"
print -r -- "      l'autre instance a bien reçu l'ordre de se remontrer)"

print -r -- "── B. marqueur absent : on dit qu'on ne sait pas, on n'invente pas ──"
# Cas réel : la capsule qui tient le verrou date d'AVANT cette réparation, donc
# elle ne s'est jamais annoncée. Le refus doit le dire au lieu de se taire.
rm -f "$TMP/ud/instance.json"
refuse "$HERE/main.js"
MSG2="$(cat "$TMP/b.err")"
verifie "sans marqueur, le refus parle quand même…" \
        "$([ -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(wc -c < "$TMP/b.err") octets"
verifie "…et il avoue qu'il ne sait pas qui c'est, au lieu de nommer au jugé" \
        "$(print -r -- "$MSG2" | grep -q "pas annoncée" && echo 1 || echo 0)" "$MSG2"

print -r -- "── C. sabotage : on remet le refus muet, A doit rougir ──"
# ⚠ Le sabotage doit produire du code VALIDE. Une erreur de syntaxe ferait sortir
#   Electron en erreur avec SA propre trace sur stderr — le banc verdirait sur un
#   message qui n'est pas le nôtre, ou rougirait pour la mauvaise raison.
sed 's|^  process.stderr.write(refusExplique());$|  // muet, comme avant le 2026-09-19|' \
    "$HERE/main.js" > "$HERE/main-sabote.js"
if ! grep -q "muet, comme avant" "$HERE/main-sabote.js"; then
  print -r -- "  ❌ le sabotage n'a rien remplacé — la ligne visée a changé de forme"
  ECHECS=$((ECHECS+1))
else
  refuse "$HERE/main-sabote.js"
  verifie "SABOTAGE : sans la ligne, le refus redevient muet (donc le banc mord)" \
          "$([ ! -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(head -c 200 "$TMP/b.err")"
fi
rm -f "$HERE/main-sabote.js"

print -r -- ""
if [ "$ECHECS" = "0" ]; then
  print -r -- "✅ le refus de la 2ᵉ capsule se nomme, et le sabotage le rend muet."
  exit 0
fi
print -r -- "❌ $ECHECS contrôle(s) en échec."
exit 1
