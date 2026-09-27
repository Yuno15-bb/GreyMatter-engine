# Forwarding stub — pre-rename. SOURCED, not run, by the uninstall.sh of a C Brain
# clone (v2.0.x): the one script an updated user still has at hand, and the one
# INSTALL.md used to name. It reads this path from the engine, finds the library,
# and removes the jobs `com.claudebrain.*` — which no longer exist: since v2.1.0
# they are `com.greymatter.*`, the shortcut is ~/GreyMatter, the Desktop app is
# GreyMatter.app. Without this file it said "✅ Uninstalled" and left all four in
# place, jobs still firing (measured on a blank Mac, 2026-09-27).
#
# So it hands the rest of the uninstall to the engine's own uninstaller, which
# knows both names. The old script has already asked, and removed the hooks; the
# new one redoes nothing harmful — each of its steps is a no-op on what is gone.
# Any other caller is refused: sourcing a library must never uninstall anything.
case "$(basename "$0")" in
  uninstall.sh) ;;
  *) echo "cbrain/launchd-lib.sh is a forwarding stub for an old uninstaller; use greymatter/launchd-lib.sh" >&2
     return 1 2>/dev/null || exit 1 ;;
esac
_gm_new="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/uninstall.sh"
[ -f "$_gm_new" ] || { echo "  ($_gm_new missing — the launchd jobs are LEFT ALONE)"; return 1; }
echo "  (an uninstaller from before the rename — handing over to $_gm_new)"
echo
if [ "${PURGE_ENGINE:-0}" = "1" ]; then exec bash "$_gm_new" --yes --purge-engine; fi
exec bash "$_gm_new" --yes
