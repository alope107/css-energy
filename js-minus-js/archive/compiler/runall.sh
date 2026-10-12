#!/bin/sh
# build + check every test program in Chromium with ccpage4
for f in fizz.js tests/t1.js tests/t2.js tests/t3.js tests/t4.js tests/e1.js tests/e2.js; do
  b=$(basename $f .js); python3 ccpage4.py $f lib.json /tmp/cc_$b > /dev/null && python3 cctest.py /tmp/cc_$b && node cctest.js /tmp/cc_${b}_test.html > /tmp/cc_$b.json
  echo "== $b: $(python3 cccheck.py $f /tmp/cc_$b.json | tr '\n' ' ')"
done
