#!/usr/bin/env python3
"""Kernel-level touch gestures for the emulator's virtio multitouch screen.

Writes struct input_event records straight into /dev/input/eventN (the virtio_input_multi_touch_1 device), so
the events take the same path as a real finger: evdev -> EventHub -> InputReader -> InputDispatcher -> app.
(`adb shell input swipe` instead injects MotionEvents at the InputDispatcher, and under TCG it manages only a
few samples per gesture because `input` is a Java process.)

A mksh script is generated on the host, pushed, and run in one guest shell: `print -n -u3` writes the binary
records (no process spawn per event) and `read -t` on a FIFO paces the frames.

usage (screen pixels, 720x1280 AVD):
  touch.py swipe X1 Y1 X2 Y2 DURATION_MS [--hold-ms N] [--frame-ms 16] [--release-hold-ms N]
  touch.py tap X Y [--hold-ms 50]
  touch.py press X Y HOLD_MS          (finger down, wait, up — for :active)
--hold-ms: stay still after touching down before moving; --release-hold-ms: stay still at the end before lifting
(0 => lift while moving, i.e. a fling).
"""
import argparse, os, struct, subprocess, sys, tempfile

ADB = os.environ.get('ADB', os.path.join(os.environ.get('ANDROID_ROOT', os.path.expanduser('~/android')), 'sdk/platform-tools/adb'))
W, H = int(os.environ.get('SCREEN_W', 720)), int(os.environ.get('SCREEN_H', 1280))
EV_SYN, EV_ABS = 0, 3
ABS_MT_SLOT, ABS_MT_TOUCH_MAJOR, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x2f, 0x30, 0x35, 0x36
ABS_MT_TOOL_TYPE, ABS_MT_TRACKING_ID, ABS_MT_PRESSURE = 0x37, 0x39, 0x3a


def ev(t, c, v):
    return struct.pack('<qqHHi', 0, 0, t, c, v)  # timeval is ignored on write; kernel stamps it


def esc(b):
    return ''.join('\\0%03o' % x for x in b)


def sx(x): return round(x * 32767 / (W - 1))
def sy(y): return round(y * 32767 / (H - 1))


def frames_swipe(x1, y1, x2, y2, dur, frame, hold, rhold):
    f = []  # list of (bytes, delay_ms_after)
    down = (ev(EV_ABS, ABS_MT_SLOT, 0) + ev(EV_ABS, ABS_MT_TRACKING_ID, 1) + ev(EV_ABS, ABS_MT_TOOL_TYPE, 0)
            + ev(EV_ABS, ABS_MT_TOUCH_MAJOR, 5) + ev(EV_ABS, ABS_MT_PRESSURE, 512)
            + ev(EV_ABS, ABS_MT_POSITION_X, sx(x1)) + ev(EV_ABS, ABS_MT_POSITION_Y, sy(y1)) + ev(EV_SYN, 0, 0))
    f.append((down, hold if hold else frame))
    n = max(1, round(dur / frame)) if dur else 0
    for i in range(1, n + 1):
        x, y = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
        f.append((ev(EV_ABS, ABS_MT_POSITION_X, sx(x)) + ev(EV_ABS, ABS_MT_POSITION_Y, sy(y)) + ev(EV_SYN, 0, 0),
                  frame if i < n else rhold))
    f.append((ev(EV_ABS, ABS_MT_TRACKING_ID, -1) + ev(EV_SYN, 0, 0), 0))
    return f


def script(frames, overhead_ms):
    lines = ['dev=$(getevent -pl 2>/dev/null | grep -B1 \'"virtio_input_multi_touch_1"\' | head -1 | sed "s/.*: //")',
             'f=/data/local/tmp/touch_tick; [ -p $f ] || mkfifo $f; exec 4<>$f; exec 3>$dev']
    for data, delay in frames:
        lines.append('print -n -u3 "%s"' % esc(data))
        d = max(0, delay - overhead_ms)
        if d:
            lines.append('read -t %.3f -u4 _' % (d / 1000))
    lines.append('exec 3>&-')
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['swipe', 'tap', 'press'])
    p.add_argument('nums', type=float, nargs='+')
    p.add_argument('--hold-ms', type=float, default=0)
    p.add_argument('--release-hold-ms', type=float, default=0)
    p.add_argument('--frame-ms', type=float, default=16)
    p.add_argument('--overhead-ms', type=float, default=float(os.environ.get('TOUCH_OVERHEAD_MS', 6)))
    p.add_argument('--print', action='store_true', help='print the guest script instead of running it')
    a = p.parse_args()
    if a.cmd == 'swipe':
        x1, y1, x2, y2, dur = a.nums
        fr = frames_swipe(x1, y1, x2, y2, dur, a.frame_ms, a.hold_ms, a.release_hold_ms)
    elif a.cmd == 'tap':
        x, y = a.nums[:2]
        fr = frames_swipe(x, y, x, y, 0, a.frame_ms, a.hold_ms or 50, 0)
    else:
        x, y, hold = a.nums
        fr = frames_swipe(x, y, x, y, 0, a.frame_ms, hold, 0)
    s = script(fr, a.overhead_ms)
    if a.print:
        sys.stdout.write(s); return
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as t:
        t.write(s)
    try:
        subprocess.run([ADB, 'push', '-q', t.name, '/data/local/tmp/touch.sh'], check=True)
        subprocess.run([ADB, 'shell', 'sh /data/local/tmp/touch.sh'], check=True)
    finally:
        os.unlink(t.name)


if __name__ == '__main__':
    main()
