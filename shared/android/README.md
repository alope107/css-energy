# shared/android/

A real Chromium for Android in the devcontainer, for checking touch behaviour on Android's own input path. The
container has no `/dev/kvm`, so the emulator runs under software emulation (TCG): it boots in about 5 minutes, pages
render slowly, and only touch *semantics* are worth reading from it, not timing or feel.

```bash
bash shared/android/setup.sh             # once: about 3.7 GB of official downloads, 12 GB unpacked, in ~/android
SERVE_DIR=$PWD bash shared/android/start.sh http://127.0.0.1:8790/css-physics/experiments/touch/handles.html
node css-physics/experiments/touch/android.js          # gestures and readings, below
bash shared/android/stop.sh              # stops the emulator, the page server and adb
```

`start.sh` takes about 9 minutes from a cold boot: the device appears after about 70 s, `boot_completed` comes after
5 minutes, and Chromium's devtools socket a few minutes after that. The first start of a new AVD takes 30 minutes
(18 to `boot_completed`, then installing Chromium), and the guest stays busy for a few minutes more: wait before
testing gestures. It serves `SERVE_DIR` on 127.0.0.1:8790
(`adb reverse`), opens the URL and forwards CDP to localhost:9222. Snapshots don't work here, so every start is cold.

## What runs

- The SDK emulator 37.3.4 with the x86_64 Android 17 (API 37.0) Google APIs image: 8 vCPUs, 4 GB, 720×1280 at
  320 dpi, so a 360-wide CSS viewport at DPR 2.
- Chromium 158.0.8111.0, the official `AndroidDesktop_x64` snapshot r1721456 (`org.chromium.chrome`). It's the
  only x86_64 Android build among the snapshots. It's the "desktop Android" flavour, with the toolbar at the bottom,
  but its UA says Mobile and `(pointer: coarse)` matches. The image's own Chrome 145 crashes its renderers under TCG.

## What it took (`start.sh` does all of it)

- `ANDROID_I_WANT_MY_TCG=yes` lets the emulator run with `-accel off`. `-qemu -accel tcg,thread=multi` gives each
  vCPU its own host thread.
- `ro.hw_timeout_multiplier=20`, set as root before restarting the framework. Without it, system_server's watchdog
  kills it every 60 s.
- `-feature -ModemSimulator`, and the radio and bluetooth HALs stopped (they spin). GMS and the other heavy Google
  apps are disabled (`debloat.sh`; this persists in userdata).
- Kernel `clocksource=tsc`. The default HPET put 100–250 ms of latency on every input event.
- `long_press_timeout` is set to 2000 ms, so that slow input delivery doesn't turn drags into long presses.

## Touch

`touch.py` writes kernel input events to the virtio touchscreen at about 60 Hz, so a gesture takes the real path:
evdev → InputReader → InputDispatcher → Chrome's gesture detector. Use it, not `adb shell input swipe`, which manages
only 3–12 moves per gesture here. Screen pixels are 720×1280; `android.js` calibrates them to the page with a tap.

What it is good for, and what synthetic CDP touch on desktop (`css-physics/tools/touchcheck.js`) can't show:

- **Show-press:** `:active` and `:hover` appear on a finger held still, and `:active` clears when the finger starts
  to scroll.
- **Android's gesture timings and Chrome's Android input path,** which is a different port from the desktop's.

What it isn't good for:

- **Distances:** input is delivered late and sometimes in batches, so drags come out shorter than the finger moved.
- **Some drags never start:** when the browser is busy, the first move can arrive hundreds of ms late, and Chrome
  never starts a scroll. Short horizontal drags (120 screen px in 500 ms) missed 2 times in 5 on a plain scroller
  page and 5 in 8 on the handles page; a 1 s vertical drag after a 300 ms rest never missed on the plain page (6 of
  6). More main-thread work seems to mean more misses, so a miss here doesn't say a phone would miss.
- **Event order on fast flicks:** a fast flick can come out as `pointerup` instead of `pointercancel`.
- **Frame rate:** the full css-physics engine renders at about 1 frame per second. Test the mechanism on a small
  page such as `css-physics/experiments/touch/handles.html`.

`cdp.js` is a small CDP client: `list`, `eval '<expr>' [url substring]`, `navigate <url>`.
