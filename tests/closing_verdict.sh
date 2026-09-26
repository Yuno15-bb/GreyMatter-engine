#!/usr/bin/env bash
# closing_verdict — the last screen of install.sh must say what actually happened.
#
# WHY THIS BENCH EXISTS
# The installer used to end on `echo "✅ C Brain installed."`, unconditionally. On a
# fresh macOS where ~/.local/bin is not on PATH, that line arrived right after a red
# "hooks broken", and was followed by four commands starting with `brain` — none of
# which resolve. The PATH warning was three hundred lines earlier and had scrolled
# away. Recorded as C bis A4, with the observable named in advance: install on a bare
# PATH, and the last screen must say PATH.
#
# A closing verdict that cannot go red is a decoration, not a report — the same defect
# as a test that never fails. So this bench carries its own sabotage: it rebuilds the
# old constant verdict and checks that case A then goes red. Without that, a future
# rewrite could flatten the verdict again and nothing would notice.
#
#   bash tests/closing_verdict.sh
#
# WHERE THIS LIVES, AND WHY IT IS NOT IN THE BRAIN
# tests/ is normally copied from the author's living Brain by sync.sh, with --delete:
# a file that exists only here is erased on the next copy unless it is named in that
# script's exclusion list. This one is safe by a different route — sync.sh refuses to
# run on `main`, and install.sh is maintained on `main` only (the `fr` copy has not
# moved since 2026-08-16). The bench therefore sits beside the script it measures.
# If install.sh is ever brought over to `fr`, this file must be added to the
# `sync_dir tests` exclusions at the same time, or the copy will take it away.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
ok() { echo "  ✅ $1"; }
ko() { echo "  ❌ $1"; fail=1; }

# A dry run writes nothing, so the whole bench is side-effect free. HOME is thrown
# away anyway: an installer test that touches the real HOME is not a test.
closing_screen() {                       # $1 = script, $2 = 1 if ~/.local/bin on PATH
  local script="$1" on_path="$2" home; home="$TMP/home-$RANDOM"
  mkdir -p "$home/.local/bin"
  local p="/usr/bin:/bin:/usr/sbin:/sbin"
  [ "$on_path" = "1" ] && p="$home/.local/bin:$p"
  ( cd "$HERE" && env HOME="$home" PATH="$p" bash "$script" --dry-run 2>&1 ) | tail -25
}

echo "== closing verdict of install.sh =="

# ─── A. bare PATH: the last screen must name PATH, not declare success ───
a="$(closing_screen "$HERE/install.sh" 0)"
case "$a" in
  *"not reachable yet"*) ok "bare PATH — the closing screen names PATH" ;;
  *) ko "bare PATH — the closing screen never mentions PATH" ;;
esac
case "$a" in
  *"✅ C Brain installed."*) ko "bare PATH — it still claims a clean install" ;;
  *) ok "bare PATH — it does not claim a clean install" ;;
esac
case "$a" in
  *"~/.local/bin/brain"*) ok "bare PATH — it offers a command that actually runs" ;;
  *) ko "bare PATH — every command it offers needs the PATH it does not have" ;;
esac

# ─── B. control: with the directory on PATH, nothing must be dramatised ───
b="$(closing_screen "$HERE/install.sh" 1)"
case "$b" in
  *"✅ C Brain installed."*) ok "PATH present — the closing screen is plain success" ;;
  *) ko "PATH present — success is no longer announced" ;;
esac
case "$b" in
  *"not reachable yet"*) ko "PATH present — a warning fires on a healthy install" ;;
  *) ok "PATH present — no warning on a healthy install" ;;
esac

# ─── C. sabotage: put the constant verdict back, case A must go red ───
sed 's/^if \[ "${PATH_OK:-1}" = "0" \]; then$/if false; then/' \
    "$HERE/install.sh" > "$TMP/sabotaged.sh"
if cmp -s "$HERE/install.sh" "$TMP/sabotaged.sh"; then
  ko "sabotage — the guarded line was not found, this bench is no longer aimed at it"
else
  c="$(closing_screen "$TMP/sabotaged.sh" 0)"
  case "$c" in
    *"not reachable yet"*) ko "sabotage — a constant verdict still passes case A" ;;
    *) ok "sabotage — a constant verdict makes case A go red, as it must" ;;
  esac
fi

echo
[ $fail -eq 0 ] && echo "✅ the closing verdict reports what happened" \
                || echo "❌ the closing verdict does not match the install"
exit $fail
