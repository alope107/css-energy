"""Strip families of gated @container blocks from a (usually frozen) PLAIN page, to measure what they cost.

  python3 tools/ablate.py out/FZ_x.html pairs=--(tcp|np|p\\d+_\\d+(uA|uB|ov)) ac=--ac\\d all=.
  -> out/FZ_x_pairs.html, out/FZ_x_ac.html, out/FZ_x_all.html  (then: node tools/tr.js a.html,b.html,...)

Each NAME=REGEX removes every top-level @container block whose condition matches REGEX (brace-matched).
Removing one gate family changes downstream gates, so deltas overlap; read them as rough attributions.
The implementation is shared with js-minus-js: ../../shared/py/ablate.py."""
import os, runpy
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py', 'ablate.py'), run_name='__main__')
