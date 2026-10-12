# Typed JavaScript, compiled by CSS, run by a font

`fontcpu/js_in_css.xhtml` is the page. It needs Chrome, and no script runs on it. Type a program, press Run,
and read the output in the console on the left. Edit clears the machine.

The page is XHTML because the compile chain is about 2,000 elements deep, and the HTML parser stops nesting
at 512.

## Pipeline

1. **Editor readback** (`ui/ui_rb.py`; the font comes from `ui/mkfont2.py`, from the CSS Text Readback chat).
   - A variable font axis copies the code of one column into a sentinel glyph's width.
   - Probes measure that width, and each line × column has a latch cell.
   - The scan is frame-locked: view-timeline registers keep the previous frame's clock and a counter, so the
     scan moves exactly one column per frame at any frame rate.
   - The scan range is fixed at 64 columns. A range taken from the editor's width flickers, because it
     includes the sentinel.
   - After Run, the scan does one more full sweep, then stops and raises a flag. That flag shows the compiler.
2. **Character chain** (`ccpage5.py`): one element per slot, 24 lines × 65.
   - Each latch cell is a view-timeline register. One source element per line animates the line's codes into
     custom properties.
   - The lexer is specialized per character class, picked by the parent's class via container query.
   - Completed tokens go into token registers, view timelines named by an `if()` mux on the token index.
3. **Token chain**: one element per token.
   - Parser variants are selected by `@container style(--vh: mode) and style(--tcq: token-code)`.
   - The parser emits code words as fixed overlays named after their RAM cells, the same handoff as before.
4. **Font CPU**: `gen_fvm4.py` with `UI=1`.
   - It stays hidden until the compiler reports done: `--ccdone` is read through a register.
   - It is reset by Edit: held registers × `--run`, and the RAM leaves are forced back to zero.

## Tests

```
python3 ui_test.py prog.js out.xhtml          # compiler alone, fed by fake latch cells
node uitest.js out.xhtml > o.json && python3 uicheck.py prog.js o.json 24 64
node fontcpu/ui_seq.js js_in_css.xhtml prog expected ...   # the whole page, typed like a user
```

## Limits

- Programs are up to 24 lines of 64 columns.
- Paste as plain text.
- Undefined functions aren't reported.
