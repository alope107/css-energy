#!/bin/sh
# runtests.sh [ui] — every test level. Browser levels need playwright-core (PW=module path) and Chrome (CHROME=path).
#   oracle  node suite_expect.js suite      : Node runs each suite/*.js and writes the expected output (*.out)
#   L1      suite_ref.py                    : reference compiler + bytecode simulator (20-bit words) vs Node
#   L2      cmp_dsl.py                      : the CSS compiler's DSL, evaluated in Python level by level, vs the reference:
#                                             parser state, tables, every code word, label and data word (SPEC=1: the
#                                             mode/token-specialised variants and class-specialised lexers the page uses)
#   L3      suite_css.py + suite_css.js     : the generated CSS compiler in Chrome (one page, programs written into its
#                                             latch cells) vs the reference, word for word; suite_err/ must be rejected
#   L4      suite_machine.py                : the font CPU's model (uarch4: 4-word cache lines, traps) runs each compiled
#                                             image vs Node
#   L5      ui_seq.js (with 'ui')           : the real page: type each program, Run, read the console (8 x 16 grid)
set -e
cd "$(dirname "$0")"
node suite_expect.js suite
echo "== L1 reference vs Node";            python3 suite_ref.py | tail -3
echo "== L2 DSL vs reference";             SPEC=1 python3 cmp_dsl.py suite/*.js suite_err/*.js | tail -1
echo "== L4 machine model vs Node";        python3 suite_machine.py | tail -3
echo "== L3 CSS compiler in Chrome";       REBUILD=1 python3 suite_css.py /tmp/suite_css.xhtml >/dev/null && node suite_css.js /tmp/suite_css.xhtml | tail -1
if [ "$1" = ui ]; then
  echo "== L5 the page, typed like a user (needs fontcpu/js_in_css.xhtml)"
  node ../fontcpu/ui_seq.js ../fontcpu/js_in_css.xhtml $(python3 suite_ui.py 1500) | grep -c '"ok":true'
fi
