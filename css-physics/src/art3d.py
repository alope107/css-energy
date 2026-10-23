#!/usr/bin/env python3
"""Art styles: other looks for the same scene, picked at runtime with the "style" radios (no script).

build3d.py puts inputs() (the radios) first in #app, labels() in the controls row, svg() (the styles' SVG filters)
at the end of the body and css(lams) in the page's stylesheet; lams[fi] is box face fi's lighting term from gen3d.py
(a calc() of the body's rotation matrix, -1 to 1). "plain" is the default and has no rules: its look is ui3d.css's
and gen3d.py's.

Cost: the plain page must cost what it did without the styles (BENCHMARKS.md "Art styles"). Two rules keep it so.
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
so faces inherit them). In `face`, {k}, {<var name>} and {fi} are the face's.
"""
import re
import urllib.parse


def step(x, e, w=40):
    """0 below e, 1 above it, a ramp 1/w wide: a hard band edge without round() (about 5 µs)."""
    return f'clamp(0, ({x} - {e}) * {w}, 1)'


def svg_uri(svg):
    return 'url("data:image/svg+xml,' + urllib.parse.quote(' '.join(svg.split()), safe="=/:;,'()") + '")'


def noise(base, matrix, size=240, kind='fractalNoise', octaves=3, seed=1):
    """A tile of SVG turbulence as a CSS image: colour matrix `matrix` (20 numbers) applied to the noise."""
    return svg_uri(f"""<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}'>
      <filter id='n' x='0' y='0' width='100%' height='100%'><feTurbulence type='{kind}' baseFrequency='{base}'
      numOctaves='{octaves}' seed='{seed}' stitchTiles='stitch'/><feColorMatrix values='{matrix}'/></filter>
      <rect width='100%' height='100%' filter='url(#n)'/></svg>""")


# overlays laid over the whole arena (static: rasterized once, blended by the compositor)
GRAIN = noise('.9', '0 0 0 0 .16  0 0 0 0 .15  0 0 0 0 .13  -1 0 0 0 .52', octaves=3, seed=4)
FIBRE = noise('.07', '0 0 0 0 .45  0 0 0 0 .35  0 0 0 0 .22  0 0 -.45 0 .26', size=300, octaves=4, seed=11)
CANVAS = noise('.9 .9', '0 0 0 0 .2  0 0 0 0 .15  0 0 0 0 .1  -1.6 0 0 0 1', octaves=2, seed=5)
STROKES = noise('.035 .16', '3 0 0 0 -1  3 0 0 0 -1  3 0 0 0 -1  0 0 0 0 1', size=320, octaves=3, seed=8)


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


# ---- cel: toon shading in three hard bands, thick ink outlines, a shine streak on lit faces ----------------------
INK = '#1b1724'
style('cel',
      k=f'color-mix(in oklab,var(--cs) calc((0.5 + 0.28 * {step("{lam}", 0.1)} + 0.22 * {step("{lam}", 0.62)}) * 100%),#2a1b4a)',
      vars=dict(s=f'calc(0.85 * {step("{lam}", 0.62)})'),
      face=f'background:linear-gradient(135deg,transparent 14%,rgb(255 255 255/{{s}}) 14% 22%,transparent 22% 27%,'
           f'rgb(255 255 255/{{s}}) 27% 30%,transparent 30%),{{k}};box-shadow:inset 0 0 0 3px {INK}',
      sp=f'color:color-mix(in oklab,{INK},var(--acc) calc(var(--sel) * 100%))',
      sh=f'background:radial-gradient(closest-side,rgb(27 23 36/.5) 0 86%,transparent 90%)',
      css=ui('#fff4dc', '#fffdf7', INK, '#5b5566', INK, '#ff4d6d', '#fff', 'light',
             "'Trebuchet MS','Avenir Next',Verdana,sans-serif") + f"""
header h1{{font-weight:900;letter-spacing:0}}
.grp label,.grp button{{border-width:2px;border-radius:8px}}
.arena{{border:3px solid {INK};border-radius:12px;
  background:radial-gradient(circle,rgb(27 23 36/.09) 1.3px,transparent 1.7px) 0 0/9px 9px,linear-gradient(#78cdfc,#e3f6ff 72%)}}
.floor{{background:linear-gradient(rgb(27 23 36/.22) 3px,transparent 3px) 0 0/80px 80px,
  linear-gradient(90deg,rgb(27 23 36/.22) 3px,transparent 3px) 0 0/80px 80px,#ffd166;border:4px solid {INK}}}
.ceil{{border:2px dashed rgb(27 23 36/.3)}}
.post{{width:3px;background:{INK}}}
.rail{{background:rgb(239 71 111/.5);border-top:3px solid {INK}}}
.disc{{border:3px solid {INK};background:radial-gradient(circle at 34% 28%,#fff 0 9%,transparent 10%),
  radial-gradient(circle at 40% 36%,var(--c) 0 54%,color-mix(in oklab,var(--c) 58%,#2a1b4a) 55%)}}""")

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
      svg="""<filter id="art-pencil" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" seed="7"/>
  <feDisplacementMap in="SourceGraphic" scale="3.5" xChannelSelector="R" yChannelSelector="G"/></filter>""")

# ---- wireframe: glowing edges and diagonals, hidden lines shown, spheres as globes --------------------------------
GREEN = 'rgb(57 255 136'
style('wireframe',
      k='color-mix(in oklab,color-mix(in oklab,var(--cs),#fff 35%) calc((0.62 + 0.38 * {l}) * 100%),transparent)',
      face='background:linear-gradient(to top right,transparent calc(50% - .6px),color-mix(in oklab,{k} 60%,transparent) '
           'calc(50% - .6px) calc(50% + .6px),transparent calc(50% + .6px)),color-mix(in oklab,{k} 7%,transparent);'
           'box-shadow:inset 0 0 0 1.3px {k};backface-visibility:visible',
      sp='color:color-mix(in oklab,color-mix(in oklab,var(--c),#fff 35%),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,transparent 62%,color-mix(in oklab,var(--c) 70%,transparent) 67% 71%,transparent 76%)',
      css=ui('#020806', '#05140d', '#b9ffd6', '#3c8a5f', '#0f3a26', '#39ff88', '#021208', 'dark') + f"""
.arena{{border:1px solid #145c38;background:radial-gradient(120% 90% at 50% 30%,#03140c,#010403)}}
.arena::after{{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(rgb(0 0 0/.22) 0 1px,transparent 1px 3px)}}
.view{{filter:drop-shadow(0 0 3px {GREEN}/.6))}}
.floor{{background:linear-gradient({GREEN}/.28) 1px,transparent 1px) 0 0/40px 40px,
  linear-gradient(90deg,{GREEN}/.28) 1px,transparent 1px) 0 0/40px 40px;border:1px solid {GREEN}/.75)}}
.ceil{{border:1px solid {GREEN}/.3)}}
.post{{background:{GREEN}/.4)}}
.rail{{background:none;border-top:1px solid {GREEN}/.65)}}
.disc{{border:1.2px solid color-mix(in oklab,var(--c),#fff 35%);
  background:radial-gradient(circle,transparent 60%,color-mix(in oklab,var(--c) 20%,transparent))}}
.sp .eq{{border-width:1.2px}}
.sp .eq::before,.sp .eq::after{{content:"";position:absolute;inset:-1.2px;border:1.2px solid;border-radius:50%}}
.sp .eq:not(.eq2)::before{{transform:rotateY(60deg)}}
.sp .eq:not(.eq2)::after{{transform:rotateY(-60deg)}}
.sp .eq2::before{{transform:translateZ(calc(var(--r) * .5px)) scale(.866)}}
.sp .eq2::after{{transform:translateZ(calc(var(--r) * -.5px)) scale(.866)}}""")

# ---- baroque: chiaroscuro jewel tones, gilded frames and medallions, a marble floor in a gilt-framed painting ---
GILT = 'color-mix(in oklab,#f6dc8a calc((0.18 + 0.82 * {g}) * 100%),#3d2808)'
style('baroque',
      k='color-mix(in oklab,color-mix(in oklab,var(--cs),#5a0f1e 28%) calc((0.12 + 0.88 * {l}) * 100%),#0b0503)',
      vars=dict(g='{l}'),
      face=(f'background:radial-gradient(circle,{GILT} 0 4.5%,transparent 5%),'
            f'radial-gradient(circle,transparent 9%,{GILT} 9.5% 11%,transparent 11.5%),'
            + ','.join(f'radial-gradient(circle at {c},{GILT} 0 7%,transparent 7.5%)' for c in ('0 0', '100% 0', '0 100%', '100% 100%')) +
            f',{{k}};box-shadow:inset 0 0 0 2px {GILT},inset 0 0 0 4px rgb(0 0 0/.4),inset 0 0 0 5px {GILT},inset 0 0 14px rgb(0 0 0/.45)'),
      sp='color:color-mix(in oklab,#e0bd5a,#fff6d5 calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(10 4 2/.85),rgb(10 4 2/0))',
      css=ui('#1f070c', '#2c0d13', '#f2e3c0', '#b08f6a', '#5b3a1c', '#d8b04c', '#1f070c', 'dark', SERIF) + """
body{background:radial-gradient(circle,rgb(150 40 60/.22) 0 9%,transparent 10%) 0 0/46px 46px,
  radial-gradient(circle,transparent 0 30%,rgb(150 40 60/.14) 31% 34%,transparent 35%) 23px 23px/46px 46px,var(--bg)}
header h1{font-style:italic;font-weight:400}
.arena{border:0;border-radius:2px;
  box-shadow:0 0 0 3px #4a3310,0 0 0 6px #e3c463,0 0 0 8px #8a6420,0 0 0 11px #f4dc86,0 0 0 13px #5c3f0f,0 14px 40px rgb(0 0 0/.7);
  background:radial-gradient(ellipse 80% 70% at 48% 32%,#4a3420,#1d120a 62%,#0b0604)}
.arena::after{content:"";position:absolute;inset:0;pointer-events:none;z-index:1;box-shadow:inset 0 0 90px rgb(0 0 0/.7)}
.floor{border:3px solid #c9a640;
  background:repeating-linear-gradient(115deg,transparent 0 13px,rgb(120 110 100/.22) 13px 14px,transparent 14px 31px),
    conic-gradient(#ece5d6 0 25%,#1e1b17 0 50%,#ece5d6 0 75%,#1e1b17 0) 0 0/80px 80px}
.ceil{display:none}
.post{width:7px;margin-left:-3px;background:linear-gradient(90deg,#5c3f0f,#f4dc86 40%,#c9a640 60%,#4a3310)}
.rail{background:linear-gradient(#f4dc86 0 2px,#8a6420 2px 4px,rgb(90 15 30/.6) 4px);border:0}
.disc{background:radial-gradient(circle at 34% 28%,#fffbe8 0 3%,color-mix(in oklab,var(--c),#fff 35%) 9%,var(--c) 30%,
  color-mix(in oklab,var(--c) 45%,#0b0503) 72%,color-mix(in oklab,var(--c) 60%,#d8b04c) 90%,#0b0503)}
.sp .eq{border-width:3px}""")

# ---- undulating: op-art stripes everywhere, seen through a rippling lens; the background stripes flow ------------
CREAM, BLACK = '#f2eee4', '#121212'
style('undulating',
      k=f'color-mix(in oklab,var(--cs) calc((0.4 + 0.6 * {{l}}) * 100%),{BLACK})',
      vars=dict(w=f'color-mix(in oklab,{CREAM} calc((0.5 + 0.5 * {{l}}) * 100%),{BLACK})'),
      face=lambda fi: f'background:repeating-linear-gradient({(0, 0, 90, 90, 45, 45)[fi]}deg,{{k}} 0 4px,{{w}} 4px 8px)',
      sp=f'color:color-mix(in oklab,{BLACK},var(--acc) calc(var(--sel) * 100%))',
      sh=f'background:radial-gradient(closest-side,rgb(18 18 18/.85) 0 70%,transparent 74%)',
      css=ui(CREAM, '#fff', BLACK, '#555', BLACK, '#e8336e', '#fff', 'light',
             "'Helvetica Neue',Helvetica,Arial,sans-serif") + f"""
.arena{{border:2px solid {BLACK};border-radius:0;background:{CREAM}}}
.view{{filter:url(#art-wave)}}
.view::before{{content:"";position:absolute;left:-80px;top:-80px;width:1060px;height:720px;
  background:repeating-linear-gradient({BLACK} 0 7px,{CREAM} 7px 14px);animation:art-flow 1.6s linear infinite}}
.floor{{background:repeating-linear-gradient(90deg,{BLACK} 0 7px,{CREAM} 7px 14px);border:2px solid {BLACK}}}
.ceil{{display:none}}
.post{{width:2px;background:{BLACK}}}
.rail{{background:repeating-linear-gradient(90deg,{CREAM} 0 7px,{BLACK} 7px 14px);border-top:2px solid {BLACK}}}
.disc{{background:radial-gradient(circle at 36% 30%,transparent 25%,rgb(0 0 0/.5)),
  repeating-radial-gradient(circle at 40% 35%,var(--c) 0 3.5px,{CREAM} 3.5px 7px)}}
.sp .eq{{border-width:3px}}""",
      keyframes='@keyframes art-flow{from{transform:translateY(0)}to{transform:translateY(14px)}}',
      svg="""<filter id="art-wave" x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.0035 0.008" numOctaves="2" seed="2"/>
  <feDisplacementMap in="SourceGraphic" scale="48" xChannelSelector="R" yChannelSelector="G"/></filter>""")

# ---- impressionist: sunlit pastels, coloured (violet) shadows, broken dabs of colour, a lily pond ---------------
style('impressionist',
      k='color-mix(in oklab,color-mix(in oklab,var(--cs),#fff2c8 8%) calc((0.55 + 0.45 * {l}) * 100%),#3b49b5)',
      face='background:' + ','.join(f'radial-gradient(ellipse {w}% {h}% at {x}% {y}%,{c},transparent)' for w, h, x, y, c in (
          (30, 9, 26, 22, 'rgb(255 247 210/.5)'), (22, 8, 70, 35, 'rgb(255 190 150/.35)'), (26, 8, 38, 55, 'rgb(90 110 220/.3)'),
          (20, 7, 74, 72, 'rgb(255 240 200/.4)'), (24, 8, 30, 86, 'rgb(110 80 200/.3)'), (18, 6, 58, 14, 'rgb(150 220 170/.3)'))) + ',{k}',
      sp='color:color-mix(in oklab,rgb(255 250 230/.6),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(70 70 160/.5),rgb(70 70 160/0))',
      css=ui('#f1ecdf', '#fbf8f0', '#3a3a5c', '#7d7a8f', '#cfc6b2', '#e07a5f', '#fff', 'light', 'Georgia,serif') + f"""
.arena{{border:0;border-radius:4px;box-shadow:0 1px 4px rgb(60 50 30/.25);
  background:radial-gradient(ellipse 60% 40% at 15% 20%,#f9e7b5,transparent 70%),radial-gradient(ellipse 50% 45% at 85% 15%,#c9d7f0,transparent 70%),
    radial-gradient(ellipse 70% 50% at 60% 90%,#b9d9b0,transparent 70%),linear-gradient(#dfe6f2,#e9e4d0)}}
{overlay(STROKES, 'soft-light', '320px', 'opacity:.55')}
.view{{filter:url(#art-impress) saturate(1.25)}}
.floor{{border:0;background:radial-gradient(ellipse 9% 6% at 25% 30%,#f2b8c8 0 25%,#7fb27a 35%,transparent 70%),
  radial-gradient(ellipse 14% 9% at 70% 55%,#8dbf86,transparent 70%),radial-gradient(ellipse 8% 5% at 42% 75%,#fff2c0 0 25%,#7fb27a 35%,transparent 70%),
  radial-gradient(ellipse 20% 12% at 85% 25%,#6fa57c,transparent 70%),radial-gradient(ellipse 16% 10% at 12% 80%,#7fb27a,transparent 70%),
  linear-gradient(160deg,#7ea7c9,#9cc3c9 50%,#6f97b8)}}
.ceil{{display:none}}
.post{{background:rgb(90 100 140/.25)}}
.rail{{background:linear-gradient(rgb(120 160 110/.55),rgb(90 130 100/.25));border-top:2px solid rgb(240 230 200/.7)}}
.disc{{background:radial-gradient(circle at 34% 28%,#fffbe6 0 6%,color-mix(in oklab,var(--c),#fff6dc 30%) 22%,var(--c) 45%,
  color-mix(in oklab,var(--c) 55%,#50519c) 85%)}}""",
      svg="""<filter id="art-impress" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.08 0.14" numOctaves="2" seed="4"/>
  <feDisplacementMap in="SourceGraphic" scale="5" xChannelSelector="R" yChannelSelector="G"/><feGaussianBlur stdDeviation=".5"/></filter>""")

# ---- Mondrian: white planes, black bars, red, yellow and blue blocks; flat light in two bands -------------------
MBLACK, MWHITE = '#111', '#f4f1e8'
_bar = lambda pos, size, col=MBLACK: f'linear-gradient({col} 0 0) {pos}/{size} no-repeat'
MONDRIAN_FACES = [   # three compositions, by face index
    [_bar('40% 0', '5px 100%'), _bar('0 62%', '100% 5px'), _bar('0 0', '40% 62%', '{k}')],
    [_bar('68% 0', '5px 100%'), _bar('100% 35%', '32% 5px'), _bar('100% 100%', '32% 65%', '{k}')],
    [_bar('0 30%', '100% 5px'), _bar('25% 100%', '5px 70%'), _bar('0 100%', '25% 70%', '{k}')],
]
style('mondrian',
      k=f'color-mix(in oklab,var(--cs) calc((0.84 + 0.16 * {step("{lam}", 0.15)}) * 100%),#000)',
      vars=dict(w=f'color-mix(in oklab,{MWHITE} calc((0.82 + 0.18 * {step("{lam}", 0.15)}) * 100%),#3a3a3a)'),
      face=lambda fi: 'background:' + ','.join(MONDRIAN_FACES[fi % 3]) + f',{{w}};box-shadow:inset 0 0 0 4px {MBLACK}',
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

# ---- oil: dark warm ground, rich colour, glossy highlights, brush streaks, smeared edges, canvas weave ------------
style('oil',
      k='color-mix(in oklab,color-mix(in oklab,var(--cs),#4a2a10 15%) calc((0.2 + 0.8 * {l}) * 100%),#140a04)',
      vars=dict(h='calc(clamp(0, ({lam} - 0.72) * 3, 1) * 0.55)'),
      face='background:radial-gradient(ellipse at 30% 25%,rgb(255 246 225/{h}),transparent 65%),'
           'linear-gradient(170deg,rgb(255 230 190/.1),transparent 40%,rgb(0 0 0/.12)),{k}',
      sp='color:color-mix(in oklab,rgb(255 236 200/.35),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(15 8 3/.85),rgb(15 8 3/0))',
      css=ui('#1a120b', '#251a10', '#efe2c8', '#a48b6a', '#4a3622', '#e0a458', '#1a120b', 'dark', 'Georgia,serif') + f"""
.arena{{border:0;border-radius:2px;box-shadow:0 0 0 9px #2b1d10,0 0 0 11px #6a4c28,0 12px 30px rgb(0 0 0/.6);
  background:radial-gradient(ellipse 75% 65% at 45% 30%,#7a5a36,#3a2716 50%,#1b110a)}}
{overlay(CANVAS, 'overlay', '240px', 'opacity:.9')}
.view{{filter:url(#art-oil)}}
.floor{{border:0;background:linear-gradient(90deg,rgb(0 0 0/.12),transparent 20% 70%,rgb(255 220 170/.08)),linear-gradient(#5e3c20,#47301a)}}
.ceil,.post{{display:none}}
.rail{{background:linear-gradient(#6b4626,#3e2614);border-top:2px solid #8a6038;opacity:.85}}
.disc{{background:radial-gradient(circle at 33% 27%,#fff8e6 0 4%,color-mix(in oklab,var(--c),#fff3d6 35%) 12%,var(--c) 34%,
  color-mix(in oklab,var(--c) 50%,#160c05) 70%,color-mix(in oklab,var(--c) 65%,#7a4a20) 88%,#160c05)}}""",
      svg="""<filter id="art-oil" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.03 0.12" numOctaves="2" seed="9"/>
  <feDisplacementMap in="SourceGraphic" scale="5" xChannelSelector="R" yChannelSelector="G" result="d"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.035 0.13" numOctaves="2" seed="3"/>
  <feDiffuseLighting surfaceScale="1.4" lighting-color="#fff"><feDistantLight azimuth="235" elevation="60"/></feDiffuseLighting>
  <feComposite in="d" operator="arithmetic" k1=".75" k2=".38"/></filter>""")

# ---- plasma: glowing see-through bodies, plasma-globe spheres, the whole arena cycling through hues -------------
style('plasma',
      k='color-mix(in oklab,var(--cs),#fff calc((0.05 + 0.3 * {l}) * 100%))',
      face='background:radial-gradient(closest-side,rgb(255 255 255/.85),color-mix(in oklab,{k} 70%,transparent) 50%,'
           'color-mix(in oklab,{k} 30%,transparent));box-shadow:inset 0 0 0 1px color-mix(in oklab,{k},#fff 50%),'
           'inset 0 0 10px {k},0 0 12px color-mix(in oklab,{k} 70%,transparent);backface-visibility:visible',
      sp='color:color-mix(in oklab,color-mix(in oklab,var(--c),#fff 50%),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,color-mix(in oklab,var(--c) 60%,transparent),transparent)',
      css=ui('#07010f', '#12051f', '#f3e8ff', '#9a7fc0', '#2c1450', '#ff2bd6', '#07010f', 'dark') + """
.arena{border:1px solid #3a1670;animation:art-hue 16s linear infinite;
  background:radial-gradient(circle at 20% 30%,rgb(255 0 170/.35),transparent 45%),radial-gradient(circle at 80% 25%,rgb(0 200 255/.35),transparent 45%),
    radial-gradient(circle at 60% 85%,rgb(140 0 255/.4),transparent 50%),radial-gradient(circle at 30% 80%,rgb(255 180 0/.25),transparent 45%),#07010f}
.floor{border:1px solid rgb(255 43 214/.6);box-shadow:0 0 18px rgb(255 43 214/.5);
  background:repeating-radial-gradient(circle,transparent 0 18px,rgb(255 43 214/.35) 20px,transparent 22px 40px),
    radial-gradient(closest-side,rgb(120 40 255/.35),transparent)}
.ceil{border-color:rgb(0 220 255/.2)}
.post{background:rgb(0 220 255/.5);box-shadow:0 0 6px rgb(0 220 255/.8)}
.rail{background:linear-gradient(rgb(0 220 255/.22),transparent);border-top:2px solid rgb(120 240 255/.9);box-shadow:0 -2px 10px rgb(0 220 255/.5)}
.disc{box-shadow:0 0 14px color-mix(in oklab,var(--c) 80%,transparent),inset 0 0 10px color-mix(in oklab,var(--c),#fff 30%);
  background:radial-gradient(circle,#fff 0 5%,color-mix(in oklab,var(--c),#fff 40%) 9%,transparent 22%),
    radial-gradient(circle,transparent 55%,color-mix(in oklab,var(--c) 70%,transparent) 92%,transparent),radial-gradient(circle,rgb(20 0 40/.6),rgb(20 0 40/.85))}
.disc::before{content:"";position:absolute;inset:6%;border-radius:50%;animation:art-spin 3s linear infinite;
  background:repeating-conic-gradient(transparent 0 9deg,color-mix(in oklab,var(--c),#fff 55%) 10deg,transparent 11.5deg 26deg);
  -webkit-mask:radial-gradient(circle,transparent 10%,#000 30% 70%,transparent 95%);mask:radial-gradient(circle,transparent 10%,#000 30% 70%,transparent 95%)}""",
      keyframes='@keyframes art-hue{from{filter:hue-rotate(0deg)}to{filter:hue-rotate(360deg)}}'
                '@keyframes art-spin{from{rotate:0deg}to{rotate:360deg}}')

# a paper-cut landscape: hills, clouds and a sun, each with a hard shadow (a darker copy a little down and right)
def _cut(shape, at, col, dx=.5, dy=1.2):
    x, y = (float(v[:-1]) for v in at.split())
    return (f'radial-gradient({shape} at {x}% {y}%,{col} 98%,transparent),'
            f'radial-gradient({shape} at {x + dx}% {y + dy}%,rgb(70 50 30/.22) 96%,transparent)')
PAPER_SCENE = ','.join([_cut('circle 34px', '84% 15%', '#f6c453'), _cut('ellipse 9% 3.2%', '18% 12%', '#fffaf0'),
                        _cut('ellipse 6% 2.6%', '24% 9%', '#fffaf0'), _cut('ellipse 8% 3%', '61% 8%', '#fffaf0'),
                        _cut('ellipse 38% 16%', '12% 44%', '#a9cf9a'), _cut('ellipse 42% 18%', '88% 46%', '#8fbf8a'),
                        _cut('ellipse 50% 14%', '50% 50%', '#c4dfa8'), 'linear-gradient(#bfe0ea,#eaf1e4 45%)'])


# ---- paper: folded card in pastel tones with white fold edges, layered paper-cut spheres, fibre texture ---------
style('paper',
      k=f'color-mix(in oklab,color-mix(in oklab,var(--cs),#fff8ec 15%) calc((0.66 + 0.17 * {step("{lam}", 0)} + 0.17 * {step("{lam}", 0.55)}) * 100%),#4a3a2a)',
      face='background:linear-gradient(160deg,rgb(255 255 255/.18),transparent 45%),{k};'
           'box-shadow:inset 0 0 0 1px rgb(255 255 255/.6),inset 0 0 6px rgb(90 60 30/.12)',
      sp='color:color-mix(in oklab,rgb(255 255 255/.65),var(--acc) calc(var(--sel) * 100%))',
      sh='background:radial-gradient(closest-side,rgb(70 50 30/.45),rgb(70 50 30/0))',
      css=ui('#ece2cf', '#f8f2e6', '#3e3326', '#8a7a64', '#d3c4a8', '#e76f51', '#fff', 'light',
             "'Gill Sans','Gill Sans MT','Trebuchet MS',sans-serif") + f"""
.arena{{border:0;border-radius:3px;box-shadow:0 2px 6px rgb(60 40 20/.25);background:{PAPER_SCENE}}}
{overlay(GRAIN + ',' + FIBRE, 'multiply', '240px,300px')}
.view{{filter:drop-shadow(4px 7px 5px rgb(70 50 30/.4))}}
.floor{{border:0;background:linear-gradient(#f4ecdc 0 0) center/94% 92% no-repeat,#c9ad82}}
.ceil,.post{{display:none}}
.rail{{height:16px;margin-top:-3px;background:#e59a74;border-top:2px solid #f6c9ad}}
.disc{{background:radial-gradient(circle at 42% 40%,color-mix(in oklab,var(--c),#fff 50%) 0 26%,rgb(70 50 30/.3) 26.5% 28.5%,
  color-mix(in oklab,var(--c),#fff 28%) 29% 46%,rgb(70 50 30/.3) 46.5% 48.5%,var(--c) 49% 65%,rgb(70 50 30/.3) 65.5% 67.5%,
  color-mix(in oklab,var(--c) 78%,#5a4a3a) 68%)}}""")

# Pixelate: keep one dot per cell (a flood tiled over the arena, `in` the picture) and dilate each dot to fill its cell.
# In fractions of the arena (primitiveUnits objectBoundingBox): WebKit places user-space primitive subregions from the
# page origin, not the element's box (../../bugs/README.md), so the 5 px version drew nothing there. The arena keeps
# VW:VH, so cells of 1/180 by 1/112 are square: a 180 x 112 picture. Morphology radii end up in whole device pixels
# (WebKit rounds down, leaving seams between cells): the blocks go over the unfiltered picture, so a seam shows it.
PX_W, PX_H = 180, 112
_fr = lambda cells, n: f'{cells / n:.6f}'.rstrip('0')
PIXELATE = (f'<filter id="art-pixel" x="0" y="0" width="1" height="1" primitiveUnits="objectBoundingBox" color-interpolation-filters="sRGB">'
            f'<feFlood x="{_fr(.33, PX_W)}" y="{_fr(.33, PX_H)}" width="{_fr(.34, PX_W)}" height="{_fr(.34, PX_H)}"/>'
            f'<feComposite width="{_fr(1, PX_W)}" height="{_fr(1, PX_H)}"/><feTile result="g"/>'
            f'<feComposite in="SourceGraphic" in2="g" operator="in"/><feMorphology operator="dilate" radius="{_fr(.35, PX_W)} {_fr(.35, PX_H)}"/>'
            '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode/></feMerge>')


# ---- pixel: 180 x 112 pixels and a posterized palette over everything, banded light, a starry sky ---------------------
PX = '#1a1c2c'
style('pixel',
      k=f'color-mix(in oklab,var(--cs) calc((0.45 + 0.3 * {step("{lam}", 0.05)} + 0.25 * {step("{lam}", 0.6)}) * 100%),{PX})',
      face=f'background:{{k}};box-shadow:inset 0 0 0 3px color-mix(in oklab,{{k}} 50%,{PX})',
      sp=f'color:color-mix(in oklab,{PX},var(--acc) calc(var(--sel) * 100%))',
      sh=f'background:radial-gradient(closest-side,rgb(26 28 44/.7) 0 80%,transparent 82%)',
      css=ui(PX, '#29366f', '#f4f4f4', '#94b0c2', '#3b5dc9', '#ffcd75', PX, 'dark') + f"""
header h1{{text-shadow:3px 3px 0 #b13e53}}
.grp label,.grp button{{border-width:2px;border-radius:0}}
.arena{{border:4px solid #f4f4f4;border-radius:0;filter:url(#art-pixel);
  background:radial-gradient(circle,#fff 0 1.5px,transparent 2px) 0 0/97px 61px,radial-gradient(circle,#ffcd75 0 1.5px,transparent 2px) 31px 17px/71px 53px,
    linear-gradient(#1a1c2c,#29366f 55%,#3b5dc9)}}
.floor{{background:conic-gradient(#38b764 0 25%,#257179 0 50%,#38b764 0 75%,#257179 0) 0 0/80px 80px;border:5px solid #a7f070}}
.ceil{{display:none}}
.post{{width:4px;background:#566c86}}
.rail{{background:rgb(93 39 93/.85);border-top:4px solid #b13e53}}
.disc{{border:3px solid {PX};background:radial-gradient(circle at 36% 30%,#f4f4f4 0 10%,color-mix(in oklab,var(--c),#fff 25%) 10% 32%,
  var(--c) 32% 62%,color-mix(in oklab,var(--c) 55%,{PX}) 62%)}}""",
      svg=PIXELATE + """
  <feComponentTransfer><feFuncR type="discrete" tableValues=".1 .3 .55 .8 1"/><feFuncG type="discrete" tableValues=".11 .3 .55 .8 1"/>
  <feFuncB type="discrete" tableValues=".17 .4 .6 .8 1"/></feComponentTransfer></filter>""")

NAMES = ['plain'] + list(STYLES)


def inputs(default='plain'):
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
