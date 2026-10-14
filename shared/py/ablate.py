"""Copies of a page with families of gated @container blocks removed, to measure what they cost (no browser).

  python3 ablate.py page.html NAME=REGEX [NAME=REGEX ...]
  -> page_NAME.html (page_NAME.xhtml for an .xhtml page) per argument, then compare them with a timing tool

Each NAME=REGEX removes every @container block whose condition matches REGEX (brace-matched). A block inside a removed
block goes with it; a matching block nested in a kept one is removed on its own. Braces inside CSS strings and comments
don't count, so `content: "{"` can't end a block. The source page is never overwritten.
Removing one gate family changes downstream gates, so deltas overlap; read them as rough attributions.

css-physics: tools/ablate.py (its docs: a frozen PLAIN page, pairs=--(tcp|np|p\\d+_\\d+(uA|uB|ov)) ac=--ac\\d all=.).
"""
import re, sys


def block_end(s, j):
    """s[j-1] is the '{' that opens a block: the index just past its matching '}'"""
    d = 1
    while d:
        c = s[j]
        if c == '/' and s.startswith('/*', j):
            j = s.index('*/', j + 2) + 2
            continue
        if c in '"\'':
            k = j + 1
            while s[k] != c:
                k += 2 if s[k] == '\\' else 1
            j = k + 1
            continue
        d += c == '{'
        d -= c == '}'
        j += 1
    return j


def strip(s, pat):
    """s with every @container block whose condition matches pat removed, and how many were"""
    out, i, n = [], 0, 0
    for m in re.finditer(r'@container ([^{]*)\{', s):
        if m.start() < i:
            continue
        if re.search(pat, m.group(1)):
            out.append(s[i:m.start()])
            i, n = block_end(s, m.end()), n + 1
    out.append(s[i:])
    return ''.join(out), n


def out_name(src, name):
    m = re.search(r'(\.x?html?)$', src)
    dst = src[:m.start()] + f'_{name}' + m.group(1) if m else f'{src}_{name}'
    assert dst != src
    return dst


if __name__ == '__main__':
    src = sys.argv[1]
    s = open(src).read()
    for arg in sys.argv[2:]:
        name, pat = arg.split('=', 1)
        t, n = strip(s, pat)
        dst = out_name(src, name)
        open(dst, 'w').write(t)
        print(f'{dst}: removed {n} blocks, {len(s) - len(t)} bytes')
