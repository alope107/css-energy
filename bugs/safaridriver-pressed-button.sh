#!/bin/bash
# safaridriver forgets a pressed mouse button after the first actions command that follows the press.
# Run on a Mac with `safaridriver -p 4444` running (Safari: Develop > Allow Remote Automation). WebDriver commands only,
# so this is a script rather than an HTML page. It presses the mouse on a box, then moves it in three separate
# "Perform Actions" commands, reading the box's :active state after each. PASS: active after every move.
#   SAFARIDRIVER=http://192.168.65.254:4444 bash safaridriver-pressed-button.sh   (from the css-energy devcontainer)
D=${SAFARIDRIVER:-http://localhost:4444}
H=(-s -H "Host: localhost:${D##*:}" -H 'Content-Type: application/json')
S=$(curl "${H[@]}" -X POST "$D/session" -d '{"capabilities":{"alwaysMatch":{"browserName":"safari"}}}' |
  python3 -c 'import sys,json;print(json.load(sys.stdin)["value"]["sessionId"])')
trap 'curl "${H[@]}" -X DELETE "$D/session/$S" >/dev/null' EXIT
page='<div id=b style=%27position:fixed;left:50px;top:50px;width:300px;height:100px;background:%23ccc;user-select:none%27></div>'
curl "${H[@]}" -X POST "$D/session/$S/url" -d "{\"url\":\"data:text/html,$page\"}" >/dev/null
act() { curl "${H[@]}" -X POST "$D/session/$S/actions" -d "{\"actions\":[{\"type\":\"pointer\",\"id\":\"m\",\"parameters\":{\"pointerType\":\"mouse\"},\"actions\":[$1]}]}" >/dev/null; }
active() { curl "${H[@]}" -X POST "$D/session/$S/execute/sync" -d '{"script":"return document.querySelector(\"#b:active\") ? 1 : 0","args":[]}' |
  python3 -c 'import sys,json;print(json.load(sys.stdin)["value"])'; }
act '{"type":"pointerMove","origin":"viewport","x":80,"y":100}'
act '{"type":"pointerDown","button":0}'; r="down:$(active)"
for k in 1 2 3; do act "{\"type\":\"pointerMove\",\"origin\":\"viewport\",\"x\":$((80 + 6 * k)),\"y\":100}"; r="$r move$k:$(active)"; done
act '{"type":"pointerUp","button":0}'
echo "$r"
case "$r" in *:0*) echo "FAIL: :active lost while the button is down (the move after the first is sent without it)";; *) echo PASS;; esac
# Observed (2026-10-25): Safari 26.6.2 (macOS 25G83): down:1 move1:1 move2:0 move3:0, FAIL. The page's events say
# buttons 1 throughout, and no mouseup arrives until the release. All in one actions command (down, moves with
# pauses, up), :active holds. A pointerDown at the start of each later move command keeps it (the page then gets
# another mousedown each time: safaridriver had forgotten the button, so the pointerDown isn't the no-op it should be).
# Spec (WebDriver §17.4, "input state"): the input state, pressed buttons included, persists between Perform Actions
# commands until Release Actions. Chromium (CDP/Playwright) keeps :active through the same sequence.
