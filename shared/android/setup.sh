#!/bin/bash
# One-time setup of the Android emulator (README.md): downloads the emulator, platform-tools, an x86_64 Android 17
# Google APIs image and a Chromium for Android snapshot (official Google URLs, about 3.7 GB), unpacks them into
# $ANDROID_ROOT (default ~/android; about 12 GB in all) and writes the AVD. Skips what is already there.
#   DL_CACHE=<dir with the dl-* folders of an earlier setup>: reuse its zips instead of downloading.
set -eu
. "$(dirname "${BASH_SOURCE[0]}")/env.sh"
mkdir -p "$ANDROID_ROOT" "$ANDROID_HOME/platforms" "$ANDROID_AVD_HOME" "$LOGDIR"
# (name, url): each zip goes into its own fresh dl-<name> folder (downloads are data: unpacked, never run from there)
get() {
  local d="$ANDROID_ROOT/dl-$1" f; f="$d/$(basename "$2")"; mkdir -p "$d"
  [ -s "$f" ] && return
  if [ -n "${DL_CACHE:-}" ] && [ -s "$DL_CACHE/dl-$1/$(basename "$2")" ]; then cp "$DL_CACHE/dl-$1/$(basename "$2")" "$f"; return; fi
  echo "$(ts) downloading $2"; curl -fL --retry 3 -o "$f.part" "$2" && mv "$f.part" "$f"
}
unz() { python3 -I "$HERE/unzip.py" "$1" "$2"; }
get emulator https://dl.google.com/android/repository/emulator-linux_x64-16555280.zip
get platform-tools https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip
get sysimg-x86_64-37.0 https://dl.google.com/android/repository/sys-img/google_apis/x86_64-37.0_r06.zip
get chromium-androiddesktop-x64 https://commondatastorage.googleapis.com/chromium-browser-snapshots/AndroidDesktop_x64/1721456/chrome-android-desktop.zip
[ -x "$ANDROID_HOME/emulator/emulator" ] || unz "$ANDROID_ROOT"/dl-emulator/*.zip "$ANDROID_HOME"
[ -x "$ANDROID_HOME/platform-tools/adb" ] || unz "$ANDROID_ROOT"/dl-platform-tools/*.zip "$ANDROID_HOME"
SYS=$ANDROID_HOME/system-images/android-37.0/google_apis
[ -f "$SYS/x86_64/kernel-ranchu" ] || { mkdir -p "$SYS"; unz "$ANDROID_ROOT"/dl-sysimg-x86_64-37.0/*.zip "$SYS"; }
if [ ! -s "$CHROMIUM_APK" ]; then
  T=$(mktemp -d); unz "$ANDROID_ROOT"/dl-chromium-androiddesktop-x64/chrome-android-desktop.zip "$T"
  mv "$T/chrome-android-desktop/apks/ChromePublic.apk" "$CHROMIUM_APK"; rm -rf "$T"
fi
# the AVD: 8 vCPUs, 4 GB, 720x1280 at 320 dpi (a 360x640 CSS viewport at DPR 2), software GPU, no sensors or modem
if [ ! -f "$ANDROID_AVD_HOME/$AVD.ini" ]; then
  mkdir -p "$ANDROID_AVD_HOME/$AVD.avd"
  printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-37.0\n' "$ANDROID_AVD_HOME/$AVD.avd" > "$ANDROID_AVD_HOME/$AVD.ini"
  cat > "$ANDROID_AVD_HOME/$AVD.avd/config.ini" <<EOF
AvdId=$AVD
avd.ini.displayname=$AVD
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=8
hw.ramSize=4096
disk.dataPartition.size=8G
image.sysdir.1=system-images/android-37.0/google_apis/x86_64/
tag.id=google_apis
tag.display=Google APIs
hw.lcd.width=720
hw.lcd.height=1280
hw.lcd.density=320
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
hw.keyboard=yes
hw.mainKeys=no
hw.camera.back=none
hw.camera.front=none
hw.audioInput=no
hw.audioOutput=no
hw.sensors.proximity=no
hw.gsmModem=no
hw.accelerometer=no
hw.gyroscope=no
hw.sensors.magnetic_field=no
hw.sensors.orientation=no
hw.sensors.temperature=no
hw.sensors.light=no
hw.sensors.pressure=no
hw.sensors.humidity=no
hw.sensors.hinge=no
hw.gps=no
hw.battery=yes
EOF
fi
echo "$(ts) set up in $ANDROID_ROOT ($(du -sh "$ANDROID_ROOT" | cut -f1)); start it with start.sh"
