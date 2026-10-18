# Sourced by setup.sh / start.sh / stop.sh.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export ANDROID_ROOT=${ANDROID_ROOT:-$HOME/android}   # SDK, AVD and downloads (about 12 GB), outside the repo
export ANDROID_HOME=$ANDROID_ROOT/sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export ANDROID_AVD_HOME=$ANDROID_ROOT/avd
export ANDROID_I_WANT_MY_TCG=yes          # the emulator's own escape hatch for -accel off (no /dev/kvm here)
ADB=$ANDROID_HOME/platform-tools/adb
EMU=$ANDROID_HOME/emulator/emulator
AVD=${AVD:-x64}
LOGDIR=$ANDROID_ROOT/logs
QEMU_PAT="^$ANDROID_HOME/emulator/qemu/"
CDP_PORT=${CDP_PORT:-9222}
PAGE_PORT=${PAGE_PORT:-8790}             # host port reverse-forwarded into the guest (adb reverse)
CHROME_PKG=${CHROME_PKG:-org.chromium.chrome}   # Chromium snapshot (AndroidDesktop_x64 r1721456, 158.0.8111.0); stable com.android.chrome 145's renderers crash under TCG
CHROME_FLAGS='--disable-fre --no-default-browser-check --no-first-run --disable-gpu-watchdog --disable-hang-monitor --disable-gpu-process-crash-limit'
CHROMIUM_APK=$ANDROID_ROOT/dl-chromium-androiddesktop-x64/ChromePublic.apk
ts() { date +%H:%M:%S; }
since() { echo $(( $(date +%s) - $1 )); }
