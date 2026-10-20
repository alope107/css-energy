# XHTML-parent tests (2026-10-16)

Pages contain no JavaScript; `run.py` is the Playwright harness.

quirks/   Is a no-doctype child quirks mode under an XHTML parent, and does it apply a CORS text/plain sheet?
          python3 srv.py 9471 & python3 srv.py 9472 &   # page origin, "third-party" origin
          python3 run.py
          (Expected: child_q / data: no-doctype -> BackCompat, sheet applied; doctype controls -> CSS1Compat, blocked.)
          Note: www/ has been edited across runs; regenerate the children if you change ports.

readback/ Fragment-scroll readback into p.html (control) and p.xhtml.
          python3 gen.py
          python3 srv.py 9481 & python3 srv.py 9482 &   # page origin, "third-party" API (value from v.txt)
          python3 run.py [chromium-executable]
          (Expected: both parents read 1334, 157, 3099, 100 = value + 100 base, as v.txt goes 1234, 57, 2999, 0.)
