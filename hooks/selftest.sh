#!/usr/bin/env bash
# selftest — vérifie que les hooks ne plantent pas et sortent en code 0.
# Un hook qui plante en silence est pire qu'absent : ce test l'attrape.
set -u
BRAIN="$HOME/.c-brain/trunk"
cd "$BRAIN"
fail=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fail=1; }

echo "== selftest des hooks du C Brain =="

# 1. compilation Python
for f in hooks/*.py; do
  python3 -m py_compile "$f" 2>/dev/null && ok "compile $f" || ko "compile $f"
done

# 2. capsule main.js
node --check capsule/main.js 2>/dev/null && ok "node --check main.js" || ko "node --check main.js"

# 3. SessionEnd : auto_maintain doit sortir 0 même sur entrée vide / session triviale.
# CLAUDE_BRAIN_GARDENING=1 = ZÉRO EFFET DE BORD : sans ça, si l'Inbox a du travail et que le quota
# est ouvert, le test franchissait les gardes, dé-filait une VRAIE session du backlog et lançait un
# agent claude (consommation tokens + risque de race). Un test ne doit jamais muter l'état réel.
CLAUDE_BRAIN_GARDENING=1 bash -c "echo '{}' | python3 hooks/auto_maintain.py"; [ $? -eq 0 ] && ok "auto_maintain exit 0 (entrée vide, sans effet de bord)" || ko "auto_maintain"

# 4. PostToolUse : on_fiche_write doit sortir 0 sur cible hors-tronc
echo '{"tool_input":{"file_path":"/tmp/horstronc.md"}}' | python3 hooks/on_fiche_write.py; [ $? -eq 0 ] && ok "on_fiche_write exit 0 (hors-tronc)" || ko "on_fiche_write"

# 5. brain_guard : interpret d'un 429 doit renvoyer 7 (échec géré, pas 0)
tmp=$(mktemp); echo '{"is_error":true,"api_error_status":429,"result":"limit resets 2:50pm"}' > "$tmp"
python3 hooks/brain_guard.py interpret "$tmp" "selftest-sid"; [ $? -eq 7 ] && ok "brain_guard interpret 429 → exit 7" || ko "brain_guard interpret"
# nettoyage de l'état de test laissé par interpret.
# CRITIQUE : interpret(429) écrit state/quota.json = {blocked_until: <futur>} (un DICT).
# L'ancien nettoyage ne traitait QUE les listes → le marqueur quota restait empoisonné
# et la maintenance autonome était silencieusement bloquée jusqu'à l'heure de reset fictive.
# On retire le sid de test de la file ET on réarme le quota à 0 (débloqué).
python3 - <<'PY' 2>/dev/null
import json,os
B=os.path.expanduser("~/.c-brain/trunk/")
p=B+"state/pending-distill.json"
if os.path.exists(p):
    try:
        d=json.load(open(p))
        if isinstance(d,list): json.dump([s for s in d if s!="selftest-sid"],open(p,"w"))
    except Exception: pass
# réarme le quota (et le login) — l'état de test ne doit JAMAIS survivre au selftest
try: json.dump({"blocked_until":0,"msg":"ok"},open(B+"state/quota.json","w"))
except Exception: pass
PY
rm -f "$tmp"

# 6. doctor doit tourner (0 sain / 1 anomalies) sans crasher
python3 hooks/brain_doctor.py --quiet; rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 1 ]; } && ok "brain_doctor tourne (rc=$rc)" || ko "brain_doctor crash"

# 7. INVARIANTS du Brain — relations doc↔code, capteurs qui redescendent, tolérance legacy.
#    Chaque bug de l'audit 2026-07-10 y est gravé comme relation, pas comme cas particulier.
python3 tests/invariants_brain.py >/dev/null 2>&1 \
  && ok "invariants_brain (7 relations)" \
  || ko "invariants_brain — un invariant du tronc est violé (python3 tests/invariants_brain.py)"

# 8. LA PORTE D'ENTRÉE — le CLI `brain` lui-même (ajouté le 2026-08-04).
#    LE TROU QUI A COÛTÉ 6 SEMAINES : ce selftest ne testait QUE des hooks. `brain` n'est pas un
#    hook, donc rien ne l'exerçait — et `brain status` appelait depuis le 2026-06-22 un
#    `brain_status.py show` qui N'EXISTAIT PAS. Le mot « show » était pris pour un ÉTAT et ÉCRIT
#    dans status.json : sortie vide, code 0, capsule corrompue. Le commit qui a introduit le bug
#    est CELUI QUI A CRÉÉ CE SELFTEST, et il annonçait « 12/12 OK ».
#    La leçon est dans le critère : « sort en code 0 » ne teste pas une commande dont le métier
#    est d'AFFICHER. On assarte donc sur la SORTIE, et sur l'ABSENCE d'effet de bord.
#    ⚠ DEUX FAUTES DE CE BLOC, PAYÉES EN CI LE 2026-08-13 :
#      · il supposait `./brain` dans le tronc. C'est vrai CHEZ L'AUTEUR, où le tronc EST le
#        dépôt. Après une vraie install il n'y a pas de `trunk/brain` : install.sh lie
#        `~/.c-brain/engine/brain` vers `~/.local/bin/brain`. Le CLI se RÉSOUT donc, il ne
#        se devine pas.
#      · `$(./brain 2>&1)` capturait le « No such file or directory » du shell — donc
#        l'assertion « ça produit une sortie » passait au VERT sur une commande ABSENTE.
#        C'est exactement la faute que ce bloc existe pour attraper, commise dans le bloc
#        lui-même. On lit stdout SEUL, et on exige aussi le code 0.
BRAIN_CLI=""
for c in "$BRAIN/brain" "$(command -v brain 2>/dev/null || true)"; do
  [ -n "$c" ] && [ -x "$c" ] && { BRAIN_CLI="$c"; break; }
done
if [ -z "$BRAIN_CLI" ]; then
  ko "CLI brain introuvable (ni $BRAIN/brain, ni dans le PATH) — la porte d'entrée n'est pas testée"
else
avant=$(cat state/status.json 2>/dev/null)
for c in "" next; do
  # stdout SEUL : un message d'erreur sur stderr ne doit JAMAIS compter comme une sortie.
  out=$("$BRAIN_CLI" $c 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && [ -n "$out" ] \
    && ok "brain ${c:-status} produit une sortie ($(echo "$out" | wc -l | tr -d ' ') ligne(s))" \
    || ko "brain ${c:-status} : code $rc, $([ -n "$out" ] && echo 'sortie non vide' || echo 'RIEN sur stdout') — une commande d'affichage muette est cassée, même en code 0"
done
# une commande de LECTURE ne doit jamais muter l'état que lit la capsule
[ "$(cat state/status.json 2>/dev/null)" = "$avant" ] \
  && ok "brain status n'a pas modifié state/status.json (lecture pure)" \
  || ko "brain status a MUTÉ status.json — c'est exactement le bug du 2026-06-22"
# un état inconnu doit être REFUSÉ, pas enregistré (sinon une faute de frappe empoisonne la capsule)
python3 hooks/brain_status.py etat-bidon >/dev/null 2>&1
[ $? -eq 2 ] && [ "$(cat state/status.json 2>/dev/null)" = "$avant" ] \
  && ok "brain_status refuse un état inconnu (exit 2, fichier intact)" \
  || ko "brain_status a accepté un état inconnu — n'importe quelle faute de frappe casse la capsule"
# toutes les sous-commandes annoncées dans l'usage existent-elles vraiment dans le case ?
if BRAIN_CLI="$BRAIN_CLI" python3 - <<'PYEOF'
import re, subprocess, sys, os
brain = os.environ["BRAIN_CLI"]          # résolu par le script, jamais deviné
usage = subprocess.run([brain, "commande-inexistante"], capture_output=True, text=True)
m = re.search(r"brain <([^>]*)>", usage.stdout + usage.stderr)
annoncees = set(m.group(1).split("|")) if m else set()
src = open(brain).read()
# toutes les alternatives de toutes les étiquettes de `case`
implementees = set()
for lab in re.findall(r"^\s{2}([a-z|]+)\)", src, re.M):
    implementees |= set(lab.split("|"))
manquantes = sorted(annoncees - implementees)
if not annoncees:
    print("usage introuvable", file=sys.stderr); sys.exit(1)
if manquantes:
    print("annoncées mais absentes : " + " ".join(manquantes), file=sys.stderr); sys.exit(1)
print(f"{len(annoncees)} sous-commandes annoncées, toutes implémentées")
PYEOF
then ok "usage ↔ case : aucune sous-commande annoncée à vide"
else ko "l'usage de brain annonce une sous-commande qui n'existe pas (c'est CE type d'écart qui a créé le bug du 2026-06-22)"
fi
fi

# 8. Le rappel ne parle QUE sur demande (décision l'auteur 2026-09-09) — et la recherche,
#    elle, reste vivante. Le test porte ses deux sabotages : sans eux, une remise en
#    marche du bavardage automatique ne rougirait nulle part.
python3 tests/rappel_a_la_demande.py >/dev/null 2>&1 \
  && ok "rappel à la demande (invariant + 2 sabotages)" \
  || ko "rappel à la demande — le hook parle tout seul, ou la recherche est cassée (python3 tests/rappel_a_la_demande.py)"

echo
[ $fail -eq 0 ] && echo "✅ selftest OK — tous les hooks sains" || echo "❌ selftest : des hooks sont cassés"
exit $fail
