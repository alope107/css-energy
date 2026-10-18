#!/bin/bash
# Cold boot the x86_64 Android 17 (API 37.0, Google APIs) emulator under TCG (no KVM), make it survive being slow,
# launch Chrome on a URL and forward CDP to localhost:$CDP_PORT.
#
# usage: start.sh [URL]      default URL: http://127.0.0.1:$PAGE_PORT/scroll.html (served by this script from
#                            $HERE/testpages unless SERVE_DIR is set or SERVE=0)
#
# Env: CHROME_PKG (default org.chromium.chrome; com.android.chrome = the image's Chrome 145, whose renderers crash
# here), PAGE_PORT (8790), CDP_PORT (9222), SERVE=0 / SERVE_DIR=<dir> for the page server.
# Takes ~9 min (boot ~5 min, Chromium's first page + devtools socket ~3 min). Stop with stop.sh.
set -u
. "$(dirname "${BASH_SOURCE[0]}")/env.sh"
URL=${1:-http://127.0.0.1:$PAGE_PORT/scroll.html}
mkdir -p "$LOGDIR"
T0=$(date +%s)

if pgrep -f "$QEMU_PAT" >/dev/null; then echo "emulator already running (stop.sh first)"; exit 1; fi

echo "$(ts) cold boot (quickboot snapshots did not restore here: \"Device 'cache' does not have the requested snapshot\")"

# The emulator's own kernel cmdline (see emulator.log) with clocksource=pit swapped for TSC: without it the guest
# falls back to HPET, and every clock read is an MMIO exit into QEMU under its global lock (input latency of
# 100-250 ms in system_server's EventHub). QEMU uses the last -append, so this replaces the emulator's.
KERNEL_APPEND='8250.nr_uarts=1 clocksource=tsc tsc=reliable no_timer_check console=0 loop.max_part=7 ramoops.mem_address=0xff018000 ramoops.mem_size=0x10000 memmap=0x10000$0xff018000 printk.devkmsg=on bootconfig'
# -accel off + ANDROID_I_WANT_MY_TCG: software CPU. -qemu -accel tcg,thread=multi: one host thread per vCPU (MTTCG);
# without it all vCPUs share one host thread.
nohup "$EMU" -avd "$AVD" -no-window -no-audio -no-boot-anim -accel off -gpu swiftshader_indirect \
  -feature -ModemSimulator -no-snapshot -qemu -accel tcg,thread=multi -append "$KERNEL_APPEND" > "$LOGDIR/emulator.log" 2>&1 &
echo $! > "$LOGDIR/emulator.pid"

"$ADB" start-server >/dev/null 2>&1
timeout 600 "$ADB" wait-for-device || { echo "no adb device after $(since $T0)s; see $LOGDIR/emulator.log"; exit 1; }
echo "$(ts) adb device after $(since $T0)s"

"$ADB" root >/dev/null 2>&1; sleep 3; timeout 300 "$ADB" wait-for-device
# Tuning is skipped if the guest already has it (e.g. start.sh re-run against a running emulator).
NEED_TUNE=; [ "$("$ADB" shell getprop ro.hw_timeout_multiplier | tr -d '\r')" = 20 ] || NEED_TUNE=1
if [ -n "$NEED_TUNE" ]; then
  # system_server's Watchdog kills it after 60 s blocked; ANR/broadcast timeouts are similar. Android scales them by
  # ro.hw_timeout_multiplier (Build.HW_TIMEOUT_MULTIPLIER), which this image leaves unset. It's a ro. property, so set
  # it as root before anything sets it, then restart the framework so zygote/system_server read it.
  "$ADB" shell 'setprop ro.hw_timeout_multiplier 20'
  echo "$(ts) cold boot: ro.hw_timeout_multiplier=$("$ADB" shell getprop ro.hw_timeout_multiplier | tr -d '\r'); restarting framework"
  "$ADB" shell 'stop; start'
else
  echo "$(ts) guest already tuned"
fi

until [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do
  sleep 5
  if ! pgrep -f "$QEMU_PAT" >/dev/null; then echo "emulator died; see $LOGDIR/emulator.log"; exit 1; fi
  [ $(since $T0) -gt 1800 ] && { echo "boot not complete after 30 min"; exit 1; }
done
echo "$(ts) boot_completed after $(since $T0)s"

if [ -n "$NEED_TUNE" ]; then
  # radio HAL spins (it can't reach the emulator's modem), bluetooth HAL crash-loops: stop both.
  "$ADB" shell 'stop vendor.radio-ranchu; stop vendor.bluetooth-default; svc power stayon true;
    settings put global window_animation_scale 0; settings put global transition_animation_scale 0;
    settings put global animator_duration_scale 0; settings put global bluetooth_on 0'
  # Input reaches apps with 100+ ms latency here; with the default 400 ms the long-press timer can fire before
  # the first touchmove is processed and the drag never becomes a scroll. (Persists in userdata.)
  "$ADB" shell 'settings put secure long_press_timeout 2000'
  # GMS, the Google app etc. saturate the vCPUs; disabling them persists in userdata, so only the first boot pays.
  "$ADB" shell pm list packages -e com.google.android.gms | grep -q 'gms$' && "$HERE/debloat.sh" >/dev/null
  "$ADB" shell "echo '_ $CHROME_FLAGS' > /data/local/tmp/chrome-command-line; chmod 644 /data/local/tmp/chrome-command-line"
  if [ "$CHROME_PKG" = org.chromium.chrome ] && ! "$ADB" shell pm path org.chromium.chrome | grep -q package; then
    "$ADB" shell 'setprop pm.dexopt.install verify'   # skip AOT compiling the 420 MB APK
    "$ADB" install -r -g "$CHROMIUM_APK" >/dev/null && echo "$(ts) installed Chromium"
  fi
  # the notification-permission dialog would otherwise sit on top of the page and eat the first touches
  "$ADB" shell "pm grant $CHROME_PKG android.permission.POST_NOTIFICATIONS 2>/dev/null; am force-stop com.android.chrome"
  "$ADB" shell am set-debug-app --persistent "$CHROME_PKG" >/dev/null   # makes Chrome read the command-line file
  echo "$(ts) guest tuned after $(since $T0)s"
fi

if [ "${SERVE:-1}" = 1 ] && ! curl -s -o /dev/null "http://127.0.0.1:$PAGE_PORT/"; then
  nohup python3 -m http.server "$PAGE_PORT" --bind 127.0.0.1 --directory "${SERVE_DIR:-$HERE/testpages}" \
    > "$LOGDIR/http.log" 2>&1 &
  echo $! > "$LOGDIR/http.pid"
fi
"$ADB" reverse "tcp:$PAGE_PORT" "tcp:$PAGE_PORT" >/dev/null

"$ADB" shell am start -a android.intent.action.VIEW -d "'$URL'" "$CHROME_PKG" >/dev/null
echo "$(ts) Chrome launched on $URL; waiting for its devtools socket"
until "$ADB" shell 'grep -aq chrome_devtools_remote /proc/net/unix' 2>/dev/null; do
  sleep 5; [ $(since $T0) -gt 2400 ] && { echo "no devtools socket"; exit 1; }
done
"$ADB" forward "tcp:$CDP_PORT" localabstract:chrome_devtools_remote >/dev/null
echo "$(ts) CDP at http://127.0.0.1:$CDP_PORT (total $(since $T0)s)"
curl -s "http://127.0.0.1:$CDP_PORT/json/version" | grep -E '"Browser"'
