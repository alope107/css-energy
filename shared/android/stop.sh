#!/bin/bash
# Stop the emulator, the page server start.sh started, and the adb server.
. "$(dirname "${BASH_SOURCE[0]}")/env.sh"
"$ADB" emu kill >/dev/null 2>&1
for i in $(seq 60); do pgrep -f "$QEMU_PAT" >/dev/null || break; sleep 1; done
pkill -f "$QEMU_PAT" 2>/dev/null; sleep 2; pkill -9 -f "$QEMU_PAT" 2>/dev/null
[ -f "$LOGDIR/http.pid" ] && kill "$(cat "$LOGDIR/http.pid")" 2>/dev/null; rm -f "$LOGDIR/http.pid"
"$ADB" kill-server >/dev/null 2>&1
pkill -f "$ANDROID_HOME/emulator/(netsimd|crashpad_handler)" 2>/dev/null
pgrep -af "$QEMU_PAT" && echo "emulator still running" || echo "stopped"
