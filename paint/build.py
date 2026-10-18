#!/usr/bin/env python3
"""Dictionary Paint, unlimited edition. No JavaScript.

Every cell is a same-origin <object> document in the namespace /c/<k>/. _redirects serves all cells from shared
files, and relative URLs inside a cell document resolve under /c/<k>/, so one file serves 480 cells.

  READ   the page shows 16 probes /c/k/r/<v>.png per cell (-> r/<v>.png), each compressed against
         dictionary v. Only the stored value's probe decodes; it decodes to a (v+1)x1 image, so the
         probe row is value+1 wide. (Reads must live in this one document: 480 frames dispatching
         their own probes at once exceed Chrome's outstanding-request limit and lose reads.)
  RETRY  a probe can fail outright: Cloudflare ends every connection after ~10,000 requests (HTTP/2 GOAWAY,
         HTTP/3 close) and Chrome drops some requests it had queued (ERR_FAILED, not retried), about 30 cells
         a load. A sentinel image after the grid, /s.png, loads once the first pass has gone out, and starts a
         second, /s.png?2, which queues behind what Chrome re-sent; 3 s after that every cell still blank shows
         a second probe row, /c/k/r/2/<v>.png (90 s after load if a sentinel fails).
         A cell never written pays its 16 probes twice.
  START  each cell holds 16 <object>s, /c/k/p/<v>, all display:none except the one for the
         value just read; a hidden <object> creates no frame and loads nothing. A never-written cell
         shows /c/k/x. (Not iframes: every <iframe> element takes one of Chrome's 1000 frames
         per page even while lazy and hidden, so 17 per cell stalls after ~59 cells.)
  WRITE  p/<v>.html loads ../d/<v>.png twice: as a CSS mask-image (registers at once) and through
         <link rel=compression-dictionary> (fetched when the network is idle, which can take ~30 s
         while the page is still reading). _headers makes it the dictionary for /c/k/r/*. Painting
         is a link to p/<u>: a new document, so writes are unlimited.
  UNDO   each paint is a history entry; Back reloads the previous p/<v>.html, which registers v
         again. Only the <link rel=compression-dictionary> does this: a history traversal serves
         every CSS-initiated fetch (mask-image, @import, fonts, prefetch) from cache, and a cached
         response never registers. Painting a cell its current colour is a same-URL navigation,
         which replaces the history entry instead of adding an undo step.
  INPUT  the <object> is (CELL + 1 + palette colour) px wide, clipped to CELL; the cell reads it
         with @media.
  LIMIT  undoing the first paint of a cell that was never written cannot erase it: x.html writes
         nothing, because "never written" and "read failed" look the same.

URLS   all page URLs are extensionless (/c/k/x, /c/k/p/5): Cloudflare Pages 308-redirects
         *.html to the extensionless path, and a redirect inside a rewrite would leave the cell's
         /c/<k>/ namespace. Files on disk keep .html; Pages serves p/5.html at /p/5.

Writes site/: cell.html, 16 p/*.html, 16 d/*.png, 16 r/*.png, s.png, index.html, _headers, _redirects.
usage: python3 build.py [W] [H]      (pip install zstandard)
"""
import os, sys, struct, zlib, hashlib
import zstandard

W = int(sys.argv[1]) if len(sys.argv) > 1 else 24
H = int(sys.argv[2]) if len(sys.argv) > 2 else 20
K, CELL = 16, 22
N = W * H
assert N <= 490, "Chrome keeps 500 dictionaries per top-level site"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
PALETTE = ["#f4efe4", "#1d1b1a", "#5b5853", "#a8a39a", "#ffffff", "#c8372d", "#e8743b", "#f2c14e",
           "#8fb339", "#2f7a4f", "#3cb4b4", "#2f5fa8", "#6b4ca8", "#d06aa0", "#8a5a3b", "#f6c8b0"]


def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def png(w, h, text=b""):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    if text:
        out += chunk(b"tEXt", b"k\x00" + text)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def dcz(dictionary, data):
    zd = zstandard.ZstdCompressionDict(dictionary, dict_type=zstandard.DICT_TYPE_RAWCONTENT)
    return (b"\x5e\x2a\x4d\x18\x20\x00\x00\x00" + hashlib.sha256(dictionary).digest()
            + zstandard.ZstdCompressor(dict_data=zd).compress(data))


for sub in ("d", "r", "p"):
    os.makedirs(f"{OUT}/{sub}", exist_ok=True)
for v in range(K):
    if not os.path.exists(f"{OUT}/d/{v}.png"):           # keep dictionaries stable across rebuilds
        open(f"{OUT}/d/{v}.png", "wb").write(png(1, 1, b"colour %d " % v + os.urandom(8).hex().encode()))
    open(f"{OUT}/r/{v}.png", "wb").write(dcz(open(f"{OUT}/d/{v}.png", "rb").read(), png(v + 1, 1)))
SENT = 8                                                  # the sentinel's width; it narrows the `done` container
open(f"{OUT}/s.png", "wb").write(png(SENT, 1))

open(f"{OUT}/_redirects", "w").write("""/c/:k/r/2/:v /r/:v 200
/c/:k/x /cell 200
/c/:k/p/:v /p/:v 200
/c/:k/r/:v /r/:v 200
/c/:k/d/:v /d/:v 200
""")
open(f"{OUT}/_headers", "w").write("""/c/:k/d/*
  Use-As-Dictionary: match="/c/:k/r/*"
  Cache-Control: public, max-age=31536000
  Vary: *
/c/:k/r/*
  Content-Encoding: dcz
  Cache-Control: no-store
  Vary: accept-encoding, available-dictionary
/c/:k/x
  Cache-Control: no-cache
/c/:k/p/*
  Cache-Control: no-store
/s.png
  Cache-Control: no-store
/
  Cache-Control: no-cache
""")

lookup = lambda var: "if(" + "".join(f"style({var}:{v}):var(--p{v});" for v in range(K)) + "else:transparent)"

# ------------------------------------------------------------------ shared cell CSS
cell_css = ":root{" + "".join(f"--p{v}:{c};" for v, c in enumerate(PALETTE)) + "}" + f"""
@property --bv{{syntax:'<integer>';inherits:false;initial-value:-1}}
html,body{{margin:0;height:100%;overflow:hidden;background:transparent}}
.px{{position:absolute;left:0;top:0;width:{CELL}px;height:{CELL}px}}
a{{display:none;position:absolute;left:0;top:0;width:{CELL}px;height:{CELL}px;z-index:2;cursor:crosshair}}
a:hover{{box-shadow:inset 0 0 0 2px var(--pc),inset 0 0 0 3px #fff8}}
""" + "".join(f"@media (width:{CELL + 1 + v}px){{:root{{--pc:var(--p{v})}}a.a{v}{{display:block}}}}" for v in range(K))
links = lambda prefix: "".join(f'<a class=a{v} href="{prefix}{v}" aria-label="paint colour {v}"></a>' for v in range(K))

# cell.html: a cell that was never written: transparent, paint links only, writes nothing
cell = f"""<!doctype html><meta charset=utf-8><title>cell</title><style>{cell_css}</style>{links('p/')}
"""
open(f"{OUT}/cell.html", "w").write(cell)

# p/<v>.html: write v, show v, offer paint links
for v in range(K):
    open(f"{OUT}/p/{v}.html", "w").write(f"""<!doctype html><meta charset=utf-8><title>cell</title><style>{cell_css}
.px{{background:var(--p{v})}}
.w{{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;mask-image:url(../d/{v}.png)}}
</style><link rel=compression-dictionary href="../d/{v}.png">
<b class=px></b><i class=w></i>{links('')}
""")

# ------------------------------------------------------------------ the page
page_css = ":root{" + "".join(f"--p{v}:{c};" for v, c in enumerate(PALETTE)) + "}" + f"""
@property --pal{{syntax:'<integer>';inherits:true;initial-value:1}}
@property --s{{syntax:'<number>';inherits:true;initial-value:1}}
@property --bv{{syntax:'<integer>';inherits:false;initial-value:-1}}
@property --go{{syntax:'<integer>';inherits:true;initial-value:0}}
:root{{--bg:#ebe5d8;--ink:#1d1b1a;--mute:#7c766c;--frame:#c9c1b1;--gw:{W * CELL}px}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141312;--ink:#ece6da;--mute:#8d867a;--frame:#3a3732}}}}
html,body{{margin:0;background:var(--bg);color:var(--ink)}}
body{{font:13px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,monospace;min-height:100vh;display:grid;
  place-items:center;padding:28px 16px;box-sizing:border-box;overflow-x:hidden}}
main{{--s:min(1,calc((100vw - 32px) / var(--gw)));width:calc(var(--gw) * var(--s))}}
header{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 14px}}
h1{{font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;margin:0}}
header span{{color:var(--mute);font-size:12px;text-align:right}}
.stage{{height:calc({H * CELL}px * var(--s))}}
/* RETRY: each .gd narrows by SENT px once its sentinel loads. /s.png follows the first pass of probes; /s.png?2
   is requested only then, so it also queues behind the probes Chrome re-sent after a GOAWAY */
.sig{{display:flex}}
.stage>.sig{{width:{W * CELL + SENT}px;transform-origin:0 0;scale:var(--s)}}
.gd{{flex:1 1 0;min-width:0;container:s1/inline-size}}
.gd .gd{{container-name:s2}}
.sig>i{{display:block;flex:none;opacity:0}}
.sig>i.s2{{display:none}}
@container s1 (width<{W * CELL + SENT // 2}px){{.sig>i.s2{{display:block}}}}
.grid{{display:grid;grid-template-columns:repeat({W},{CELL}px);width:var(--gw);background:var(--p0);outline:1px solid var(--frame);
  box-shadow:0 12px 30px -18px rgba(0,0,0,.35)}}
.c{{position:relative;width:{CELL}px;height:{CELL}px;overflow:hidden;anchor-scope:--rd,--rt}}
/* READ: the probe row is (stored value + 1) px wide; 0 = never written */
.rd{{position:absolute;left:0;top:0;display:flex;anchor-name:--rd;opacity:0;pointer-events:none}}
.rd i{{display:block;flex:none}}
.v{{position:absolute;left:0;top:0;height:0;width:anchor-size(--rd width);container-type:inline-size;
  animation:go-late 0s 90s forwards}}
/* a cell still 0 px wide after the first pass reads again, with fresh URLs; .w takes whichever row decoded */
@keyframes go{{from,to{{--go:1}}}}
@keyframes go-late{{from,to{{--go:1}}}}
@container s2 (width<{W * CELL - SENT // 2}px){{.v{{animation:go 0s 3s forwards}}}}
.rt{{position:absolute;left:0;top:0;display:none;anchor-name:--rt;opacity:0;pointer-events:none}}
.rt i{{display:block;flex:none}}
@container (width:0px){{.rt{{display:if(style(--go:1):flex;else:none)}}}}
.w{{position:absolute;left:0;top:0;height:0;width:max(100cqw,anchor-size(--rt width,0px));container-type:inline-size}}
.px{{position:absolute;left:0;top:0;width:{CELL}px;height:{CELL}px;--bv:calc(100cqw / 1px - 1);background:{lookup('--bv')}}}
/* the cell document's width carries the palette colour; only the object for the value read is
   shown, and a hidden <object> never loads */
.c object{{position:absolute;left:0;top:0;display:none;border:0;color-scheme:normal;
  width:calc({CELL + 1}px + var(--pal) * 1px);height:{CELL}px}}
@container (width:0px){{.c object.x{{display:block}}}}
""" + "".join(f"@container (width:{v + 1}px){{.c object.f{v}{{display:block}}}}" for v in range(K)) + f"""
.pal{{display:grid;grid-template-columns:repeat(16,1fr);gap:4px;margin:14px 0 0}}
.pal input{{position:absolute;opacity:0;pointer-events:none}}
.pal label{{aspect-ratio:1;border-radius:3px;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(0,0,0,.12)}}
.pal input:checked+label{{box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--ink)}}
.pal input:focus-visible+label{{outline:2px solid var(--ink);outline-offset:4px}}
p{{color:var(--mute);font-size:12px;margin:16px 0 0;max-width:62ch}}
kbd{{font:inherit;border:1px solid var(--frame);border-radius:3px;padding:0 4px}}
""" + "".join(f"html:has(#pc{v}:checked){{--pal:{v}}}" for v in range(K))

cells = "".join('<div class=c><span class=rd>'
                + "".join(f'<i style="content:url(/c/{k}/r/{v}.png)"></i>' for v in range(K))
                + '</span><div class=v><span class=rt>'
                + "".join(f'<i style="content:url(/c/{k}/r/2/{v}.png)"></i>' for v in range(K))
                + f'</span><div class=w><b class=px></b><object class=x type=text/html data="/c/{k}/x" title="cell {k}"></object>'
                + "".join(f'<object class=f{v} type=text/html data="/c/{k}/p/{v}" title="cell {k}"></object>' for v in range(K))
                + '</div></div></div>'
                for k in range(N))
pal = "".join(f'<input type=radio name=pal id=pc{v} autocomplete=off{" checked" if v == 1 else ""}>'
              f'<label for=pc{v} style="background:var(--p{v})" title="colour {v}"></label>' for v in range(K))
html = f"""<!doctype html>
<html lang=en>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Dictionary Paint</title>
<!-- No JavaScript. Each cell is one compression dictionary Chrome keeps for this site. See build.py. -->
<style>{page_css}</style>
<main>
<header><h1>Dictionary Paint</h1><span>{W}×{H} · 16 colours · no JS</span></header>
<div class=stage><div class=sig><div class=gd><div class=sig><div class=gd><div class=grid>{cells}</div></div><i class=s2 style="content:url(/s.png?2)"></i></div></div><i style="content:url(/s.png)"></i></div></div>
<div class=pal>{pal}</div>
<p>Pick a colour and paint. Everything is saved as you go and survives reloads and restarts.
The browser's Back button is undo, Forward is redo.</p>
</main>
</html>
"""
open(f"{OUT}/index.html", "w").write(html)
print(f"{W}x{H}: index.html {len(html)/1e3:.0f} KB, cell.html {len(cell)} B, data files {2*K}, pages {K+1}")
