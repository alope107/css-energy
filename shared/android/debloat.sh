#!/bin/bash
# Disable heavy Google/AOSP apps in the guest (persists in userdata). Needs a running device.
A=${ADB:-${ANDROID_ROOT:-$HOME/android}/sdk/platform-tools/adb}
PKGS="com.google.android.gms com.google.android.gsf com.android.vending com.google.android.googlequicksearchbox
com.google.android.apps.bard com.google.android.apps.docs com.google.android.apps.maps com.google.android.apps.messaging
com.google.android.apps.photos com.google.android.apps.pulse com.google.android.apps.restore com.google.android.apps.safetyhub
com.google.android.apps.wellbeing com.google.android.apps.youtube.music com.google.android.youtube com.google.android.as
com.google.android.as.oss com.google.android.calendar com.google.android.contacts com.google.android.deskclock
com.google.android.dialer com.google.android.gm com.google.android.glasses.companion com.google.android.glasses.core
com.google.android.projection.gearhead com.google.android.marvin.talkback com.google.android.apps.accessibility.voiceaccess
com.google.android.accessibility.switchaccess com.google.android.tts com.google.android.feedback com.google.android.partnersetup
com.google.android.settings.intelligence com.google.android.odad com.google.android.federatedcompute
com.google.android.healthconnect.controller com.google.android.googlesdksetup com.google.android.inputmethod.latin
com.android.camera2 com.android.DeviceAsWebcam com.google.android.cellbroadcastreceiver com.android.cellbroadcastreceiver
com.google.android.apps.customization.pixel com.google.android.apps.wallpaper com.google.android.webapp.service
com.google.android.markup com.android.stk com.android.dreams.basic "
$A shell "for p in $(echo $PKGS | tr '\n' ' '); do cmd package disable-user --user 0 \$p >/dev/null 2>&1 && echo -n \"\$p \" ; done; echo"
