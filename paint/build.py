#!/usr/bin/env python3
"""Dictionary Paint: click or drag to paint. No JavaScript.

Every cell owns the namespace /c/<k>/. _redirects serves all cells from shared files, and relative URLs inside a
cell's writer document resolve under /c/<k>/, so one file serves 480 cells.

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
  INPUT  the page: a cell under the pointer while the grid is :active takes the palette colour, --L, held by
         a transition with a 1e7 s delay. The cell shows it at once. (Cells can't be documents: a press is
         captured by the frame it starts in, so a drag never reaches the next one.) Touch screens get a
         layer of scroller handles, one per cell (css-physics); the dragged one names an anchor whose size
         encodes (cell, drag), which a container around the canvas reads with anchor-size(). A follower gives
         "finger down"; a handle returns to rest once still, a re-snap Chrome defers to the gesture's end.
  STROKE the stroke's cell as numbers on .grid (mouse: :has(:hover) per row and column; touch: the anchor), the
         last frame's in .gw (a 1 ms transition); every cell on the line between them paints, so a stroke
         faster than a cell per frame leaves no gaps.
  WRITE  three writer <object>s per cell, /c/k/w, hidden (no frame, nothing loaded) until the cell is first
         painted. A shown writer is (CELL + L) x (CELL + slot) px and loads mask-image d/<L>.png?<slot>,
         which _headers makes the dictionary for /c/k/r/*. A document fetches each URL once, so each change
         needs a new slot: --W follows --L SETTLE ms late, a per-cell clock runs while they differ, and the
         slot is the clock in TICKs. After SLOTS slots the next writer, a fresh document, takes over.
  SAVING the page's spinner sits under the writer, whose square is masked by its write: a mask still loading
         paints nothing, so the spinner shows until the write has loaded.
  BLANK  a cell never written shows the grid's checkerboard, not colour 0.
  UNDO   none: Back/Forward undo was each cell document's history (docs/HISTORY.md, 8).

URLS   all page URLs are extensionless (/c/k/w): Cloudflare 308-redirects *.html to the extensionless path, and a
         redirect inside a rewrite would leave the cell's /c/<k>/ namespace. Files on disk keep .html.

Writes site/: w.html, 16 d/*.png, 16 r/*.png, s.png, index.html, _headers, _redirects.
usage: python3 build.py [W] [H]      (pip install zstandard)
"""
import os, sys, struct, zlib, hashlib
import zstandard
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared", "py"))
import csslabel as lbl     # section and group comments in the output (../shared/README.md#labels-in-generated-css)

W = int(sys.argv[1]) if len(sys.argv) > 1 else 24
H = int(sys.argv[2]) if len(sys.argv) > 2 else 20
K, CELL = 16, 22
SLOTS, WRITERS = 64, 3        # write URLs per colour in one writer document; writer documents per cell
TICK, SETTLE = 40, 50         # ms per slot; a change runs its cell's clock at least SETTLE ms (> TICK: a new slot)
HD = 3000                     # a touch handle scrolls up to this far from its rest offset
PUB, STILL = 8192, 100        # px per cell index in the publisher's width; ms still before a handle returns to rest
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


for sub in ("d", "r"):
    os.makedirs(f"{OUT}/{sub}", exist_ok=True)
for v in range(K):
    if not os.path.exists(f"{OUT}/d/{v}.png"):           # keep dictionaries stable across rebuilds
        open(f"{OUT}/d/{v}.png", "wb").write(png(1, 1, b"colour %d " % v + os.urandom(8).hex().encode()))
    open(f"{OUT}/r/{v}.png", "wb").write(dcz(open(f"{OUT}/d/{v}.png", "rb").read(), png(v + 1, 1)))
SENT = 8                                                  # the sentinel's width; it narrows the `done` container
open(f"{OUT}/s.png", "wb").write(png(SENT, 1))

open(f"{OUT}/_redirects", "w").write("""/c/:k/r/2/:v /r/:v 200
/c/:k/w /w 200
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
/c/:k/w
  Cache-Control: no-cache
/s.png
  Cache-Control: no-store
/
  Cache-Control: no-cache
""")

lookup = lambda var: "if(" + "".join(f"style({var}:{v}):var(--p{v});" for v in range(K)) + "else:transparent)"

# ------------------------------------------------------------------ the writer
# w.html, at /c/<k>/w: writes cell k. The page sizes it (CELL + L) x (CELL + slot) px, so its viewport says what to
# write; relative URLs resolve under /c/<k>/, so this one file serves every cell. Each (colour, slot) URL is fetched
# once per document, and the page moves to a fresh slot on every change (the clock below), so a cell can go back to
# a colour it held before. The square shows only once its mask, the write, has loaded: until then the page's
# spinner, under this document, shows through.
urls = "if(" + "".join(f"style(--L:{v}):if(" + "".join(f"style(--s:{i}):url(d/{v}.png?{i});" for i in range(SLOTS))
                       + "else:none);" for v in range(K)) + "else:none)"
writer = f"""<!doctype html><meta charset=utf-8><title>cell writer</title><style>
{lbl.header("paint/build.py", "paint/docs/ARCHITECTURE.md")}
{lbl.section("Writer: colour from the viewport width, slot from its height")}
@property --L{{syntax:'<integer>';inherits:true;initial-value:-1}}
@property --s{{syntax:'<integer>';inherits:true;initial-value:-1}}
:root{{""" + "".join(f"--p{v}:{c};" for v, c in enumerate(PALETTE)) + f"""--L:calc(100vw / 1px - {CELL});--s:calc(100vh / 1px - {CELL})}}
html,body{{margin:0;overflow:hidden;background:transparent}}
b{{position:fixed;left:0;top:0;width:{CELL}px;height:{CELL}px;background:{lookup('--L')};mask-image:{urls}}}
</style><b></b>
"""
lbl.check(writer, "w.html")
open(f"{OUT}/w.html", "w").write(writer)
for old in ["cell.html"] + [f"p/{v}.html" for v in range(K)]:       # the cell documents of the click-only canvas
    if os.path.exists(f"{OUT}/{old}"):
        os.remove(f"{OUT}/{old}")
if os.path.isdir(f"{OUT}/p"):
    os.rmdir(f"{OUT}/p")

# ------------------------------------------------------------------ the page
page_css = (lbl.header("paint/build.py", "paint/docs/ARCHITECTURE.md") + "\n" +
            lbl.section("Palette, registered properties and page layout") + "\n:root{" +
            "".join(f"--p{v}:{c};" for v, c in enumerate(PALETTE)) + "}") + f"""
@property --pal{{syntax:'<integer>';inherits:true;initial-value:1}}
@property --s{{syntax:'<number>';inherits:true;initial-value:1}}
@property --bv{{syntax:'<integer>';inherits:false;initial-value:-1}}
@property --go{{syntax:'<integer>';inherits:true;initial-value:0}}
@property --L{{syntax:'<integer>';inherits:true;initial-value:-1}}
@property --W{{syntax:'<integer>';inherits:true;initial-value:-1}}
@property --d{{syntax:'<integer>';inherits:true;initial-value:0}}
@property --C{{syntax:'<number>';inherits:true;initial-value:0}}
@property --g{{syntax:'<integer>';inherits:true;initial-value:0}}
@property --ws{{syntax:'<integer>';inherits:true;initial-value:0}}
@property --wj{{syntax:'<integer>';inherits:true;initial-value:0}}
@property --wp{{syntax:'<integer>';inherits:true;initial-value:0}}
""" + "".join(f"@property --{n}{{syntax:'<integer>';inherits:false;initial-value:{iv}}}\n" for n, iv in
              [("tdx", 0), ("tdy", 0), ("rw", 0), ("fox", 0), ("foy", 0), ("tgi", 0), ("held", 0), ("fr", 0),
               ("fc", 0), ("dv", 0), ("hr", 0), ("hc", 0), ("hv", 0), ("qr", 0), ("qc", 0), ("qv", 0), ("or", 0), ("oc", 0), ("pr", 0), ("pc", 0), ("pv", 0), ("kr", 0), ("kc", 0), ("on", 0)]) + \
    "".join(f"@property --{n}{{syntax:'<number>';inherits:false;initial-value:0}}\n" for n in
              ["sx", "sy", "dx", "dy", "rx", "ry", "inx", "iny", "maj"]) + \
    "".join(f"@property --{n}{{syntax:'<number>';inherits:true;initial-value:0}}\n" for n in
              ["tx", "ty", "txd", "tyd", "tgx", "tgy", "tgl", "still"]) + f""":root{{--bg:#ebe5d8;--ink:#1d1b1a;--mute:#7c766c;--frame:#c9c1b1;--ck1:#ddd6c8;--ck2:#e9e3d6;--gw:{W * CELL}px}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141312;--ink:#ece6da;--mute:#8d867a;--frame:#3a3732;--ck1:#262421;--ck2:#1d1b19}}}}
html,body{{margin:0;background:var(--bg);color:var(--ink)}}
body{{font:13px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,monospace;min-height:100vh;display:grid;
  place-items:center;padding:28px 16px;box-sizing:border-box;overflow-x:hidden}}
main{{--s:min(1,calc((100vw - 32px) / var(--gw)));width:calc(var(--gw) * var(--s))}}
header{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 14px}}
h1{{font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;margin:0}}
header span{{color:var(--mute);font-size:12px;text-align:right}}
.stage{{height:calc({H * CELL}px * var(--s))}}
{lbl.section("RETRY: the sentinels", "each .gd narrows by SENT px once its sentinel loads")}
/* /s.png follows the first pass of probes; /s.png?2 is requested only then, so it also queues behind the probes
   Chrome re-sent after a GOAWAY */
.sig{{display:flex}}
.stage>.sig{{width:{W * CELL + SENT}px;transform-origin:0 0;scale:var(--s)}}
.gd{{flex:1 1 0;min-width:0;container:s1/inline-size}}
.gd .gd{{container-name:s2}}
.sig>i{{display:block;flex:none;opacity:0}}
.sig>i.s2{{display:none}}
@container s1 (width<{W * CELL + SENT // 2}px){{.sig>i.s2{{display:block}}}}
{lbl.section("The canvas: one .c per cell")}
/* a cell never written shows the checkerboard behind it, so it can't be mistaken for colour 0 */
.grid{{display:grid;grid-template-columns:repeat({W},{CELL}px);width:var(--gw);
  background:repeating-conic-gradient(var(--ck1) 0 25%,var(--ck2) 0 50%) 0 0/{CELL}px {CELL}px;
  cursor:crosshair;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}}
.c{{position:relative;width:{CELL}px;height:{CELL}px;overflow:hidden;anchor-scope:--rd,--rt}}
.c *{{pointer-events:none}}
{lbl.section("INPUT: press and drag", "a cell under the pointer while the grid is pressed takes the palette colour")}
/* --L, the colour painted in this page (-1: none), holds for 1e7 s after the pointer leaves; the cell
   shows it at once, before the write */
.c{{--L:-1;transition:--L 0s 1e7s}}
.grid:active .c:hover{{--L:var(--pal);transition-delay:0s}}
{lbl.group("Strokes: the cells between two frames' positions", "a fast stroke crosses several cells per frame; every cell on the segment from the last frame's position paints")}
/* the stroke's cell (--qr, --qc; --qv: 1 while drawing) and where a stroke's first segment starts (--or, --oc: the
   cell itself for the mouse, the cell the finger came down on for touch, whose first update comes past the slop) are
   set on .grid, by the mouse rules below or the touch sums; .gw holds last frame's (--pr, --pc, --pv: a transition 1 ms late), and each cell paints if it is on the line
   between them: one cell per step along the major axis, the nearest (as Bresenham). All non-inherited: .c takes them
   with inherit, so nothing below it restyles. */
""" + "".join(f".wrap:active:has(.y{r}:hover){{--hr:{r}}}" for r in range(H)) + "".join(
    f".wrap:active:has(.x{c}:hover){{--hc:{c}}}" for c in range(W)) + f"""
.wrap:active:has(.c:hover,.hd:hover){{--hv:1}}
.R,.Rv{{--hr:inherit;--hc:inherit;--hv:inherit}}
.grid{{--hr:inherit;--hc:inherit;--hv:inherit;--qr:var(--hr);--qc:var(--hc);--qv:var(--hv);--or:var(--hr);--oc:var(--hc)}}
.gw{{display:contents;--qr:inherit;--qc:inherit;--qv:inherit;--or:inherit;--oc:inherit;--pr:var(--qr);--pc:var(--qc);--pv:var(--qv);
  transition:--pr 0s 1ms,--pc 0s 1ms,--pv 0s 1ms}}
.c{{--qr:inherit;--qc:inherit;--qv:inherit;--or:inherit;--oc:inherit;--pr:inherit;--pc:inherit;--pv:inherit;
  --sx:if(style(--pv:1):var(--pc);else:var(--oc));--sy:if(style(--pv:1):var(--pr);else:var(--or));
  --dx:calc(var(--qc) - var(--sx));--dy:calc(var(--qr) - var(--sy));
  --maj:sign(max(0,abs(var(--dx)) - abs(var(--dy)) + 0.5));
  --inx:calc(1 - sign(max(0,(var(--kc) - var(--sx)) * (var(--kc) - var(--qc)))));
  --iny:calc(1 - sign(max(0,(var(--kr) - var(--sy)) * (var(--kr) - var(--qr)))));
  --rx:round(var(--sy) + (var(--kc) - var(--sx)) * var(--dy) / (var(--dx) + 1 - abs(sign(var(--dx)))));
  --ry:round(var(--sx) + (var(--kr) - var(--sy)) * var(--dx) / (var(--dy) + 1 - abs(sign(var(--dy)))));
  --on:calc(var(--qv) * (var(--maj) * var(--inx) * (1 - min(1,abs(var(--rx) - var(--kr)))) +
    (1 - var(--maj)) * var(--iny) * (1 - min(1,abs(var(--ry) - var(--kc))))))}}
.c{{--L:if(style(--on:1):var(--pal);else:-1);transition-delay:if(style(--on:1):0s;else:1e7s)}}
.c:hover::after{{content:"";position:absolute;inset:0;z-index:3;pointer-events:none;
  box-shadow:inset 0 0 0 2px {lookup('--pal')},inset 0 0 0 3px #fff8}}
{lbl.group("Touch: handles", "a finger drag gets no :hover, but it scrolls the handle it came down on (css-physics ARCHITECTURE.md, Touch)")}
/* a layer of handles over the canvas, one per cell: a scroller resting mid-content. Each reads its own offset (an
   anonymous scroll timeline, --tx/--ty: the drag) and, while off rest, names its publisher --drag: a box
   (cell index + 1) * {PUB} + {HD} + tx px wide and {HD} + ty px tall. .R, around the canvas, is sized by
   anchor-size(--drag) and .Rv decodes it, so the drag reaches every cell without a timeline-scope (960 animations
   on scoped timelines made every layout cost ~90 ms). A handle snaps to an area around its offset (u: nothing moves
   when the finger lifts) until its offset has been still for {STILL} ms, then to rest (i); while a gesture is active
   Chrome defers that re-snap to the gesture's end. */
.hds,.fo{{display:none}}
@keyframes htx{{from{{--tx:{HD}}}to{{--tx:{-HD}}}}}
@keyframes hty{{from{{--ty:{HD}}}to{{--ty:{-HD}}}}}
@keyframes hgx{{0%,49.99%{{--tgx:1;animation-timing-function:step-start}}50.01%{{--tgx:0;animation-timing-function:step-start}}100%{{--tgx:1}}}}
@keyframes hgy{{0%,49.99%{{--tgy:1;animation-timing-function:step-start}}50.01%{{--tgy:0;animation-timing-function:step-start}}100%{{--tgy:1}}}}
@keyframes hdl{{from{{left:-40px}}to{{left:{2 * HD - 40}px}}}}
@keyframes hdt{{from{{top:-40px}}to{{top:{2 * HD - 40}px}}}}
.fo{{position:absolute;left:0;top:0;width:10px;height:10px;overflow:hidden;scroll-snap-type:both mandatory;
  visibility:hidden;pointer-events:none;scroll-timeline:--Fx x,--Fy y}}
.fo,.fo>i,.fo>i>b{{--tdx:inherit;--tdy:inherit}}
.fo>i{{display:block;position:relative;width:{2 * HD + 10}px;height:{2 * HD + 10}px}}
.fo>i>b{{position:absolute;width:10px;height:10px;scroll-snap-align:start;
  left:calc(({HD} - var(--tdx)) * 1px);top:calc(({HD} - var(--tdy)) * 1px)}}
@keyframes hfx{{from{{--fox:{HD}}}to{{--fox:{-HD}}}}}
@keyframes hfy{{from{{--foy:{HD}}}to{{--foy:{-HD}}}}}
.wrap{{position:relative;width:var(--gw);height:{H * CELL}px;overflow:clip;outline:1px solid var(--frame);
  box-shadow:0 12px 30px -18px rgba(0,0,0,.35)}}
.R{{position:absolute;left:0;top:0;width:anchor-size(--drag width,{HD}px);height:anchor-size(--drag height,{HD}px);
  container-type:size}}
.Rv{{width:var(--gw);--rw:calc(100cqw / 1px);--tgi:round(down,var(--rw) / {PUB});--tdx:calc(var(--rw) - var(--tgi) * {PUB} - {HD});
  --tdy:calc(100cqh / 1px - {HD})}}
@media (pointer:coarse){{
  .c:hover::after{{display:none}}
  .fo{{display:block}}
  .hds{{display:grid;grid-template-columns:repeat({W},{CELL}px);position:absolute;left:0;top:0;z-index:5}}
  .hd{{display:block;width:{CELL}px;height:{CELL}px;overflow:scroll;scrollbar-width:none;scroll-snap-type:both mandatory;
    overscroll-behavior:contain;scroll-axis-lock:none;touch-action:pan-x pan-y;-webkit-tap-highlight-color:transparent}}
  .hd::-webkit-scrollbar{{display:none}}
  .hd>b{{display:block;position:relative;width:{2 * HD + CELL}px;height:{2 * HD + CELL}px;
    animation:htx linear both,hty linear both,hgx linear both,hgy linear both;
    animation-timeline:scroll(nearest x),scroll(nearest y),scroll(nearest x),scroll(nearest y)}}
  .hd em{{display:block;--tgl:max(var(--tgx),var(--tgy));--txd:var(--tx);--tyd:var(--ty);
    transition:--txd 0s {STILL}ms,--tyd 0s {STILL}ms}}
  .hd strong{{display:block;--still:calc(1 - sign(abs(var(--tx) - var(--txd)) + abs(var(--ty) - var(--tyd))))}}
  .hd i{{position:absolute;left:{HD}px;top:{HD}px;width:{CELL}px;height:{CELL}px;
    scroll-snap-align:if(style(--still:1):start;else:none)}}
  .hd u{{position:absolute;left:0;top:0;width:{CELL + 80}px;height:{CELL + 80}px;
    animation:hdl linear both,hdt linear both;animation-timeline:scroll(nearest x),scroll(nearest y);
    scroll-snap-align:if(style(--still:1):none;else:start)}}
  .hd p{{position:absolute;left:0;top:0;width:0;height:0;margin:0;overflow:clip}}
  .hd s{{position:absolute;left:0;top:0;width:calc(var(--kk) * {PUB}px + {HD}px + var(--tx) * 1px);
    height:calc({HD}px + var(--ty) * 1px);anchor-name:if(style(--tgl:1):--drag;else:none)}}
  /* a drag needs a handle off rest and the finger down; the cell it came down on starts its first segment */
  .grid{{--tdx:inherit;--tdy:inherit;--tgi:inherit;timeline-scope:--Fx,--Fy;
    animation:hfx linear both,hfy linear both;animation-duration:auto;animation-timeline:--Fx,--Fy;
    --held:sign(max(0,abs(var(--tdx) - var(--fox)) + abs(var(--tdy) - var(--foy)) - 0.01));
    --fr:calc(round(down,(var(--tgi) - 1) / {W}) + round(var(--tdy) / {CELL}));
    --fc:calc(mod(var(--tgi) - 1,{W}) + round(var(--tdx) / {CELL}));
    --dv:calc(var(--held) * (1 - sign(max(0,0 - var(--fr),var(--fr) - {H - 1},0 - var(--fc),var(--fc) - {W - 1},1 - var(--tgi)))));
    --qr:if(style(--dv:1):var(--fr);else:var(--hr));--qc:if(style(--dv:1):var(--fc);else:var(--hc));
    --qv:max(var(--dv),var(--hv));
    --or:if(style(--dv:1):round(down,(var(--tgi) - 1) / {W});else:var(--hr));
    --oc:if(style(--dv:1):mod(var(--tgi) - 1,{W});else:var(--hc))}}
}}
{lbl.section("READ: the probe rows", "the probe row is (stored value + 1) px wide; 0 = never written")}
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
/* the colour painted in this page if any, else the colour read (transparent if never written) */
.px{{position:absolute;left:0;top:0;width:{CELL}px;height:{CELL}px;--bv:calc(100cqw / 1px - 1);
  background:if(style(--L:-1):{lookup('--bv')};else:{lookup('--L')})}}
{lbl.section("WRITE: a clock per cell and the writer documents", "every change of --L runs the clock for SETTLE ms, so each write gets a fresh slot")}
/* --W follows --L SETTLE ms late; the clock runs while they differ. (The test reads --d on a grandchild:
   on the element whose transition moved, animation-play-state isn't recomputed when it ends.) */
.k{{--W:var(--L);transition:--W 0s {SETTLE}ms}}
.q{{--d:calc(var(--L) - var(--W))}}
.t{{animation:ck 1000000s linear infinite;animation-play-state:if(style(--d:0):paused;else:running)}}
@keyframes ck{{from{{--C:0}}to{{--C:1000000}}}}
/* slot --ws within writer --wj; the writer reads (colour, slot) from its size. A hidden <object> never
   loads, so a cell gets its first writer when first painted, and the next one when the slots run out */
.u{{display:if(style(--L:-1):none;else:block);--g:round(down,calc(var(--C) * 1000 / {TICK}));
  --ws:mod(var(--g),{SLOTS});--wj:round(down,calc(var(--g) / {SLOTS}));--wp:mod(var(--g),2)}}
.u object{{position:absolute;left:0;top:0;display:none;border:0;color-scheme:normal;
  width:calc({CELL}px + var(--L) * 1px);height:calc({CELL}px + var(--ws) * 1px)}}
""" + "".join(f".u object.w{j}{{display:if(style(--wj:{j}):block;else:none)}}" for j in range(WRITERS)) + f"""
{lbl.group("Saving: a spinner under the writer, covered once its write has loaded", "it restarts on each slot (--wp) and stops after 28 s")}
.sp{{position:absolute;left:5px;top:5px;width:12px;height:12px;border-radius:50%;mix-blend-mode:difference;
  background:conic-gradient(#fff0,#fff);mask:radial-gradient(closest-side,#0000 55%,#000 60%);
  animation:if(style(--wp:0):spa;else:spb) .7s linear 40}}
@keyframes spa{{to{{rotate:1turn}}}}
@keyframes spb{{to{{rotate:1turn}}}}
{lbl.section("Palette picker and notes")}
.pal{{display:grid;grid-template-columns:repeat(16,1fr);gap:4px;margin:14px 0 0}}
.pal input{{position:absolute;opacity:0;pointer-events:none}}
.pal label{{aspect-ratio:1;border-radius:3px;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(0,0,0,.12)}}
.pal input:checked+label{{box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--ink)}}
.pal input:focus-visible+label{{outline:2px solid var(--ink);outline-offset:4px}}
p{{color:var(--mute);font-size:12px;margin:16px 0 0;max-width:62ch}}
kbd{{font:inherit;border:1px solid var(--frame);border-radius:3px;padding:0 4px}}
""" + "".join(f"html:has(#pc{v}:checked){{--pal:{v}}}" for v in range(K))

cells = "".join(f'<div class="c y{k // W} x{k % W}" style="--kr:{k // W};--kc:{k % W}"><span class=rd>'
                + "".join(f'<i style="content:url(/c/{k}/r/{v}.png)"></i>' for v in range(K))
                + '</span><div class=v><span class=rt>'
                + "".join(f'<i style="content:url(/c/{k}/r/2/{v}.png)"></i>' for v in range(K))
                + '</span><div class=w><b class=px></b></div></div><div class=k><div class=q><div class=t><div class=u><i class=sp></i>'
                + "".join(f'<object class=w{j} type=text/html data="/c/{k}/w" title="cell {k}"></object>' for j in range(WRITERS))
                + '</div></div></div></div></div>'
                for k in range(N))
hds = "".join(f'<i class="hd y{k // W} x{k % W}" style="--kk:{k + 1}"><b><em><strong><i></i><u></u><p><s></s></p></strong></em></b></i>'
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
<div class=stage><div class=sig><div class=gd><div class=sig><div class=gd><div class=wrap><div class=hds>{hds}</div><div class=R><div class=Rv><div class=grid><div class=fo><i><b></b></i></div><div class=gw>{cells}</div></div></div></div></div></div><i class=s2 style="content:url(/s.png?2)"></i></div></div><i style="content:url(/s.png)"></i></div></div>
<div class=pal>{pal}</div>
<p>Pick a colour, then click or drag to paint. A cell shows its colour at once and spins until the
browser has stored it; the picture survives reloads and restarts. Unpainted cells are checkered.</p>
</main>
</html>
"""
lbl.check(html, "index.html")
open(f"{OUT}/index.html", "w").write(html)
print(f"{W}x{H}: index.html {len(html)/1e3:.0f} KB, w.html {len(writer)/1e3:.0f} KB, data files {2*K}")
