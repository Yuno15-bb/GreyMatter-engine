"""_fake_launchd.py — a launchd domain that is a text file.

ONE definition, shared by every launchd bench. $HOME does not isolate the real
domain — that is the finding this whole chantier came from — so no test here
may reach `gui/<uid>`. The substitute is a shell script placed first on PATH.

THE REGISTRY is a file, one service per line:
    <label>                          a service with no known program
    <label>\\t<program>\\t<plist-path>  what `print` will report

WHAT IS FAITHFUL, AND WHAT IS ASSUMED. The exit codes follow launchctl(1): a
`print` of an unknown service fails, and `load` of a Label the domain already
holds fails too — which is why the theft in the incident needed the unload
first. Those are READ FROM THE MAN PAGE, not measured against the real tool.
The `print` output shape is likewise a plausible transcription, not a capture.
Everything a bench concludes rests on that, and it is why no bench here can
close the runtime half on its own.
"""

FAKE = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
verb="$1"; shift
label_of_plist() { sed -n 's|.*<string>\(com\.[^<]*\)</string>.*|\1|p' "$1" | head -1; }
case "$verb" in
  print)
    label="${1##*/}"
    line="$(grep -E "^${label}(\t|$)" "$FAKE_REG" 2>/dev/null | head -1)" || :
    [ -n "$line" ] || { echo "Could not find service \"$label\"" >&2; exit 113; }
    prog="$(printf '%s' "$line" | cut -f2)"
    path="$(printf '%s' "$line" | cut -f3)"
    printf '%s = {\n' "$label"
    printf '\tstate = running\n'
    [ -n "$path" ] && printf '\tpath = %s\n' "$path"
    [ -n "$prog" ] && printf '\tprogram = /usr/bin/python3\n\targuments = {\n\t\t/usr/bin/python3\n\t\t%s\n\t}\n' "$prog"
    printf '}\n' ;;
  load)
    [ "${FAKE_FAIL_LOAD:-0}" = "1" ] && { echo "Load failed: 5: Input/output error" >&2; exit 1; }
    l="$(label_of_plist "$1")"
    grep -qE "^${l}(\t|$)" "$FAKE_REG" 2>/dev/null && { echo "Load failed: 17: File exists" >&2; exit 1; }
    printf '%s\n' "$l" >> "$FAKE_REG" ;;
  unload)
    [ "${FAKE_FAIL_UNLOAD:-0}" = "1" ] && { echo "Unload failed: 3: No such process" >&2; exit 1; }
    l="$(label_of_plist "$1")"
    grep -vE "^${l}(\t|$)" "$FAKE_REG" > "$FAKE_REG.t" 2>/dev/null || :
    mv "$FAKE_REG.t" "$FAKE_REG" ;;
esac
exit 0
'''

PLIST = ('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>\n'
         '<key>Label</key><string>%s</string>\n'
         '<key>ProgramArguments</key><array><string>/usr/bin/python3</string>'
         '<string>%s</string></array>\n'
         '</dict></plist>\n')
