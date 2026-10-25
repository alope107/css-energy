#!/usr/bin/env python3
"""Art styles: other looks for the same scene, picked at runtime with the "style" radios (no script).

build3d.py puts inputs() (the radios) first in #app, labels() in the controls row, svg() (the styles' SVG filters)
at the end of the body and css(lams) in the page's stylesheet; lams[fi] is box face fi's lighting term from gen3d.py
(a calc() of the body's rotation matrix, -1 to 1). "original" is the default and has no rules: its look is ui3d.css's
and gen3d.py's.

Cost: the original page must cost what it did without the styles (BENCHMARKS.md "Art styles"). Two rules keep it so.
- Static rules (page, arena, tray, discs, rings) are scoped to #app:has(> #a-NAME:checked): the radios are #app's
  children, and `>` keeps the :has() to them. Without it, :has() searches #app's whole subtree (the engine and 5,000
  pointer cells), once per style pass for each style, as soon as anything restyled that pass tries one of its rules:
  +13-18% per pass at 16 bodies.
- What moving bodies restyle every frame (.bx, the faces .f0-.f5, .sp, .sh, .bw) is styled inside
  @container art-NAME { ... }, a name the style's static rule puts on .cam; for the styles not picked, each such rule
  costs one failed container lookup. Each style has one rule per such element: `k` and `vars` (on .bx, per face),
  `face` (one rule per face index), `sp`, `sh` and `frame`. Their declarations use var(), so they're parsed again on
  every restyle: keep long literals (data: URIs) out of them; textures go on static elements (.arena::after
  overlays), effects in SVG filters on .view or .arena, which the compositor runs. Anything animated animates
  transform, rotate or filter, which the compositor runs without a style pass.

In `css`, a selector that starts with & is the root itself, one that starts with body is under the root, and any
other is under #app. In `k` and `vars`, {lam} is the face's lighting term and {l} = max(0, lam); `k` gives the face
colour --k<fi> (declared on .bx, inherited by the face), `vars` more per-face values (--<name><fi>, unregistered,
so faces inherit them). In `face`, {k}, {<var name>} and {fi} are the face's. `webkit`: flat rules scoped as `css`
and applied in WebKit only (for what Safari draws differently: pencil's filter).
"""
import math
import re
import urllib.parse


def step(x, e, w=40):
    """0 below e, 1 above it, a ramp 1/w wide: a hard band edge without round() (about 5 µs)."""
    return f'clamp(0, ({x} - {e}) * {w}, 1)'


def svg_uri(svg):
    return 'url("data:image/svg+xml,' + urllib.parse.quote(' '.join(svg.split()), safe="=/:;,'()") + '")'


def svg(body, w=100, h=100, defs=''):
    return svg_uri(f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
                   f"{'<defs>' + defs + '</defs>' if defs else ''}{body}</svg>")


def noise(base, matrix, size=240, kind='fractalNoise', octaves=3, seed=1):
    """A tile of SVG turbulence as a CSS image: colour matrix `matrix` (20 numbers) applied to the noise."""
    return svg_uri(f"""<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}'>
      <filter id='n' x='0' y='0' width='100%' height='100%'><feTurbulence type='{kind}' baseFrequency='{base}'
      numOctaves='{octaves}' seed='{seed}' stitchTiles='stitch'/><feColorMatrix values='{matrix}'/></filter>
      <rect width='100%' height='100%' filter='url(#n)'/></svg>""")


def ring(n, r, cx=50, cy=50, rot=0):
    """n points on a circle of radius r (degrees from 12 o'clock, clockwise)."""
    return [(round(cx + r * math.sin(math.radians(rot + 360 * k / n)), 2), round(cy - r * math.cos(math.radians(rot + 360 * k / n)), 2))
            for k in range(n)]


def star(n, ro, ri, cx=50, cy=50, rot=0):
    """An n-pointed star polygon's points attribute."""
    o, i = ring(n, ro, cx, cy, rot), ring(n, ri, cx, cy, rot + 180 / n)
    return ' '.join(f'{x},{y}' for a, b in zip(o, i) for x, y in (a, b))


# overlays laid over the whole arena (static: rasterized once, blended by the compositor)
GRAIN = noise('.9', '0 0 0 0 .16  0 0 0 0 .15  0 0 0 0 .13  -1 0 0 0 .52', octaves=3, seed=4)
FIBRE = noise('.07', '0 0 0 0 .45  0 0 0 0 .35  0 0 0 0 .22  0 0 -.45 0 .26', size=300, octaves=4, seed=11)


def overlay(img, blend, size='240px', extra=''):
    return (f'.arena{{isolation:isolate}}'
            f'.arena::after{{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;'
            f'background:{img} 0 0/{size};mix-blend-mode:{blend};{extra}}}')


def ui(bg, panel, ink, dim, line, acc, on_acc, scheme, font=None):
    """The page around the arena: ui3d.css's colour variables and the font."""
    s = (f'&{{--bg:{bg};--panel:{panel};--ink:{ink};--dim:{dim};--line:{line};--acc:{acc};--on-acc:{on_acc};'
         f'color-scheme:{scheme}}}')
    return s + (f'body{{font-family:{font}}}' if font else '')


SERIF = "'Palatino Linotype',Palatino,'Book Antiqua',Georgia,serif"
STYLES = {}


def style(name, **kw):
    STYLES[name] = kw


# ---- cel: toon shading in three hard bands, chunky ink outlines, a shine streak on lit faces ----------------------
INK = '#1b1724'
style('cel',
      k=f'color-mix(in oklab,var(--cs) calc((0.5 + 0.28 * {step("{lam}", 0.1)} + 0.22 * {step("{lam}", 0.62)}) * 100%),#2a1b4a)',
      vars=dict(s=f'calc(0.85 * {step("{lam}", 0.62)})'),
      # (the inset line and the outline beyond the face's edge make one stroke over each edge: 7 px)
      face=f'background:linear-gradient(135deg,transparent 16%,rgb(255 255 255/{{s}}) 16% 24%,transparent 24% 29%,'
           f'rgb(255 255 255/{{s}}) 29% 32%,transparent 32%),{{k}};box-shadow:inset 0 0 0 4.5px {INK};outline:2.5px solid {INK}',
      sp=f'color:color-mix(in oklab,{INK},var(--acc) calc(var(--sel) * 100%))',
      sh=f'background:radial-gradient(closest-side,rgb(27 23 36/.5) 0 86%,transparent 90%)',
      css=ui('#fff4dc', '#fffdf7', INK, '#5b5566', INK, '#ff4d6d', '#fff', 'light',
             "'Trebuchet MS','Avenir Next',Verdana,sans-serif") + f"""
header h1{{font-weight:900;letter-spacing:0}}
.grp label,.grp button{{border-width:3px;border-radius:9px}}
.arena{{border:5px solid {INK};border-radius:14px;
  background:radial-gradient(circle,rgb(27 23 36/.09) 1.3px,transparent 1.7px) 0 0/9px 9px,linear-gradient(#78cdfc,#e3f6ff 72%)}}
.floor{{background:linear-gradient(rgb(27 23 36/.25) 4px,transparent 4px) 0 0/80px 80px,
  linear-gradient(90deg,rgb(27 23 36/.25) 4px,transparent 4px) 0 0/80px 80px,#ffd166;border:7px solid {INK}}}
.ceil{{border:3px dashed rgb(27 23 36/.3)}}
.post{{width:6px;margin-left:-3px;background:{INK}}}
.rail{{background:rgb(239 71 111/.5);border-top:6px solid {INK}}}
.disc{{border:5.5px solid {INK};background:radial-gradient(circle at 34% 28%,#fff 0 9%,transparent 10%),
  radial-gradient(circle at 40% 36%,var(--c) 0 54%,color-mix(in oklab,var(--c) 58%,#2a1b4a) 55%)}}
.sp .eq{{border-width:4px}}""")

# ---- pencil: graphite hatching on paper, denser and crossed as a face turns from the light; wobbly lines ---------
GRAPH = 'rgb(38 38 44'
style('pencil',
      k='color-mix(in oklab,var(--cs) 20%,#f6f3ec)',
      vars=dict(a=f'clamp(0, (0.92 - {{lam}}) * 0.85, 0.8)', x=f'clamp(0, (0.3 - {{lam}}) * 1.3, 0.75)'),
      face=f'background:repeating-linear-gradient(-45deg,{GRAPH}/{{x}}) 0 .8px,transparent .8px 4.2px),'
           f'repeating-linear-gradient(45deg,{GRAPH}/{{a}}) 0 .9px,transparent .9px 3.6px),{{k}};'
           f'box-shadow:inset 0 0 0 1.4px rgb(30 30 34/.85)',
      sp='color:color-mix(in oklab,rgb(35 35 40/.6),var(--acc) calc(var(--sel) * 100%))',
      sh=f'background:repeating-linear-gradient(45deg,{GRAPH}/.6) 0 1px,transparent 1px 3.4px);'
         '-webkit-mask:radial-gradient(closest-side,#000 35%,transparent);mask:radial-gradient(closest-side,#000 35%,transparent)',
      css=ui('#f3f0e8', '#fbf9f4', '#2d2d30', '#6d6a66', '#b9b4aa', '#2d2d30', '#f3f0e8', 'light') + f"""
header h1{{font-family:'Bradley Hand','Segoe Print','Chalkboard SE','Comic Sans MS',cursive}}
.arena{{border:1.5px solid #3a3a3d;border-radius:3px;background:#f6f3ec}}
{overlay(GRAIN, 'multiply')}
.view{{filter:url(#art-pencil)}}
.floor{{background:linear-gradient({GRAPH}/.16) 1px,transparent 1px) 0 0/40px 40px,
  linear-gradient(90deg,{GRAPH}/.16) 1px,transparent 1px) 0 0/40px 40px;border:1.5px solid {GRAPH}/.8)}}
.ceil{{border:1px dashed {GRAPH}/.35)}}
.post{{background:{GRAPH}/.45)}}
.rail{{background:repeating-linear-gradient(45deg,{GRAPH}/.16) 0 .8px,transparent .8px 5px);border-top:1.5px solid {GRAPH}/.7)}}
.disc{{border:1.4px solid rgb(30 30 34/.85);
  background:radial-gradient(circle at 36% 30%,transparent 0 20%,{GRAPH}/.22) 62%,{GRAPH}/.5)),color-mix(in oklab,var(--c) 20%,#f6f3ec)}}
.disc::before,.disc::after{{content:"";position:absolute;inset:0;border-radius:50%}}
.disc::before{{background:repeating-linear-gradient(45deg,{GRAPH}/.75) 0 .9px,transparent .9px 3.6px);
  -webkit-mask:radial-gradient(circle at 34% 28%,transparent 36%,#000 82%);mask:radial-gradient(circle at 34% 28%,transparent 36%,#000 82%)}}
.disc::after{{background:repeating-linear-gradient(-45deg,{GRAPH}/.65) 0 .8px,transparent .8px 4.2px);
  -webkit-mask:radial-gradient(circle at 30% 24%,transparent 62%,#000 96%);mask:radial-gradient(circle at 30% 24%,transparent 62%,#000 96%)}}
.sp .eq{{border-width:1.2px}}""",
      # (WebKit draws the scene's planes on their own compositing layers, which a filter on .view never reaches: there
      # the scenery wobbles plane by plane. Not the bodies: a moving face repaints, and its filter with it, every frame:
      # 62 -> 30 fps at 16 bodies in Safari 26.6; the scenery is painted once, 62 fps)
      webkit=".view{filter:none}.floor,.ceil,.post,.rail{filter:url(#art-pencil)}",
      svg="""<filter id="art-pencil" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" seed="7"/>
  <feDisplacementMap in="SourceGraphic" scale="3.5" xChannelSelector="R" yChannelSelector="G"/></filter>""")

# ---- baroque: a gilded frame, velvet drapes, chiaroscuro jewel tones under gilt scrollwork, barley-twist columns,
# an inlaid marble floor, damask walls --------------------------------------------------------------------------------
GILT = 'color-mix(in oklab,#f6dc8a calc((0.18 + 0.82 * {g}) * 100%),#3d2808)'
# the face ornament, masks filled with the face's lit gilt: a rosette and a scroll in each corner
ROSETTE = svg("<circle cx='50' cy='50' r='9'/><circle cx='50' cy='50' r='15' fill='none' stroke='#000' stroke-width='4'/>"
              + ''.join(f"<ellipse cx='50' cy='25' rx='6.5' ry='10' transform='rotate({a} 50 50)'/>" for a in range(0, 360, 45))
              + ''.join(f"<circle cx='{x}' cy='{y}' r='2.8'/>" for x, y in ring(8, 33, rot=22.5))
              + ''.join(f"<circle cx='{x}' cy='{y}' r='2'/>" for x, y in ring(16, 45)))
_SCROLL = ("<path d='M0 0H44Q14 14 0 44Z'/><path d='M9 78C9 34 34 9 78 9' fill='none' stroke='#000' stroke-width='5' "
           "stroke-linecap='round'/><circle cx='9' cy='82' r='7'/><circle cx='82' cy='9' r='7'/><path d='M22 52C28 40 40 28 52 22' "
           "fill='none' stroke='#000' stroke-width='2.5'/><ellipse cx='30' cy='30' rx='5' ry='11' transform='rotate(-45 30 30)'/>")
SCROLLS = {c: svg(f"<g transform='{t}'>{_SCROLL}</g>") for c, t in (
    ('left top', ''), ('right top', 'translate(100 0) scale(-1 1)'), ('left bottom', 'translate(0 100) scale(1 -1)'),
    ('right bottom', 'translate(100 100) scale(-1 -1)'))}
ORNAMENT = ','.join([f'{ROSETTE} center/auto 58% no-repeat'] + [f'{u} {c}/auto 48% no-repeat' for c, u in SCROLLS.items()])
# the frame around the arena (a border-image, 40 px slices): mouldings, a row of beads, rosettes with garnets
_GOLD = ("<radialGradient id='b' cx='.35' cy='.35' r='.7'><stop offset='0' stop-color='#fff6cf'/><stop offset='.5' "
         "stop-color='#d8b04c'/><stop offset='1' stop-color='#5c3f0f'/></radialGradient><radialGradient id='j' cx='.35' cy='.35' "
         "r='.7'><stop offset='0' stop-color='#ff8a9a'/><stop offset='.45' stop-color='#a3142a'/><stop offset='1' "
         "stop-color='#3a0610'/></radialGradient>")
FRAME = svg(''.join(f"<rect x='{i}' y='{i}' width='{120 - 2 * i}' height='{120 - 2 * i}' fill='none' stroke='{c}' stroke-width='{w}'/>"
                    for i, w, c in ((1, 2, '#2a1a06'), (4, 4, '#f4dc86'), (7.5, 3, '#a37a26'), (10, 2, '#f9e9a8'), (12.5, 1.5, '#4a3310'),
                                    (20, 13, '#b8902e'), (27, 1.5, '#4a3310'), (30.5, 5, '#f0d27a'), (34.5, 3, '#8a6420'),
                                    (37, 2, '#e8c766'), (39, 2, '#2a1a06')))
            + ''.join(f"<circle cx='{x}' cy='{y}' r='3.4' fill='url(#b)'/>" for t in (44, 52, 60, 68, 76)
                      for x, y in ((t, 20), (t, 100), (20, t), (100, t)))
            + ''.join(f"<circle cx='{cx}' cy='{cy}' r='16' fill='url(#b)' stroke='#4a3310'/>"
                      + ''.join(f"<ellipse cx='{x}' cy='{y}' rx='3' ry='6' transform='rotate({a} {x} {y})' fill='#f9e9a8' stroke='#6e4f16' "
                                f"stroke-width='.6'/>" for a, (x, y) in zip(range(0, 360, 45), ring(8, 10, cx, cy)))
                      + f"<circle cx='{cx}' cy='{cy}' r='5.5' fill='url(#j)' stroke='#4a3310'/>"
                      for cx, cy in ((20, 20), (100, 20), (20, 100), (100, 100))), 120, 120, _GOLD)
# a compass star inlaid in the floor
MEDALLION = svg("<circle cx='100' cy='100' r='97' fill='#1c0a0c' stroke='#d8b04c' stroke-width='4'/>"
                "<circle cx='100' cy='100' r='88' fill='#efe8d8' stroke='#7a1020' stroke-width='3'/>"
                f"<polygon points='{star(4, 62, 17, 100, 100, 45)}' fill='#7a1020' stroke='#3a0610' stroke-width='1.5'/>"
                f"<polygon points='{star(4, 84, 20, 100, 100)}' fill='#d8b04c' stroke='#5c3f0f' stroke-width='1.5'/>"
                "<circle cx='100' cy='100' r='15' fill='#1c0a0c' stroke='#d8b04c' stroke-width='3'/><circle cx='100' cy='100' r='6' fill='#d8b04c'/>",
                200, 200)
# damask for the walls (the page)
DAMASK = svg("<g fill='#b4324a' fill-opacity='.22'><ellipse cx='30' cy='44' rx='7' ry='17'/><path d='M30 4l6 8-6 8-6-8z'/>"
             "<circle cx='30' cy='74' r='3'/></g><g fill='none' stroke='#b4324a' stroke-opacity='.22' stroke-width='2.5'>"
             "<path d='M23 32C9 28 6 50 19 54'/><path d='M37 32C51 28 54 50 41 54'/><path d='M22 62C26 70 34 70 38 62'/></g>", 60, 84)
# velvet: swags under a pelmet, tassels, side curtains with gilt tie-backs (laid over the scene, inside the arena)
_FOLDS = '#4a0812 0,#8e1626 8px,#c23347 13px,#8e1626 18px,#4a0812 26px'
DRAPES = ','.join([
    'radial-gradient(ellipse 3.4% 2.4% at 3.6% 63%,#fff2b8 0 25%,#d8b04c 50%,#6e4f16 72%,transparent 76%)',
    'radial-gradient(ellipse 3.4% 2.4% at 96.4% 63%,#fff2b8 0 25%,#d8b04c 50%,#6e4f16 72%,transparent 76%)',
    'radial-gradient(ellipse 7px 15px at 0 50%,#fff2b8 0 25%,#d8b04c 50%,#6e4f16 75%,transparent 80%) 0 9%/20% 7% repeat-x',
    'linear-gradient(#e3c463 0 2px,#6e4f16 2px 3px,transparent 3px) 0 3.2%/100% 4px no-repeat',
    'linear-gradient(#7a1020,#4a0812) 0 0/100% 3.3% no-repeat',
    'radial-gradient(ellipse 50% 100% at 50% 0,#c23347 0,#8e1626 45%,#5a0a14 86%,#f4dc86 88%,#a37a26 96%,transparent 100%) 0 0/20% 14% repeat-x',
    'linear-gradient(90deg,transparent 55%,rgb(0 0 0/.55)) 0 0/7% 100% no-repeat',
    f'repeating-linear-gradient(90deg,{_FOLDS}) 0 0/7% 100% no-repeat',
    'linear-gradient(-90deg,transparent 55%,rgb(0 0 0/.55)) 100% 0/7% 100% no-repeat',
    f'repeating-linear-gradient(-90deg,{_FOLDS}) 100% 0/7% 100% no-repeat'])
style('baroque',
      k='color-mix(in oklab,color-mix(in oklab,var(--cs),#5a0f1e 28%) calc((0.12 + 0.88 * {l}) * 100%),#0b0503)',
      vars=dict(g='{l}'),
      face=(f'--gl:{GILT};background:repeating-linear-gradient(45deg,rgb(0 0 0/.14) 0 1px,transparent 1px 8px),'
            'repeating-linear-gradient(-45deg,rgb(255 220 150/.08) 0 1px,transparent 1px 8px),{k};'
            'box-shadow:inset 0 0 0 2px var(--gl),inset 0 0 0 3.5px rgb(0 0 0/.45),inset 0 0 0 4.5px var(--gl),inset 0 0 16px rgb(0 0 0/.5)'),
      # (the ornament: a mask, so a literal parsed once, filled with the face's --gl)
      frame=f'.bx .f::before{{content:"";position:absolute;inset:5px;background:var(--gl);-webkit-mask:{ORNAMENT};mask:{ORNAMENT}}}',
      sp='color:color-mix(in oklab,#e0bd5a,#fff6d5 calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(10 4 2/.85),rgb(10 4 2/0))',
      css=ui('#1f070c', '#2c0d13', '#f2e3c0', '#b08f6a', '#5b3a1c', '#d8b04c', '#1f070c', 'dark', SERIF) + f"""
body{{background:{DAMASK} 0 0/60px 84px,{DAMASK} 30px 42px/60px 84px,var(--bg)}}
header h1{{font-style:italic;font-weight:400}}
header h1::before{{content:"❦ ";color:var(--acc);font-style:normal}}
header h1::after{{content:" ❧";color:var(--acc);font-style:normal}}
.stage{{position:relative;width:auto;margin:var(--fw);--fw:clamp(12px,2.8vw,30px)}}
.stage::after{{content:"";position:absolute;inset:calc(-1 * var(--fw));border:var(--fw) solid transparent;
  border-image:{FRAME} 40 round;pointer-events:none;filter:drop-shadow(0 10px 14px rgb(0 0 0/.65))}}
.arena{{border:0;border-radius:0;box-shadow:0 0 0 2px #2a1a06;
  background:radial-gradient(ellipse 80% 70% at 42% 30%,#5a3f24,#1d120a 62%,#0b0604)}}
.arena::after{{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;box-shadow:inset 0 0 90px rgb(0 0 0/.75)}}
.arena::before{{content:"";position:absolute;inset:0;pointer-events:none;z-index:2;background:{DRAPES}}}
.floor{{border:3px solid #c9a640;box-shadow:inset 0 0 0 12px #2a0f12,inset 0 0 0 14px #d8b04c,inset 0 0 0 16px #2a0f12;
  background:{MEDALLION} center/36% auto no-repeat,
    repeating-linear-gradient(115deg,transparent 0 13px,rgb(120 110 100/.22) 13px 14px,transparent 14px 31px),
    conic-gradient(#ece5d6 0 25%,#1e1b17 0 50%,#ece5d6 0 75%,#1e1b17 0) 0 0/80px 80px}}
.ceil{{display:none}}
.post{{width:13px;margin-left:-6px;background:linear-gradient(90deg,rgb(0 0 0/.6),transparent 30% 55%,rgb(0 0 0/.65)),
  repeating-linear-gradient(-58deg,#fff0b0 0 2px,#d8b04c 2px 7px,#6e4f16 7px 10px,#3d2808 10px 12px,#b8902e 12px 16px)}}
.rail{{border:0;background:linear-gradient(#fff2b8 0 1px,#d8b04c 1px 4px,#6e4f16 4px 5px,transparent 5px),
  radial-gradient(circle at 50% 62%,#f4dc86 0 2.5px,#6e4f16 3px 4px,transparent 4.5px) 0 0/18px 100%,
  linear-gradient(rgb(120 16 32/.8),rgb(60 8 16/.9))}}
.disc{{background:radial-gradient(circle at 34% 28%,#fffbe8 0 3%,color-mix(in oklab,var(--c),#fff 35%) 9%,var(--c) 30%,
  color-mix(in oklab,var(--c) 45%,#0b0503) 72%,color-mix(in oklab,var(--c) 60%,#d8b04c) 90%,#0b0503)}}
.sp .eq{{border-width:3px}}""")

# ---- Mondrian: white planes, black bars, red, yellow and blue; one block per box, flat light in two bands ---------
MBLACK, MWHITE = '#111', '#f4f1e8'
_bar = lambda pos, size, col=MBLACK: f'linear-gradient({col} 0 0) {pos}/{size} no-repeat'
MONDRIAN_FACES = {  # by face index (FACES in gen3d.py): the front gets a strip, the top a block; the rest stay white
    0: [_bar('64% 0', '4px 100%'), _bar('100% 0', '35% 100%', '{k}')],
    4: [_bar('0 42%', '100% 4px'), _bar('0 0', '100% 42%', '{k}')],
}
style('mondrian',
      k=f'color-mix(in oklab,var(--cs) calc((0.84 + 0.16 * {step("{lam}", 0.15)}) * 100%),#000)',
      vars=dict(w=f'color-mix(in oklab,{MWHITE} calc((0.82 + 0.18 * {step("{lam}", 0.15)}) * 100%),#3a3a3a)'),
      face=lambda fi: 'background:' + ','.join(MONDRIAN_FACES.get(fi, []) + ['{w}']) + f';box-shadow:inset 0 0 0 4px {MBLACK}',
      sp=f'color:color-mix(in oklab,{MBLACK},#888 calc(var(--sel) * 100%))',
      # (the bodies' colours, by position: :is(#_) lifts the rules over gen3d.py's #w<i>{--c})
      frame=''.join(f'.bw:is(#_,.bw):nth-child(3n+{k}){{--c:{c}}}' for k, c in enumerate(('#d42a20', '#f7d02b', '#1d3f94'))),
      sh='background:radial-gradient(closest-side,rgb(17 17 17/.3) 0 84%,transparent 88%)',
      css=ui(MWHITE, '#fff', MBLACK, '#555', MBLACK, '#d42a20', '#fff', 'light',
             "Futura,'Century Gothic','Avenir Next','Helvetica Neue',Arial,sans-serif") + f"""
header h1{{text-transform:uppercase;letter-spacing:.06em;font-weight:800}}
.grp label,.grp button{{border-width:2px;border-radius:0}}
.arena{{border:6px solid {MBLACK};border-radius:0;
  background:{_bar('22% 0', '6px 100%')},{_bar('81% 0', '6px 100%')},{_bar('0 22%', '22% 6px')},{_bar('100% 64%', '19% 6px')},
    {_bar('0 0', '22% 22%', '#d42a20')},{_bar('100% 100%', '19% 36%', '#1d3f94')},{_bar('0 100%', '22% 30%', '#f7d02b')},{MWHITE}}}
.floor{{border:6px solid {MBLACK};
  background:{_bar('30% 0', '6px 100%')},{_bar('72% 0', '6px 100%')},{_bar('0 40%', '100% 6px')},{_bar('100% 75%', '28% 6px')},
    {_bar('0 0', '30% 40%', '#f7d02b')},{_bar('100% 100%', '28% 25%', '#1d3f94')},{_bar('51% 0', '42% 40%', '#d42a20')},{MWHITE}}}
.ceil{{display:none}}
.post{{width:6px;margin-left:-3px;background:{MBLACK}}}
.rail{{background:rgb(244 241 232/.55);border-top:6px solid {MBLACK}}}
.disc{{background:var(--c);border:5px solid {MBLACK}}}
.sp .eq{{border-width:4px}}""")


# ---- paper: a paper-cut diorama. Folded card bodies in pastel bands, layered paper-cut spheres, and scenery that
# stands in the scene, so it turns with the camera: a ground sheet and, on each side, three layers of cut-outs
# (hills, farther hills, clouds and the sun) facing the tray, culled when they face away ----------------------------
def _cut(shape, at, col, dx=.4, dy=4):
    """A cut-out shape and its hard shadow (a darker copy, a little right and down)."""
    x, y = (float(v[:-1]) for v in at.split())
    return (f'radial-gradient({shape} at {x}% {y}%,{col} 98%,transparent),'
            f'radial-gradient({shape} at {x + dx}% {y + dy}%,rgb(70 50 30/.22) 96%,transparent)')


# Distances from the tray's centre (the tray is 560 x 360) and heights put the layers' tops at about 120, 205 and 280
# units above the view's centre at the default camera (clouds lower, 220-250), which looks 28 degrees down: the sky shows above them.
D, D2, D3 = 380, 540, 760      # near hills, far hills, clouds and sun
_tree = lambda x, h: (f'radial-gradient(circle 8px at {x}% {100 - h}%,#5e9e5e 96%,transparent),'
                      f'linear-gradient(#8a6a4a 0 0) {x}% 100%/3px {h}% no-repeat')
HILLS = ','.join([_tree(x, h) for x, h in ((14, 62), (47, 70), (66, 55), (84, 66))]
                 + [_cut(f'ellipse {rx}% {ry}%', f'{x}% 100%', c, dy=6) for x, rx, ry, c in (
                     (5, 10, 70, '#7bb07a'), (22, 9, 95, '#86b884'), (38, 12, 60, '#7bb07a'), (57, 8, 85, '#86b884'),
                     (74, 11, 70, '#7bb07a'), (93, 9, 100, '#86b884'))])
FAR_HILLS = ','.join(_cut(f'ellipse {rx}% {ry}%', f'{x}% 100%', c, dy=4) for x, rx, ry, c in (
    (8, 14, 70, '#b9d6aa'), (30, 16, 100, '#c6dcb8'), (52, 12, 65, '#b9d6aa'), (72, 15, 90, '#c6dcb8'), (93, 12, 75, '#b9d6aa')))
CLOUDS = ','.join(_cut(f'ellipse {rx}% {ry}%', at, '#fffaf0', dy=8) for rx, ry, at in (
    (3.4, 30, '14% 55%'), (2.4, 24, '17% 38%'), (4, 32, '47% 45%'), (3, 28, '78% 55%'), (2, 20, '80.5% 40%')))
SUN = _cut('circle 22px', '62% 45%', '#f6c453', dy=8)
style('paper',
      k=f'color-mix(in oklab,color-mix(in oklab,var(--cs),#fff8ec 15%) calc((0.66 + 0.17 * {step("{lam}", 0)} + 0.17 * {step("{lam}", 0.55)}) * 100%),#4a3a2a)',
      face='background:linear-gradient(160deg,rgb(255 255 255/.18),transparent 45%),{k};'
           'box-shadow:inset 0 0 0 1px rgb(255 255 255/.6),inset 0 0 6px rgb(90 60 30/.12)',
      sp='color:color-mix(in oklab,rgb(255 255 255/.65),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(70 50 30/.45),rgb(70 50 30/0))',
      css=ui('#ece2cf', '#f8f2e6', '#3e3326', '#8a7a64', '#d3c4a8', '#e76f51', '#fff', 'light',
             "'Gill Sans','Gill Sans MT','Trebuchet MS',sans-serif") + f"""
.arena{{border:0;border-radius:3px;box-shadow:0 2px 6px rgb(60 40 20/.25);background:linear-gradient(#b5dbe8,#e6f0e6 70%)}}
{overlay(GRAIN + ',' + FIBRE, 'multiply', '240px,300px')}
.view{{filter:drop-shadow(4px 7px 5px rgb(70 50 30/.4))}}
.cam>.deco{{display:block}}
.deco>i,.deco>i::before,.deco>i::after{{backface-visibility:hidden}}
.deco>i::before,.deco>i::after{{content:"";position:absolute}}
.deco>i:first-child{{width:1200px;height:1200px;margin:-600px 0 0 -600px;border-radius:50%;transform:translateY(2px) rotateX(90deg);
  background:radial-gradient(closest-side,#dbe9b8,#c9dfa6)}}
.deco>i:not(:first-child){{width:{2 * D}px;height:50px;margin:-50px 0 0 {-D}px;transform-origin:50% 100%;background:{HILLS}}}
.deco>i:nth-child(2){{transform:translateZ({-D}px)}}
.deco>i:nth-child(3){{transform:rotateY(90deg) translateZ({-D}px)}}
.deco>i:nth-child(4){{transform:rotateY(180deg) translateZ({-D}px)}}
.deco>i:nth-child(5){{transform:rotateY(-90deg) translateZ({-D}px)}}
.deco>i:not(:first-child)::before{{left:{D - D2}px;right:{D - D2}px;top:-30px;bottom:0;transform:translateZ({D - D2}px);background:{FAR_HILLS}}}
.deco>i:not(:first-child)::after{{left:{D - D3}px;right:{D - D3}px;top:-25px;bottom:22px;transform:translateZ({D - D3}px);background:{CLOUDS}}}
.deco>i:nth-child(2)::after{{background:{SUN},{CLOUDS}}}
.floor{{border:0;background:linear-gradient(#f4ecdc 0 0) center/94% 92% no-repeat,#c9ad82}}
.ceil,.post{{display:none}}
.rail{{height:16px;margin-top:-3px;background:#e59a74;border-top:2px solid #f6c9ad}}
.disc{{background:radial-gradient(circle at 42% 40%,color-mix(in oklab,var(--c),#fff 50%) 0 26%,rgb(70 50 30/.3) 26.5% 28.5%,
  color-mix(in oklab,var(--c),#fff 28%) 29% 46%,rgb(70 50 30/.3) 46.5% 48.5%,var(--c) 49% 65%,rgb(70 50 30/.3) 65.5% 67.5%,
  color-mix(in oklab,var(--c) 78%,#5a4a3a) 68%)}}""")

NAMES = ['original'] + list(STYLES)


def inputs(default='original'):
    """The radios, as #app's first children: every rule tests them with :has(> …), which looks at #app's children only
    (a :has() without the > searches #app's whole subtree, the engine and 5,000 pointer cells, once per style pass)."""
    assert default in NAMES, f'ART={default}: not one of {", ".join(NAMES)}'
    return ''.join(f'<input type="radio" class="art-in" name="a" id="a-{n}"{" checked" if n == default else ""}>' for n in NAMES)


def labels():
    return ''.join(f'<label for="a-{n}">{n}</label>' for n in NAMES)


def svg():
    return ('<svg class="artfx" aria-hidden="true" width="0" height="0">' +
            ''.join(s['svg'] for s in STYLES.values() if s.get('svg')) + '</svg>')


def _pre(name):
    return f'#app:has(> #a-{name}:checked)'


def _root(name):
    return f':root:has(> body > #app > #a-{name}:checked)'


def _scope(name, css):
    """Scope flat rules (no nested blocks) to style `name`: `&x` is the root (+ x), `body…` is under the root, anything
    else is under #app."""
    def one(s):
        if s.startswith('&'):
            return _root(name) + s[1:]
        return f'{_root(name)} {s}' if s.split()[0] == 'body' else f'{_pre(name)} {s}'
    out = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sels = ','.join(one(x.strip()) for x in m.group(1).split(','))
        out.append(f'{sels}{{{" ".join(m.group(2).split())}}}')
    return '\n'.join(out)


def css(lams, lbl):
    """The styles' CSS for box faces lit by `lams` (gen3d.py's lighting terms); lbl is csslabel."""
    out = [lbl.section('Art styles', 'other looks, picked with the style radios (#app\'s first children): each rule is '
                                     'scoped to #app:has(> #a-NAME:checked); src/art3d.py'),
           lbl.group('The radios and their labels'),
           '.art-in{position:absolute;opacity:0;pointer-events:none}' +
           ''.join(f'{_pre(n)} label[for=a-{n}]{{background:var(--acc);color:var(--on-acc);border-color:var(--acc)}}'
                   f'#app:has(> #a-{n}:focus-visible) label[for=a-{n}]{{outline:2px solid var(--acc);outline-offset:2px}}'
                   for n in NAMES)]
    for name, s in STYLES.items():
        out.append(lbl.group(f'Style: {name}'))
        out.append(_scope(name, s['css']))
        if s.get('webkit'):
            # (WebKit only: a reference filter there skips composited descendants, and every body and scenery plane is
            # one; ../../bugs/webkit-reference-filter-composited.html)
            out.append('@supports (-webkit-backdrop-filter: none){' + _scope(name, s['webkit']) + '}')
        if s.get('keyframes'):
            out.append(s['keyframes'])
        # every frame: one rule on .bx (the faces' colours), one per face, .sp, .sh and `frame`, behind .cam's name
        frame = []
        dec = []
        for fi, lam in enumerate(lams):
            sub = dict(lam=f'({lam})', l=f'max(0, {lam})')
            dec.append(f'--k{fi}:' + s['k'].format(**sub))
            dec += [f'--{v}{fi}:' + t.format(**sub) for v, t in s.get('vars', {}).items()]
        frame.append(f'.bx{{{";".join(dec)}}}')
        for fi in range(len(lams)):
            face = s['face'](fi) if callable(s['face']) else s['face']
            frame.append(f'.bx .f{fi}{{' + face.format(k=f'var(--k{fi})', fi=fi, **{v: f'var(--{v}{fi})' for v in s.get('vars', {})}) + '}')
        frame.append(f'.sp{{{s["sp"]}}}')
        frame.append(f'.sh{{{s["sh"]}}}')
        frame.append(s.get('frame', ''))
        out.append(f'{_pre(name)} .cam{{container-name:art-{name}}}')
        out.append(f'@container art-{name}{{' + ''.join(frame) + '}')
    return '\n'.join(out)
