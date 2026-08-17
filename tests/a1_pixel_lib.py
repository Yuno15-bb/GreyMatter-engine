#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""
a1_pixel_lib.py — the MEASUREMENTS behind A1, and nothing else.

WHY THIS FILE EXISTS SEPARATELY. Every judgement A1 makes lives here as a
function that takes its inputs as arguments. `a1_capsule_pixel.sh --run` feeds
those functions real data; `--self-check` feeds the SAME functions crafted data
that must make them go red. A sabotage that exercised a copy of the logic would
prove nothing about the path that actually runs, which is the trap recorded in
`test-d-equivalence-vert-aussi-quand-le-code-est-inerte`.

THE COORDINATE SPACE, MEASURED ON 2026-08-17. The first version of this harness
computed the orb rectangle from `system_profiler`'s "Resolution: 2560 x 1664"
and handed it to `screencapture -R`, which takes POINTS. Three different numbers
were in play on the same machine:

    2560 x 1664   the PANEL's native resolution, what system_profiler reports
    2940 x 1912   the FRAMEBUFFER, what a full-screen capture actually contains
    1470 x  956   the POINT space, what -R and Electron both use

Only the third is the coordinate system of the question. Asking for the orb at
`2384,1488` wrote NO FILE — and a harness that reads "no file" as "the rectangle
is empty" hands out a green negative control while blind. That is the same
failure the sensor check exists to prevent, one layer down, which is why
`capture()` below has no code path that can return emptiness for a missing file.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

# How much a channel must move for a pixel to count as changed. Below this, a
# capture's own noise (compression, a cursor, a clock ticking) reads as change.
CHANNEL_DELTA = 12
# A capture holding fewer distinct colours than this is not looking at a screen.
# Measured: a uniform image gives 1, a real desktop gives several hundred.
BLIND_COLOURS = 8


# ═══════════════════════════════════════════════════════════════════════════
# THE COORDINATE SYSTEM — established from two independent instruments
# ═══════════════════════════════════════════════════════════════════════════
def screen_points_from_finder():
    """Point size of the main display, according to the window server."""
    out = subprocess.run(
        ["osascript", "-e", "tell application \"Finder\" to get bounds of window of desktop"],
        capture_output=True, text=True).stdout.strip()
    nums = [int(n) for n in re.findall(r"-?\d+", out)]
    if len(nums) != 4:
        return None
    return (nums[2] - nums[0], nums[3] - nums[1])


def screen_points_from_capture(work):
    """Point size derived from a capture and its measured backing scale.

    Independent of the call above: it goes through screencapture and sips
    rather than through the Finder. Two instruments that share nothing but the
    screen itself — the point of asking twice.
    """
    full = os.path.join(work, "_full.png")
    if capture(None, full) != "OK":
        return None
    fw, fh = image_size(full)
    probe = os.path.join(work, "_scale.png")
    if capture("0,0,100,100", probe) != "OK":
        return None
    pw, _ = image_size(probe)
    if not pw or pw % 100:
        return None
    scale = pw // 100
    if not fw or not fh or not scale:
        return None
    return (fw // scale, fh // scale)


def screen_points(work):
    """Both instruments, and a refusal to guess when they disagree."""
    a = screen_points_from_finder()
    b = screen_points_from_capture(work)
    return a, b, (a is not None and a == b)


def orb_rect(size, edge, points_w, points_h):
    """PURE. Where `capsule/main.js` puts the window, in the space -R speaks.

    main.js:  x = bounds.x + bounds.width  - SIZE - EDGE
              y = bounds.y + bounds.height - SIZE - EDGE
    and Electron's `bounds` are points, so the screen size handed in here must
    be points too. Feeding it a framebuffer or a panel resolution is the bug
    this signature makes visible instead of silent.
    """
    return (points_w - size - edge, points_h - size - edge, size, size)


def rect_on_screen(rect, points_w, points_h):
    """PURE. A rectangle -R can actually satisfy."""
    x, y, w, h = rect
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= points_w and y + h <= points_h


# ═══════════════════════════════════════════════════════════════════════════
# CAPTURE — where "nothing came back" must never become "nothing is there"
# ═══════════════════════════════════════════════════════════════════════════
def capture(rect, out):
    """Returns "OK" or "UNREADABLE". There is deliberately no third answer.

    screencapture exits 0 in cases where it writes nothing at all — an
    off-screen rectangle is one. Every caller therefore has to handle
    UNREADABLE explicitly; none of them can accidentally treat it as an empty
    region, because emptiness is not one of the values this returns.
    """
    try:
        os.path.exists(out) and os.remove(out)
    except OSError:
        pass
    cmd = ["screencapture", "-x"]
    if rect:
        cmd += ["-R", rect]
    cmd.append(out)
    subprocess.run(cmd, capture_output=True)
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        return "UNREADABLE"
    return "OK"


def image_size(png):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", png],
                         capture_output=True, text=True).stdout
    w = re.search(r"pixelWidth:\s*(\d+)", out)
    h = re.search(r"pixelHeight:\s*(\d+)", out)
    return (int(w.group(1)) if w else None, int(h.group(1)) if h else None)


def signature(png, side=96):
    """Downsampled raw RGB of an image, or None if it cannot be read.

    None is not an empty signature. `diff_pct` refuses to compare it, so an
    unreadable capture propagates as "unknown" all the way to the verdict.
    """
    if not png or not os.path.exists(png) or os.path.getsize(png) == 0:
        return None
    work = tempfile.mkdtemp(prefix="a1sig-")
    small = os.path.join(work, "s.png")
    bmp = os.path.join(work, "s.bmp")
    subprocess.run(["sips", "-Z", str(side), png, "--out", small], capture_output=True)
    subprocess.run(["sips", "-s", "format", "bmp", small, "--out", bmp], capture_output=True)
    data = open(bmp, "rb").read() if os.path.exists(bmp) else b""
    body = data[54:] if len(data) > 54 else b""
    return body or None


def colours(sig):
    """PURE. Distinct colours in a signature — the blindness measure."""
    if not sig:
        return 0
    return len({sig[i:i + 3] for i in range(0, len(sig) - 3, 3)})


def diff_pct(a, b):
    """PURE. Percentage of pixels that moved, or None when either side is unknown."""
    if not a or not b:
        return None
    n = min(len(a), len(b))
    if n < 3:
        return None
    changed = sum(1 for i in range(0, n - 2, 3) if abs(a[i] - b[i]) > CHANNEL_DELTA)
    return 100.0 * changed / (n / 3.0)


# ═══════════════════════════════════════════════════════════════════════════
# THE JUDGEMENTS — pure, so a sabotage can reach every one of them
# ═══════════════════════════════════════════════════════════════════════════
def judge_sensor(sig):
    """Can this capture be looking at a screen at all?"""
    c = colours(sig)
    if sig is None:
        return False, "the capture is unreadable — the sensor produced nothing to judge"
    if c < BLIND_COLOURS:
        return False, ("the capture holds %d distinct colours: it is blind. Screen "
                       "Recording is probably not granted to this terminal" % c)
    return True, "the capture carries %d distinct colours" % c


def judge_discrimination(d_appear, d_vanish, d_drift):
    """Does the sensor separate a window being there from not being there?

    Not "is the image colourful" — a desktop picture is colourful, and a capture
    taken without Screen Recording permission returns exactly that while showing
    no window at all. The only calibration that speaks to A1 is one made of
    windows.
    """
    if d_appear is None or d_vanish is None or d_drift is None:
        return False, "one of the calibration captures was unreadable"
    if d_appear < 5.0:
        return False, ("a window appearing moved %.1f%% of the rectangle: the sensor "
                       "does not see windows, only the desktop behind them" % d_appear)
    if d_drift > 3.0:
        return False, ("the same scene twice already differs by %.1f%%: too noisy to "
                       "attribute any later change to the orb" % d_drift)
    if d_appear < 3 * max(d_drift, 0.3):
        return False, ("a window appearing (%.1f%%) is not clear of the noise floor "
                       "(%.1f%%)" % (d_appear, d_drift))
    return True, ("appear %.1f%% / vanish %.1f%% / drift %.1f%%"
                  % (d_appear, d_vanish, d_drift))


def judge_negative(rect_status, capsule_processes, alive_mtime, session_start):
    """Is the orb rectangle trustworthy as a BEFORE picture?

    Three ways it is not, and the first one is the trap: an unreadable capture
    is not an empty rectangle. The other two are contamination — a capsule
    running now, or one that ran earlier in this same login session, because
    macOS keeps ghost layers of these transparent always-on-top windows and a
    killed capsule can still be on screen.
    """
    bad = []
    if rect_status != "OK":
        bad.append("the rectangle did not capture (%s) — this is NOT an empty region"
                   % rect_status)
    if capsule_processes:
        bad.append("%d capsule process(es) are running right now" % capsule_processes)
    if alive_mtime and session_start and alive_mtime >= session_start:
        bad.append("a capsule beat in THIS login session (%d s after it opened) — "
                   "its ghost layer may still be on screen"
                   % int(alive_mtime - session_start))
    if bad:
        return False, bad
    return True, ["no capsule now, none in this session, and the rectangle reads"]


def judge_engine_path(real, home):
    """PURE. Is this engine one the INSTALLER built, or the author's checkout?

    Kept here rather than in the shell so it can be shown both a path it must
    refuse and a path it must accept, without an engine having to exist on disk.
    Fabricating one to make a check green would be the exact move this harness
    exists to refuse.
    """
    versions = os.path.join(home, ".c-brain", "versions") + os.sep
    if "/claude-brain" in real:
        return False, "the engine resolves into ~/claude-brain — the author's layout"
    if not (real.rstrip(os.sep) + os.sep).startswith(versions):
        return False, ("the engine is %s, which is NOT under ~/.c-brain/versions/. A1 "
                       "certifies the capsule of an INSTALLED engine" % real)
    return True, "the engine is an installed version: %s" % os.path.basename(real.rstrip(os.sep))


def judge_launch(probe, expected_capsule):
    """Did the capsule we asked for actually start, and is it the one reporting?

    The failure this catches is silent by design. `app.requestSingleInstanceLock`
    makes a second capsule `app.quit()` with no message, no log and no exit code
    anyone sees — main.js says so in its own comment. A harness that only looked
    for an orb on screen would then measure the capsule ALREADY running from the
    author's trunk and call it a pass.
    """
    if not probe:
        return False, ("no probe was written: the capsule exited before it could "
                       "report. A second capsule quits instantly and silently on the "
                       "single-instance lock — launch it with --user-data-dir")
    engine = str(probe.get("engine_dir", ""))
    if os.path.realpath(engine) != os.path.realpath(expected_capsule):
        return False, ("the probe came from %r, not from the capsule under test (%r)"
                       % (engine, expected_capsule))
    return True, "the capsule under test is the one reporting"


def judge_drive(capsule_status_path, written_status_path, payload, liveness_seconds, now):
    """Are we driving the state file this capsule actually reads?

    `main.js` derives it from `os.homedir()`, never from the engine directory.
    Writing to the wrong home leaves the orb idle for the whole run, and the
    pixel step would then fail for a reason that has nothing to do with the orb.
    """
    bad = []
    if os.path.realpath(capsule_status_path) != os.path.realpath(written_status_path):
        bad.append("the capsule reads %s but the harness writes %s: it would never "
                   "see the state" % (capsule_status_path, written_status_path))
    if payload.get("state") == "busy":
        age = now - float(payload.get("ts", 0))
        if age >= liveness_seconds:
            bad.append("the busy payload is already %.0f s old against a %d s liveness "
                       "window: the orb would read it as idle" % (age, liveness_seconds))
    if bad:
        return False, bad
    return True, ["driving %s, the file this capsule reads" % capsule_status_path]


def judge_dom(busy, idle, versions_root):
    """What the RENDERER says it is showing, in both states.

    Two requirements, and the second is the one a constant channel fails: the
    states must each be right, AND they must DIFFER. A probe file that never
    changes satisfies neither state honestly, and would sail through a check
    that only ever looked at `busy`.
    """
    bad = []
    if not busy or not idle:
        return False, ["the probe wrote no readable JSON in one of the two states"]
    if busy == idle:
        bad.append("the probe reported the SAME thing busy and idle: a constant, "
                   "not a measurement")
    if busy.get("renderer_ready") != "complete":
        bad.append("busy: renderer_ready is %r, not 'complete'" % busy.get("renderer_ready"))
    if not str(busy.get("state_text", "")).startswith("DISTILLING"):
        bad.append("busy: state_text is %r, expected it to start with DISTILLING"
                   % busy.get("state_text"))
    if not busy.get("state_visible"):
        bad.append("busy: the state label is not visible")
    if not str(busy.get("detail_text", "")).strip():
        bad.append("busy: no detail text")
    if not busy.get("window_visible"):
        bad.append("busy: the window itself is not visible to the system")
    engine = str(busy.get("engine_dir", ""))
    if versions_root not in engine:
        bad.append("busy: engine_dir is %r, which is not under %s" % (engine, versions_root))
    if str(idle.get("state_text", "")).strip():
        bad.append("idle: state_text is still %r" % idle.get("state_text"))
    if idle.get("state_visible"):
        bad.append("idle: the state label is still visible")
    if idle.get("detail_visible"):
        bad.append("idle: the detail is still visible")
    if bad:
        return False, bad
    return True, ["busy says %r, idle says nothing, engine under versions/"
                  % busy.get("state_text")]


def judge_pixels(d_appear, d_vanish, drift_busy, drift_idle):
    """Did the SCREEN change when the orb came and went?

    The comparison that matters is against the harness's own noise: the orb
    animates, so two captures of the same busy state already differ. If that
    self-difference is as large as the difference the orb's arrival makes, the
    instrument cannot attribute anything, and it has to say so rather than
    round up to a pass.
    """
    if None in (d_appear, d_vanish, drift_busy, drift_idle):
        return False, ["one of the four captures was unreadable — nothing can be "
                       "concluded, and an unreadable capture is not an empty rectangle"]
    floor = max(drift_busy, drift_idle, 0.3)
    bad = []
    if d_appear < 5.0:
        bad.append("the orb appearing moved only %.1f%% of the rectangle" % d_appear)
    if d_vanish < 5.0:
        bad.append("the orb leaving moved only %.1f%% of the rectangle" % d_vanish)
    if d_appear < 3 * floor:
        bad.append("appear %.1f%% is not clear of the same-state noise %.1f%%"
                   % (d_appear, floor))
    if d_vanish < 3 * floor:
        bad.append("vanish %.1f%% is not clear of the same-state noise %.1f%%"
                   % (d_vanish, floor))
    if bad:
        return False, bad
    return True, ["appear %.1f%% / vanish %.1f%% against a %.1f%% noise floor"
                  % (d_appear, d_vanish, floor)]


def judge_cross(dom_ok, pixel_ok):
    """Neither observable is allowed to stand in for the other.

    A renderer can be certain it is drawing an orb nobody can see. A screen can
    show an orb no renderer is drawing — macOS keeps ghost layers. A1 is proven
    only where the two agree.
    """
    if dom_ok and pixel_ok:
        return True, "the renderer and the screen agree"
    if dom_ok and not pixel_ok:
        return False, ("the renderer believes it is drawing an orb the screen does not "
                       "show — off-screen, occluded, or fully transparent")
    if pixel_ok and not dom_ok:
        return False, ("the screen changed but the renderer does not report the state — "
                       "a ghost layer would look exactly like this")
    return False, "neither observable held"


# ═══════════════════════════════════════════════════════════════════════════
# THE MACHINE'S OWN FACTS
# ═══════════════════════════════════════════════════════════════════════════
def session_start_epoch():
    """When the current login session opened, from loginwindow's own age."""
    pid = subprocess.run(["pgrep", "-x", "loginwindow"], capture_output=True, text=True).stdout.split()
    if not pid:
        return None
    et = subprocess.run(["ps", "-p", pid[0], "-o", "etime="],
                        capture_output=True, text=True).stdout.strip()
    m = re.match(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$", et)
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return time.time() - (d * 86400 + h * 3600 + mi * 60 + s)


def capsule_process_count():
    """Capsule Electron processes alive right now, from any trunk."""
    out = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True).stdout
    n = 0
    for line in out.splitlines():
        if "capsule/node_modules/electron" in line and "Helper" not in line:
            n += 1
    return n


def newest_alive_mtime(paths):
    best = None
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        best = m if best is None else max(best, m)
    return best


def read_probe(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# THE SABOTAGES — every judgement above, fed a state it must refuse
# ═══════════════════════════════════════════════════════════════════════════
def _uniform_png(path, side=64):
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes([0, 0, 0]) * side for _ in range(side))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data)))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


SABOTAGES = []


def sabotage(step, name):
    def deco(fn):
        SABOTAGES.append((step, name, fn))
        return fn
    return deco


@sabotage("0", "a uniform image is not mistaken for a screen")
def _sab_blind():
    work = tempfile.mkdtemp(prefix="a1sab-")
    p = os.path.join(work, "blank.png")
    _uniform_png(p)
    ok, why = judge_sensor(signature(p))
    return (not ok and "blind" in why), why


@sabotage("0", "an unreadable capture is refused, not scored")
def _sab_sensor_unreadable():
    ok, why = judge_sensor(None)
    return (not ok and "unreadable" in why), why


@sabotage("1", "a sensor that sees the desktop but no windows is refused")
def _sab_desktop_only():
    # What a permission-denied capture looks like: colourful, and identical
    # whether or not a window is on top of it.
    ok, why = judge_discrimination(d_appear=0.2, d_vanish=0.2, d_drift=0.1)
    return (not ok and "does not see windows" in why), why


@sabotage("1", "a noisy scene cannot be used as a baseline")
def _sab_noisy():
    ok, why = judge_discrimination(d_appear=9.0, d_vanish=9.0, d_drift=8.0)
    return (not ok and "noisy" in why), why


@sabotage("2", "an unreadable rectangle is NOT reported as empty")
def _sab_unreadable_is_not_empty():
    ok, why = judge_negative("UNREADABLE", 0, None, None)
    return (not ok and any("NOT an empty region" in b for b in why)), "; ".join(why)


@sabotage("2", "an off-screen rectangle really does capture nothing")
def _sab_offscreen_capture():
    # The 2026-08-17 bug, executed rather than described: a rectangle computed
    # in framebuffer or panel pixels lands outside the point space.
    work = tempfile.mkdtemp(prefix="a1sab-")
    out = os.path.join(work, "off.png")
    status = capture("99000,99000,150,150", out)
    return status == "UNREADABLE", "off-screen capture returned %s" % status


@sabotage("2", "a rectangle computed in the wrong coordinate space is rejected")
def _sab_wrong_space():
    # points 1470x956, framebuffer 2940x1912. Computing the rect from the
    # framebuffer is exactly what the first harness did.
    bad = orb_rect(150, 26, 2940, 1912)
    ok_bad = rect_on_screen(bad, 1470, 956)
    good = orb_rect(150, 26, 1470, 956)
    ok_good = rect_on_screen(good, 1470, 956)
    return (not ok_bad and ok_good), "framebuffer rect %s rejected, point rect %s kept" % (bad, good)


@sabotage("2", "a capsule running now contaminates the negative control")
def _sab_contaminated_running():
    ok, why = judge_negative("OK", 3, None, None)
    return (not ok and any("running right now" in b for b in why)), "; ".join(why)


@sabotage("2", "a capsule that ran EARLIER in this session contaminates it too")
def _sab_contaminated_ghost():
    start = time.time() - 3600
    ok, why = judge_negative("OK", 0, alive_mtime=start + 120, session_start=start)
    return (not ok and any("ghost layer" in b for b in why)), "; ".join(why)


@sabotage("3", "the author's own checkout is refused as an engine")
def _sab_engine_author():
    ok, why = judge_engine_path("/Users/x/claude-brain", "/Users/x")
    return (not ok and "author's layout" in why), why


@sabotage("3", "an engine outside versions/ is refused")
def _sab_engine_outside():
    ok, why = judge_engine_path("/opt/somewhere/engine", "/Users/x")
    return (not ok and "NOT under" in why), why


@sabotage("4", "a capsule killed by the single-instance lock is not a launch")
def _sab_launch_silent_death():
    ok, why = judge_launch(None, "/Users/x/.c-brain/versions/abc/capsule")
    return (not ok and "single-instance lock" in why), why


@sabotage("4", "a probe from another capsule is not this capsule")
def _sab_launch_wrong_reporter():
    probe = {"engine_dir": "/Users/x/claude-brain/capsule"}
    ok, why = judge_launch(probe, "/Users/x/.c-brain/versions/abc/capsule")
    return (not ok and "not from the capsule under test" in why), why


@sabotage("5", "driving a state file the capsule does not read is caught")
def _sab_drive_wrong_home():
    ok, why = judge_drive("/Users/them/.c-brain/trunk/state/status.json",
                          "/Users/us/.c-brain/trunk/state/status.json",
                          {"state": "busy", "ts": time.time()}, 30, time.time())
    return (not ok and any("would never see" in b for b in why)), "; ".join(why)


@sabotage("5", "a busy payload already too old to read as busy is caught")
def _sab_drive_stale():
    now = time.time()
    ok, why = judge_drive("/s.json", "/s.json", {"state": "busy", "ts": now - 90}, 30, now)
    return (not ok and any("liveness window" in b for b in why)), "; ".join(why)


@sabotage("6", "a probe that never changes is a constant, not a measurement")
def _sab_dom_constant():
    same = {"renderer_ready": "complete", "state_text": "DISTILLING...",
            "state_visible": True, "detail_text": "a1", "window_visible": True,
            "engine_dir": "/Users/x/.c-brain/versions/abc/capsule"}
    ok, why = judge_dom(same, dict(same), "/.c-brain/versions/")
    return (not ok and any("constant" in b for b in why)), "; ".join(why)


@sabotage("6", "a renderer drawing into a hidden window is refused")
def _sab_dom_hidden():
    busy = {"renderer_ready": "complete", "state_text": "DISTILLING...",
            "state_visible": True, "detail_text": "a1", "window_visible": False,
            "engine_dir": "/Users/x/.c-brain/versions/abc/capsule"}
    idle = {"renderer_ready": "complete", "state_text": "", "state_visible": False,
            "detail_visible": False, "window_visible": False, "engine_dir": busy["engine_dir"]}
    ok, why = judge_dom(busy, idle, "/.c-brain/versions/")
    return (not ok and any("not visible to the system" in b for b in why)), "; ".join(why)


@sabotage("6", "a probe from an engine outside versions/ is refused")
def _sab_dom_wrong_engine():
    busy = {"renderer_ready": "complete", "state_text": "DISTILLING...",
            "state_visible": True, "detail_text": "a1", "window_visible": True,
            "engine_dir": "/Users/x/claude-brain/capsule"}
    idle = {"renderer_ready": "complete", "state_text": "", "state_visible": False,
            "detail_visible": False, "window_visible": True, "engine_dir": busy["engine_dir"]}
    ok, why = judge_dom(busy, idle, "/.c-brain/versions/")
    return (not ok and any("not under" in b for b in why)), "; ".join(why)


@sabotage("7", "a rectangle that does not change between busy and idle is refused")
def _sab_pixel_flat():
    ok, why = judge_pixels(d_appear=0.4, d_vanish=0.3, drift_busy=0.2, drift_idle=0.1)
    return (not ok and any("only" in b for b in why)), "; ".join(why)


@sabotage("7", "a change no larger than the orb's own animation proves nothing")
def _sab_pixel_in_the_noise():
    ok, why = judge_pixels(d_appear=18.0, d_vanish=17.0, drift_busy=16.0, drift_idle=0.2)
    return (not ok and any("noise" in b for b in why)), "; ".join(why)


@sabotage("7", "an unreadable capture never becomes a pixel verdict")
def _sab_pixel_unreadable():
    ok, why = judge_pixels(None, 20.0, 0.2, 0.1)
    return (not ok and any("unreadable" in b for b in why)), "; ".join(why)


@sabotage("8", "the renderer alone cannot carry the verdict")
def _sab_cross_dom_only():
    ok, why = judge_cross(dom_ok=True, pixel_ok=False)
    return (not ok and "does not show" in why), why


@sabotage("8", "the screen alone cannot carry it either — that is what a ghost is")
def _sab_cross_pixel_only():
    ok, why = judge_cross(dom_ok=False, pixel_ok=True)
    return (not ok and "ghost layer" in why), why


@sabotage("*", "diff refuses to compare an unreadable signature")
def _sab_diff_none():
    # The quiet version of the whole bug: if this returned 0.0, "nothing came
    # back" would read as "nothing changed" everywhere downstream.
    return diff_pct(None, b"\x00\x01\x02") is None, "diff(None, x) = %r" % diff_pct(None, b"\x00\x01\x02")


# ═══════════════════════════════════════════════════════════════════════════
# THE POSITIVE CONTROLS — every judgement, fed a state it must ACCEPT
# ═══════════════════════════════════════════════════════════════════════════
# Sabotages alone prove a judge can say no. A judge that says no to everything
# is a constant, not a measurement, and it would fail A1 forever while looking
# rigorous. Both halves of the calibration, or neither.
POSITIVES = []


def positive(step, name):
    def deco(fn):
        POSITIVES.append((step, name, fn))
        return fn
    return deco


_GOOD_BUSY = {"renderer_ready": "complete", "state_text": "DISTILLING...",
              "state_visible": True, "detail_text": "a1 capsule pixel proof",
              "detail_visible": True, "window_visible": True,
              "engine_dir": "/Users/x/.c-brain/versions/abc123/capsule"}
_GOOD_IDLE = {"renderer_ready": "complete", "state_text": "", "state_visible": False,
              "detail_text": "", "detail_visible": False, "window_visible": True,
              "engine_dir": _GOOD_BUSY["engine_dir"]}


@positive("0", "a real screen capture is accepted")
def _pos_sensor():
    sig = bytes(range(0, 255, 3)) * 12
    ok, why = judge_sensor(sig)
    return ok, why


@positive("1", "the calibration measured on 2026-08-17 passes")
def _pos_discrimination():
    # The numbers this harness actually produced against a known window.
    return judge_discrimination(20.8, 20.8, 0.0)


@positive("2", "a readable rectangle on a clean session is accepted")
def _pos_negative():
    start = time.time() - 600
    ok, why = judge_negative("OK", 0, alive_mtime=start - 90000, session_start=start)
    return ok, "; ".join(why)


@positive("2", "the point-space rectangle is accepted")
def _pos_rect():
    r = orb_rect(150, 26, 1470, 956)
    return rect_on_screen(r, 1470, 956), "rect %s on a 1470x956 point screen" % (r,)


@positive("3", "an installed version IS accepted — the judge is not a constant no")
def _pos_engine():
    return judge_engine_path("/Users/x/.c-brain/versions/7bb6e9f", "/Users/x")


@positive("4", "the capsule under test reporting is accepted")
def _pos_launch():
    return judge_launch({"engine_dir": "/tmp"}, "/tmp")


@positive("5", "a fresh busy payload on the right file is accepted")
def _pos_drive():
    now = time.time()
    ok, why = judge_drive("/s.json", "/s.json", {"state": "busy", "ts": now - 1}, 30, now)
    return ok, "; ".join(why)


@positive("6", "a renderer reporting both states correctly is accepted")
def _pos_dom():
    ok, why = judge_dom(_GOOD_BUSY, _GOOD_IDLE, "/.c-brain/versions/")
    return ok, "; ".join(why)


@positive("7", "an orb clearly above the noise is accepted")
def _pos_pixels():
    ok, why = judge_pixels(31.0, 29.0, 6.0, 0.2)
    return ok, "; ".join(why)


@positive("8", "two agreeing observables are accepted")
def _pos_cross():
    return judge_cross(True, True)


@positive("*", "diff of two real signatures returns a number")
def _pos_diff():
    a = bytes([0, 0, 0]) * 100
    b = bytes([255, 255, 255]) * 100
    d = diff_pct(a, b)
    return (d is not None and d > 99.0), "diff(black, white) = %r" % d


def run_positives():
    fails = 0
    for step, name, fn in POSITIVES:
        try:
            ok, detail = fn()
        except Exception as e:                                   # noqa: BLE001
            ok, detail = False, "raised %s: %s" % (type(e).__name__, e)
        print("%s  [step %s] %s" % ("  ok  " if ok else "  FAIL", step, name))
        print("        %s" % detail)
        if not ok:
            fails += 1
    return fails


def run_sabotages():
    fails = 0
    for step, name, fn in SABOTAGES:
        try:
            ok, detail = fn()
        except Exception as e:                                   # noqa: BLE001
            ok, detail = False, "raised %s: %s" % (type(e).__name__, e)
        mark = "  ok  " if ok else "  FAIL"
        print("%s  [step %s] %s" % (mark, step, name))
        print("        %s" % detail)
        if not ok:
            fails += 1
    return fails


def covered_steps():
    """Steps that have BOTH halves of a calibration: a red and a green."""
    return (sorted({s for s, _, _ in SABOTAGES if s != "*"}),
            sorted({s for s, _, _ in POSITIVES if s != "*"}))


# ═══════════════════════════════════════════════════════════════════════════
# CLI — the shell driver's only way in, so both callers share one implementation
# ═══════════════════════════════════════════════════════════════════════════
def _emit(**kw):
    for k, v in kw.items():
        print("%s=%s" % (k.upper(), v))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    work = os.environ.get("A1_WORK", os.path.expanduser("~/.c-brain-a1"))
    os.makedirs(work, exist_ok=True)

    if cmd == "screen-points":
        a, b, agree = screen_points(work)
        _emit(finder="%sx%s" % a if a else "UNREADABLE",
              capture="%sx%s" % b if b else "UNREADABLE",
              agree="yes" if agree else "no")
        if not agree:
            return 1
        _emit(points_w=a[0], points_h=a[1])
        return 0

    if cmd == "orb-rect":
        size, edge, pw, ph = (int(x) for x in argv[2:6])
        rect = orb_rect(size, edge, pw, ph)
        _emit(rect="%d,%d,%d,%d" % rect,
              on_screen="yes" if rect_on_screen(rect, pw, ph) else "no")
        return 0 if rect_on_screen(rect, pw, ph) else 1

    if cmd == "capture":
        status = capture(argv[2] if argv[2] != "-" else None, argv[3])
        _emit(capture=status)
        return 0 if status == "OK" else 1

    if cmd == "sensor":
        ok, why = judge_sensor(signature(argv[2]))
        _emit(sensor="ok" if ok else "blind", why=why)
        return 0 if ok else 1

    if cmd == "diff":
        d = diff_pct(signature(argv[2]), signature(argv[3]))
        _emit(diff="UNREADABLE" if d is None else "%.2f" % d)
        return 0 if d is not None else 1

    if cmd == "machine-facts":
        start = session_start_epoch()
        alive = newest_alive_mtime(argv[2:])
        _emit(session_start="%.0f" % start if start else "UNKNOWN",
              capsule_processes=capsule_process_count(),
              alive_mtime="%.0f" % alive if alive else "NONE")
        return 0

    if cmd == "judge-negative":
        status, procs, alive, start = argv[2], int(argv[3]), argv[4], argv[5]
        ok, why = judge_negative(status, procs,
                                 float(alive) if alive not in ("NONE", "UNKNOWN") else None,
                                 float(start) if start not in ("NONE", "UNKNOWN") else None)
        for line in why:
            print("     %s" % line)
        return 0 if ok else 1

    if cmd in ("judge-discrimination", "judge-pixels"):
        vals = [None if v == "UNREADABLE" else float(v) for v in argv[2:]]
        fn = judge_discrimination if cmd == "judge-discrimination" else judge_pixels
        ok, why = fn(*vals)
        for line in ([why] if isinstance(why, str) else why):
            print("     %s" % line)
        return 0 if ok else 1

    if cmd == "judge-launch":
        ok, why = judge_launch(read_probe(argv[2]), argv[3])
        print("     %s" % why)
        return 0 if ok else 1

    if cmd == "judge-drive":
        ok, why = judge_drive(argv[2], argv[3], read_probe(argv[4]) or {},
                              int(argv[5]), time.time())
        for line in why:
            print("     %s" % line)
        return 0 if ok else 1

    if cmd == "judge-dom":
        ok, why = judge_dom(read_probe(argv[2]), read_probe(argv[3]), argv[4])
        for line in why:
            print("     %s" % line)
        return 0 if ok else 1

    if cmd == "judge-cross":
        ok, why = judge_cross(argv[2] == "ok", argv[3] == "ok")
        print("     %s" % why)
        return 0 if ok else 1

    if cmd == "judge-engine-path":
        ok, why = judge_engine_path(argv[2], argv[3])
        print("     %s" % why)
        return 0 if ok else 1

    if cmd == "sabotages":
        return 1 if run_sabotages() else 0

    if cmd == "positives":
        return 1 if run_positives() else 0

    if cmd == "covered-steps":
        sab, pos = covered_steps()
        print("SABOTAGED=%s" % " ".join(sab))
        print("POSITIVE=%s" % " ".join(pos))
        return 0

    sys.stderr.write("unknown command: %r\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
