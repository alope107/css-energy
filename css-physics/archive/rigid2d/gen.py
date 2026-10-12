#!/usr/bin/env python3
"""Generator for rigid.css: a rigid body physics engine in pure CSS (no JavaScript in output).

Loop, once per style pass (Chrome runs two per frame, so 120 steps/s at 60 Hz):
  readback   state (x, y, angle, vx, vy, omega per body) is the progress of view timelines
             attached to hidden register elements, hoisted with timeline-scope
  solve      an XPBD-style contact solver written as registered custom properties over a chain
             of nested elements. Declarations sit inside @container style(--flag: 1) blocks
             keyed on flags computed one level up, so far-apart pairs and non-touching contacts
             are never declared at all:
               L0  predict, broadphase (bounding circles vs each other and the walls)
               L1  narrowphase: SAT reference-face manifolds for box/box, closest point for
                   circle/box, distance for circle/circle, corners/radius for walls
               L2  solve: each group's contacts reduced to one depth-weighted contact, then
                   Gauss-Seidel over batches (walls, then round-robin matchings of all pairs),
                   with friction, restitution and shock propagation; velocities rederived
  writeback  next state sets each register's `top`; Chrome re-samples view timelines after
             layout, which closes the loop with no dependency cycle.

Usage: gen.py [substeps] [out.html]        (SCENE=name picks the scene that loads first)
"""
import math, sys, os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 800, 500
S = int(sys.argv[1]) if len(sys.argv) > 1 else 2
HS = 1_000_000          # register scroller height, CSS px. Android lays out in physical px
                        # and LayoutUnit caps at ~33.5M, so this must stay well under 33.5M / DPR
GRAV = 1400.0
MU = 0.5
E = 0.4
BOUNCE_THR = 200.0
LIN_DAMP = 0.05
ANG_DAMP = 0.3
DENS = 0.001
MARGIN = 3.0
REF_TOL = 1.0   # box-box: also use the other box's face when overlaps are this close
SLOP = float(os.environ.get("SLOP", 0.3))   # allowed resting penetration
MAXCORR = float(os.environ.get('MAXCORR', 1.0))   # max extra depenetration per step
SKIN = 0.5      # box-box: face extent slack for corner clipping
SHOCK = float(os.environ.get('SHOCK', 0.25))   # inverse-mass scale for the lower body in a stacked contact
SWEEPS = int(os.environ.get("SWEEPS", 1))      # Gauss-Seidel sweeps per substep (1 or 2)

BODIES = [
    dict(k='box', hw=30, hh=30, col='#f2b134'),
    dict(k='box', hw=30, hh=30, col='#ed6a5a'),
    dict(k='box', hw=30, hh=30, col='#4ecdc4'),
    dict(k='box', hw=110, hh=11, col='#d6d3cc', dens=0.5),
    dict(k='box', hw=40, hh=20, col='#9b8cff'),
    dict(k='cir', r=26, col='#ff8fb1'),
    dict(k='cir', r=20, col='#7bd389'),
    dict(k='cir', r=34, col='#5aa9e6'),
    dict(k='cir', r=16, col='#ffd23f'),
    dict(k='cir', r=22, col='#ff9f43'),
]
N = len(BODIES)
for b in BODIES:
    if b['k'] == 'box':
        b['m'] = DENS * b.get('dens', 1) * 4 * b['hw'] * b['hh']
        b['I'] = b['m'] * ((2 * b['hw'])**2 + (2 * b['hh'])**2) / 12
        b['R'] = math.hypot(b['hw'], b['hh'])
    else:
        b['m'] = DENS * math.pi * b['r']**2
        b['I'] = 0.5 * b['m'] * b['r']**2
        b['R'] = b['r']
    b['im'] = 1 / b['m']
    b['ii'] = 1 / b['I']

SCENES = {
    'tower': [
        (560, 470, 0, 0, 0, 0), (560, 410, 0, 0, 0, 0), (560, 350, 0, 0, 0, 0),
        (560, 309, 0, 0, 0, 0), (560, 278, 0, 0, 0, 0),
        (120, 80, 0, 520, 0, 0), (200, 40, 0, 300, -100, 0), (90, 230, 0, 450, -300, 0),
        (300, 120, 0, 200, 0, 0), (700, 60, 0, -120, 0, 0),
    ],
    'rain': [
        (150, 60, 0.3, 0, 0, 2), (300, 30, 1.1, 0, 0, -3), (450, 80, 0.7, 0, 0, 1),
        (400, 200, 0.15, 0, 0, 0), (620, 40, 2.2, 0, 0, 4),
        (180, 200, 0, 60, 0, 0), (560, 150, 0, -80, 0, 0), (700, 220, 0, 0, 0, 0),
        (260, 140, 0, 0, 0, 0), (100, 330, 0, 200, 0, 0),
    ],
    'catapult': [
        (300, 470, 0, 0, 0, 0), (402, 30, 0, 0, 0, 0), (402, -32, 0, 0, 0, 0),
        (300, 429, 0, 0, 0, 0), (680, 480, 0, 0, 0, 0),
        (560, 474, 0, 0, 0, 0), (202, 398, 0, 0, 0, 0), (90, 466, 0, 0, 0, 0),
        (240, 402, 0, 0, 0, 0), (680, 438, 0, 0, 0, 0),
    ],
}
SCENES['stack'] = [
    (400, 470, 0, 0, 0, 0), (400, 410, 0, 0, 0, 0), (400, 350, 0, 0, 0, 0),
    (400, 289, 0, 0, 0, 0), (400, 258, 0, 0, 0, 0),
    (60, 470, 0, 0, 0, 0), (130, 476, 0, 0, 0, 0), (220, 462, 0, 0, 0, 0),
    (690, 480, 0, 0, 0, 0), (760, 474, 0, 0, 0, 0),
]
if os.environ.get('SCENE'):
    SCENES = {os.environ['SCENE']: SCENES[os.environ['SCENE']], **{k: v for k, v in SCENES.items() if k != os.environ['SCENE']}}
SCENE_NAMES = list(SCENES)
RANGES = dict(x=(-150, W + 150), y=(-150, H + 150), a=(0, 2 * math.pi),
              vx=(-6000, 6000), vy=(-6000, 6000), w=(-250, 250))
FIELDS = ['x', 'y', 'a', 'vx', 'vy', 'w']


def f(v):
    if isinstance(v, str):
        return v
    s = repr(round(float(v), 9))
    return s[:-2] if s.endswith('.0') else s


class Gen:
    def __init__(self):
        self.props = OrderedDict()   # name -> (syntax, inherits, init)
        self.decl = []               # (level, gate, name, expr)
        self.levels = 0

    def reg(self, name, inherits=True, syntax='<number>', init='0'):
        assert name not in self.props, name
        self.props[name] = (syntax, inherits, init)
        return f'var(--{name})'

    def P(self, name, expr, level, gate=None, syntax='<number>', inherits=True):
        v = self.reg(name, inherits, syntax)
        self.decl.append((level, gate, name, expr))
        self.levels = max(self.levels, level + 1)
        return v


g = Gen()
V = lambda n: f'var(--{n})'

# ---- L0: time, controls, readback --------------------------------------------
g.reg('now')
for c in ['gx', 'gy', 'att', 'mx', 'my', 'kick', 'rst']:
    g.reg(c)
for i in range(N):
    for fl in FIELDS:
        g.reg(f'i{fl}{i}')
        g.reg(f'{fl.upper()}{i}')
TP, DB = g.reg('TP'), g.reg('DB')
# Fixed step: each pass consumes exactly STEP seconds of real time when the budget allows,
# otherwise it is a no-op. A constant h keeps resting stacks perfectly still; Chrome runs two
# passes per frame, so 60 Hz gives real time and slow machines get slow motion, never blow-up.
STEP = 1 / 120
raw = g.P('raw', f'mod(var(--now) - {TP} + 100, 100)', 0)
avail = g.P('avail', f'min({DB} + {raw}, 0.05)', 0)
live = g.P('live', f'sign(max(0, {avail} - {f(STEP * 0.5)}))', 0)
consE = g.P('consE', f'{live} * {f(STEP)}', 0)
h = g.P('h', f'{f(STEP / S)}', 0)

# ---- contact candidates, grouped -----------------------------------------------
boxes = [i for i, b in enumerate(BODIES) if b['k'] == 'box']
CORN = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
WALLS = {'F': (0, -1), 'L': (1, 0), 'R': (-1, 0), 'C': (0, 1)}

groups = []
for i in range(N):
    for wl in WALLS:
        cs = [('cw', i, j, wl) for j in range(4)] if BODIES[i]['k'] == 'box' else [('rw', i, wl)]
        groups.append(dict(id=f'w{i}{wl}', a=i, b=None, wall=wl, cs=cs))
for x in range(N):
    for y in range(x + 1, N):
        kx, ky = BODIES[x]['k'], BODIES[y]['k']
        if kx == 'box' and ky == 'box':
            cs = [('bb', x, j, y) for j in range(4)] + [('bb', y, j, x) for j in range(4)]
        elif kx == 'cir' and ky == 'cir':
            cs = [('cc', x, y)]
        else:
            ci, bi = (x, y) if kx == 'cir' else (y, x)
            cs = [('bc', ci, bi)]
        groups.append(dict(id=f'p{x}_{y}', a=x, b=y, wall=None, cs=cs))
NCAND = sum(len(gr['cs']) for gr in groups)

# ---- mouse grab (L0, declared only while the pointer is pressed on the arena) ----------
# Pick: hit-test the pointer against every body's real shape, topmost (highest index) wins.
# Latch: registers GI (grabbed body + 1, 0 = none) and GX/GY (grab point in the body's own
# frame) persist the grab across passes, so a fast mouse can't drop it.
# Drag: a damped spring pulls the grab point toward the pointer, normalised by the point's
# effective inverse mass so a plank grabbed at its tip is as stable as a ball.
GRAB_K, GRAB_C, GRAB_AMAX, GRAB_TOL = 1500.0, 60.0, 40000.0, 3.0
GI, GXr, GYr = g.reg('GI'), g.reg('GX'), g.reg('GY')
AT = 'att'
hits, lxs, lys = [], [], []
for i, b in enumerate(BODIES):
    X, Y, A = V(f'X{i}'), V(f'Y{i}'), V(f'A{i}')
    ca, sa = f'cos({A})', f'sin({A})'
    lx = g.P(f'gl{i}x', f'{ca} * (var(--mx) - {X}) + {sa} * (var(--my) - {Y})', 0, AT)
    ly = g.P(f'gl{i}y', f'{ca} * (var(--my) - {Y}) - {sa} * (var(--mx) - {X})', 0, AT)
    if b['k'] == 'box':
        hit = f"sign(max(0, min({b['hw'] + GRAB_TOL} - abs({lx}), {b['hh'] + GRAB_TOL} - abs({ly}))))"
        cx = f"clamp({-b['hw']}, {lx}, {b['hw']})"
        cy = f"clamp({-b['hh']}, {ly}, {b['hh']})"
    else:
        dist = f'hypot({lx}, {ly})'
        hit = f"sign(max(0, {b['r'] + GRAB_TOL} - {dist}))"
        sc = f"min(1, {b['r'] * 0.9} / max({dist}, 0.000001))"
        cx, cy = f'{lx} * {sc}', f'{ly} * {sc}'
    hits.append(f'{hit} * {i + 1}')
    lxs.append(cx); lys.append(cy)
pick = g.P('gpick', f"max({', '.join(hits)})", 0, AT)
gprev = g.P('gprev', f'round({GI})', 0, AT)
G = g.P('G', f'{gprev} + (1 - sign({gprev})) * {pick}', 0, AT)
eqs = [g.P(f'eq{i}', f'1 - min(1, abs({G} - {i + 1}))', 0, AT) for i in range(N)]
fresh = f'(1 - sign({gprev}))'
sel = lambda terms: ' + '.join(f'{e} * {t}' for e, t in zip(eqs, terms))
ox = g.P('gox', f'{fresh} * ({sel(lxs)}) + (1 - {fresh}) * {GXr}', 0, AT)
oy = g.P('goy', f'{fresh} * ({sel(lys)}) + (1 - {fresh}) * {GYr}', 0, AT)
cG = g.P('gc', sel([f"cos(var(--A{i}))" for i in range(N)]), 0, AT)
sG = g.P('gs', sel([f"sin(var(--A{i}))" for i in range(N)]), 0, AT)
rx = g.P('grx', f'{cG} * {ox} - {sG} * {oy}', 0, AT)
ry = g.P('gry', f'{sG} * {ox} + {cG} * {oy}', 0, AT)
gpx = g.P('Ngpx', f"{sel([V(f'X{i}') for i in range(N)])} + {rx}", 0, AT)
gpy = g.P('Ngpy', f"{sel([V(f'Y{i}') for i in range(N)])} + {ry}", 0, AT)
wg = sel([V(f'W{i}') for i in range(N)])
vpx = f"({sel([V(f'VX{i}') for i in range(N)])} - ({wg}) * {ry})"
vpy = f"({sel([V(f'VY{i}') for i in range(N)])} + ({wg}) * {rx})"
imG = g.P('gim', sel([f(b['im']) for b in BODIES]), 0, AT)
iiG = g.P('gii', sel([f(b['ii']) for b in BODIES]), 0, AT)
adx = f'clamp(-{GRAB_AMAX}, {GRAB_K} * (var(--mx) - {gpx}) - {GRAB_C} * {vpx}, {GRAB_AMAX})'
ady = f'clamp(-{GRAB_AMAX}, {GRAB_K} * (var(--my) - {gpy}) - {GRAB_C} * {vpy}, {GRAB_AMAX})'
weff = f'({imG} + ({rx} * {rx} + {ry} * {ry}) * {iiG})'
Fx = g.P('gFx', f'{adx} / {weff}', 0, AT)
Fy = g.P('gFy', f'{ady} / {weff}', 0, AT)
g.P('gax', f'{Fx} * {imG}', 0, AT)
g.P('gay', f'{Fy} * {imG}', 0, AT)
g.P('gal', f'({rx} * {Fy} - {ry} * {Fx}) * {iiG}', 0, AT)
for i in range(N):   # render flag for the grabbed body's outline
    g.P(f'Neq{i}', f'{eqs[i]}', 0, AT)

# ---- substeps ------------------------------------------------------------------
st = {(i, fl): V(f'{fl.upper()}{i}') for i in range(N) for fl in FIELDS}
for k in range(S):
    L0, L1, L2 = (3 * k + d for d in range(3))
    p = f'k{k}'
    B = {}
    for i, b in enumerate(BODIES):
        X, Y, A = st[(i, 'x')], st[(i, 'y')], st[(i, 'a')]
        VX, VY, WW = st[(i, 'vx')], st[(i, 'vy')], st[(i, 'w')]
        axe = f'var(--gx) + var(--eq{i}) * var(--gax) + var(--kick) * 2600 * sin(var(--now) * 23 + {f(i * 2.1)})'
        aye = f'var(--gy) + var(--eq{i}) * var(--gay) - var(--kick) * 3400'
        damp = f'(1 - {LIN_DAMP} * {h})'
        u = g.P(f'{p}u{i}', f'({VX} + ({axe}) * {h}) * {damp}', L0)
        v = g.P(f'{p}v{i}', f'({VY} + ({aye}) * {h}) * {damp}', L0)
        om = g.P(f'{p}o{i}', f'({WW} + var(--eq{i}) * var(--gal) * {h}) * (1 - ({ANG_DAMP} + var(--eq{i}) * 3) * {h})', L0)
        px = g.P(f'{p}px{i}', f'{X} + {u} * {h}', L0)
        py = g.P(f'{p}py{i}', f'{Y} + {v} * {h}', L0)
        pa = g.P(f'{p}pa{i}', f'{A} + {om} * {h}', L0)
        d = dict(u=u, v=v, o=om, px=px, py=py, pa=pa, X=X, Y=Y, A=A)
        if b['k'] == 'box':
            d['c'] = g.P(f'{p}c{i}', f'cos({pa})', L0)
            d['s'] = g.P(f'{p}s{i}', f'sin({pa})', L0)
        B[i] = d

    for i in boxes:
        b, d = BODIES[i], B[i]
        d['q'] = []
        for j, (sx, sy) in enumerate(CORN):
            lx, ly = sx * b['hw'], sy * b['hh']
            qx = g.P(f'{p}qx{i}{j}', f"{d['px']} + {d['c']} * {f(lx)} - {d['s']} * {f(ly)}", L1)
            qy = g.P(f'{p}qy{i}{j}', f"{d['py']} + {d['s']} * {f(lx)} + {d['c']} * {f(ly)}", L1)
            d['q'].append((qx, qy))

    for gr in groups:
        a, bb, wl = gr['a'], gr['b'], gr['wall']
        Ra = BODIES[a]['R']
        if wl:
            pxa, pya = B[a]['px'], B[a]['py']
            e = {'F': f'{pya} + {f(Ra + MARGIN)} - {H}', 'L': f'{f(Ra + MARGIN)} - {pxa}',
                 'R': f'{pxa} + {f(Ra + MARGIN)} - {W}', 'C': f'{f(Ra + MARGIN)} - {pya}'}[wl]
        else:
            rr = Ra + BODIES[bb]['R'] + MARGIN
            e = (f"{f(rr * rr)} - pow({B[a]['px']} - {B[bb]['px']}, 2)"
                 f" - pow({B[a]['py']} - {B[bb]['py']}, 2)")
        gr['flag'] = f'{p}n{gr["id"]}'
        g.P(gr['flag'], f'sign(max(0, {e}))', L0, syntax='<integer>')

    # box-box reference faces (L1, gated by pair flag): SAT overlap on each box's own axes
    for gr in groups:
        if gr['cs'][0][0] != 'bb':
            continue
        gate = gr['flag']
        refs = {}
        for R, I in ((gr['a'], gr['b']), (gr['b'], gr['a'])):
            rp = f"{p}{gr['id']}r{R}"
            bR, bI, dR, dI = BODIES[R], BODIES[I], B[R], B[I]
            cR, sR = dR['c'], dR['s']
            ex, ey = f"({dI['px']} - {dR['px']})", f"({dI['py']} - {dR['py']})"
            ox = g.P(rp + 'ox', f'{cR} * {ex} + {sR} * {ey}', L1, gate)
            oy = g.P(rp + 'oy', f'{cR} * {ey} - {sR} * {ex}', L1, gate)
            cd = f"abs({dI['c']} * {cR} + {dI['s']} * {sR})"
            sd = f"abs({dI['s']} * {cR} - {dI['c']} * {sR})"
            ovx = f"({bR['hw']} + {bI['hw']} * {cd} + {bI['hh']} * {sd} - abs({ox}))"
            ovy = f"({bR['hh']} + {bI['hw']} * {sd} + {bI['hh']} * {cd} - abs({oy}))"
            fy = g.P(rp + 'fy', f'sign(max(0, {ovx} - {ovy}))', L1, gate)
            ovm = g.P(rp + 'om', f'min({ovx}, {ovy})', L1, gate)
            nlx = f'((1 - {fy}) * sign({ox}))'
            nly = f'({fy} * sign({oy}))'
            nx = g.P(rp + 'nx', f'{cR} * {nlx} - {sR} * {nly}', L1, gate)
            ny = g.P(rp + 'ny', f'{sR} * {nlx} + {cR} * {nly}', L1, gate)
            hn = g.P(rp + 'hn', f"(1 - {fy}) * {bR['hw']} + {fy} * {bR['hh']}", L1, gate)
            hl = f"((1 - {fy}) * {bR['hh']} + {fy} * {bR['hw']})"
            refs[R] = dict(ox=ox, oy=oy, fy=fy, ovm=ovm, nx=nx, ny=ny, hn=hn, hl=hl, rp=rp, I=I)
        a_, b_ = gr['a'], gr['b']
        for R, O in ((a_, b_), (b_, a_)):
            # use this reference face if its overlap is within tolerance of the best axis
            refs[R]['use'] = f"sign(max(0, {refs[O]['ovm']} - {refs[R]['ovm']} + {REF_TOL}))"
        gr['refs'] = refs

    for gr in groups:
        gate = gr['flag']
        gr['cdat'] = []
        for ci, ct in enumerate(gr['cs']):
            cp = f'{p}{gr["id"]}c{ci}'
            kind = ct[0]
            act_expr = None
            if kind == 'cw':
                _, a, j, wl = ct
                bb = None
                qx, qy = B[a]['q'][j]
                dd = '(' + {'F': f'{qy} - {H}', 'L': f'-1 * {qx}', 'R': f'{qx} - {W}', 'C': f'-1 * {qy}'}[wl] + ')'
                nx, ny = map(f, WALLS[wl])
                cx_, cy_ = qx, qy
            elif kind == 'rw':
                _, a, wl = ct
                bb = None
                r = BODIES[a]['r']
                pxa, pya = B[a]['px'], B[a]['py']
                dd = '(' + {'F': f'{pya} + {r} - {H}', 'L': f'{r} - {pxa}', 'R': f'{pxa} + {r} - {W}', 'C': f'{r} - {pya}'}[wl] + ')'
                nxv, nyv = WALLS[wl]
                nx, ny = f(nxv), f(nyv)
                cx_, cy_ = f'({pxa} - {f(nxv * r)})', f'({pya} - {f(nyv * r)})'
            elif kind == 'bb':
                # corner j of incident box `a` against the chosen face of reference box `bb`
                _, a, j, bb = ct
                rf = gr['refs'][bb]
                qx, qy = B[a]['q'][j]
                cB, sB, pxB, pyB = B[bb]['c'], B[bb]['s'], B[bb]['px'], B[bb]['py']
                lx = f'({cB} * ({qx} - {pxB}) + {sB} * ({qy} - {pyB}))'
                ly = f'({cB} * ({qy} - {pyB}) - {sB} * ({qx} - {pxB}))'
                fy = rf['fy']
                along = g.P(cp + 'al', f"(1 - {fy}) * sign({rf['ox']}) * {lx} + {fy} * sign({rf['oy']}) * {ly}", L1, gate)
                lat = f'((1 - {fy}) * {ly} + {fy} * {lx})'
                dd = g.P(cp + 'd', f"{rf['hn']} - {along}", L1, gate)
                nx, ny = rf['nx'], rf['ny']
                cx_, cy_ = qx, qy
                # active: penetrating the face plane, still on the box's slab, within face extent
                act_expr = (f"{rf['use']} * sign(max(0, min({dd}, {along} + {rf['hn']}, "
                            f"{rf['hl']} + {SKIN} - abs({lat}))))")
            elif kind == 'bc':
                _, a, bb = ct
                r = BODIES[a]['r']
                ob = BODIES[bb]
                cB, sB, pxB, pyB = B[bb]['c'], B[bb]['s'], B[bb]['px'], B[bb]['py']
                pxA, pyA = B[a]['px'], B[a]['py']
                lx = g.P(cp + 'lx', f'{cB} * ({pxA} - {pxB}) + {sB} * ({pyA} - {pyB})', L1, gate)
                ly = g.P(cp + 'ly', f'{cB} * ({pyA} - {pyB}) - {sB} * ({pxA} - {pxB})', L1, gate)
                gx_ = g.P(cp + 'gx', f'{lx} - clamp({-ob["hw"]}, {lx}, {ob["hw"]})', L1, gate)
                gy_ = g.P(cp + 'gy', f'{ly} - clamp({-ob["hh"]}, {ly}, {ob["hh"]})', L1, gate)
                dist = g.P(cp + 'di', f'hypot({gx_}, {gy_})', L1, gate)
                o = g.P(cp + 'o', f'sign({dist})', L1, gate)
                pnx = f'({ob["hw"]} - abs({lx}))'
                pny = f'({ob["hh"]} - abs({ly}))'
                fx = g.P(cp + 'fx', f'sign(max(0, {pny} - {pnx}))', L1, gate)
                nlx = f'({o} * {gx_} / max({dist}, 0.000001) + (1 - {o}) * {fx} * sign({lx}))'
                nly = f'({o} * {gy_} / max({dist}, 0.000001) + (1 - {o}) * (1 - {fx}) * sign({ly}))'
                dd = g.P(cp + 'd', f'{o} * ({r} - {dist}) + (1 - {o}) * ({r} + min({pnx}, {pny}))', L1, gate)
                nx = g.P(cp + 'nx', f'{cB} * {nlx} - {sB} * {nly}', L1, gate)
                ny = g.P(cp + 'ny', f'{sB} * {nlx} + {cB} * {nly}', L1, gate)
                cx_, cy_ = f'({pxA} - {nx} * {r})', f'({pyA} - {ny} * {r})'
            elif kind == 'cc':
                _, a, bb = ct
                ra, rb = BODIES[a]['r'], BODIES[bb]['r']
                ex = f"({B[a]['px']} - {B[bb]['px']})"
                ey = f"({B[a]['py']} - {B[bb]['py']})"
                dist = g.P(cp + 'di', f'max(hypot({ex}, {ey}), 0.000001)', L1, gate)
                nx = g.P(cp + 'nx', f'{ex} / {dist}', L1, gate)
                ny = g.P(cp + 'ny', f'{ey} / {dist}', L1, gate)
                dd = g.P(cp + 'd', f'{ra + rb} - {dist}', L1, gate)
                cx_, cy_ = f"({B[a]['px']} - {nx} * {ra})", f"({B[a]['py']} - {ny} * {ra})"

            act = g.P(cp + 'a', act_expr or f'sign(max(0, {dd}))', L1, gate, syntax='<integer>')
            gr['cdat'].append(dict(a=a, bb=bb, act=act, sg=cp + 'a', cp=cp, dd=dd, nx=nx, ny=ny, cx=cx_, cy=cy_))

    # ---- solve (L2): Gauss-Seidel over batches ---------------------------------------
    # batch 0 = every body against the walls; then round-robin matchings of all pairs, so
    # each body is touched at most once per batch and gets exactly one new version per batch.
    # Inside a group, the active contacts are first reduced to ONE depth-weighted contact
    # (patch reduction), which corrects a flat face's translation fully in one step.
    pair_of = {(gr['a'], gr['b']): gr for gr in groups if not gr['wall']}
    ring = list(range(N)) + ([None] if N % 2 else [])
    rounds = []
    for r in range(len(ring) - 1):
        rnd = []
        for t in range(len(ring) // 2):
            x, y = ring[t], ring[-1 - t]
            if x is not None and y is not None:
                rnd.append([pair_of[(min(x, y), max(x, y))]])
        rounds.append(rnd)
        ring = [ring[0]] + [ring[-1]] + ring[1:-1]
    walls_batch = [[gr for gr in groups if gr['wall'] and gr['a'] == i] for i in range(N)]
    batches = [walls_batch] + rounds
    if SWEEPS == 2:
        batches = batches + batches[::-1][1:]

    # position versions are universal-syntax properties declared only when that body's group in
    # that batch is near; readers take the newest declared one through a var() fallback chain
    vhist = {i: [] for i in range(N)}     # names of version props, oldest first

    def latest(i, fl):
        base = B[i][{'x': 'px', 'y': 'py', 'a': 'pa'}[fl]]
        e = base
        for vn_ in vhist[i]:
            e = f'var(--{vn_}{fl}, {e})'
        return e

    for i in range(N):
        g.P(f'{p}nw{i}', 'sign(' + ' + '.join(V(gr['flag']) for gr in groups if gr['wall'] and gr['a'] == i) + ')',
            L0, syntax='<integer>')


    def moved(body, nx, ny, rx, ry):
        """displacement of `body`'s material point at r along n, from corrections so far"""
        cr = f'({rx} * {ny} - {ry} * {nx})'
        return (f"(({latest(body, 'x')} - {B[body]['px']}) * {nx} + ({latest(body, 'y')} - {B[body]['py']}) * {ny}"
                f" + ({latest(body, 'a')} - {B[body]['pa']}) * {cr})")

    for bi, batch in enumerate(batches):
        newver = {}
        for unit in batch:          # a unit = groups touching the same bodies; deltas are summed
            dsum = {}
            for gr in unit:
                A_ = gr['a']; Bo = gr['b']
                gate = gr['flag']
                gp = f'{p}b{bi}{gr["id"]}'
                qs = []
                for ci, cd in enumerate(gr['cdat']):
                    sg, nx, ny = cd['sg'], cd['nx'], cd['ny']
                    a, bb = cd['a'], cd['bb']
                    rx = f"({cd['cx']} - {B[a]['px']})"
                    ry = f"({cd['cy']} - {B[a]['py']})"
                    mv = moved(a, nx, ny, rx, ry)
                    if bb is not None:
                        mv += ' - ' + moved(bb, nx, ny, f"({cd['cx']} - {B[bb]['px']})", f"({cd['cy']} - {B[bb]['py']})")
                    q = g.P(f'{gp}q{ci}', f"max(0, {cd['dd']} - {mv})", L2, sg)
                    sgn = '' if a == A_ else '-1 * '
                    qs.append((q, cd, sgn))
                Q = g.P(gp + 'Q', ' + '.join(q for q, _, _ in qs), L2, gate)
                iq = f'(1 / max({Q}, 0.000000001))'
                has = g.P(gp + 'H', f'sign({Q})', L2, gate)
                dbar = g.P(gp + 'D', '(' + ' + '.join(f'{q} * {q}' for q, _, _ in qs) + f') * {iq}', L2, gate)
                pbx = g.P(gp + 'px', '(' + ' + '.join(f"{q} * {cd['cx']}" for q, cd, _ in qs) + f') * {iq}', L2, gate)
                pby = g.P(gp + 'py', '(' + ' + '.join(f"{q} * {cd['cy']}" for q, cd, _ in qs) + f') * {iq}', L2, gate)
                if len(qs) == 1:
                    nx, ny = qs[0][1]['nx'], qs[0][1]['ny']
                    if qs[0][2]:
                        nx, ny = f'(-1 * {nx})', f'(-1 * {ny})'
                else:
                    nbx = '(' + ' + '.join(f"{sg}{q} * {cd['nx']}" for q, cd, sg in qs) + ')'
                    nby = '(' + ' + '.join(f"{sg}{q} * {cd['ny']}" for q, cd, sg in qs) + ')'
                    nl = g.P(gp + 'nl', f'max(hypot({nbx}, {nby}), 0.000000001)', L2, gate)
                    nx = g.P(gp + 'nx', f'{nbx} / {nl}', L2, gate)
                    ny = g.P(gp + 'ny', f'{nby} / {nl}', L2, gate)
                # single reduced contact: push A_ along +n (and Bo along -n)
                Aa = BODIES[A_]
                rax = g.P(gp + 'rx', f"{pbx} - {B[A_]['px']}", L2, gate)
                ray = g.P(gp + 'ry', f"{pby} - {B[A_]['py']}", L2, gate)
                cna = g.P(gp + 'na', f'{rax} * {ny} - {ray} * {nx}', L2, gate)
                cta = f'({rax} * {nx} + {ray} * {ny})'
                vax = f"({B[A_]['u']} - {B[A_]['o']} * {ray})"
                vay = f"({B[A_]['v']} + {B[A_]['o']} * {rax})"
                if Bo is not None:
                    Bb = BODIES[Bo]
                    rbx = g.P(gp + 'qx', f"{pbx} - {B[Bo]['px']}", L2, gate)
                    rby = g.P(gp + 'qy', f"{pby} - {B[Bo]['py']}", L2, gate)
                    cnb = g.P(gp + 'nb', f'{rbx} * {ny} - {rby} * {nx}', L2, gate)
                    ctb = f'({rbx} * {nx} + {rby} * {ny})'
                    # shock propagation: the body lower along gravity acts heavier, so stacks
                    # carry their load in one sweep instead of sagging
                    up = f'(-1 * ({nx} * var(--gx) + {ny} * var(--gy)) / max(hypot(var(--gx), var(--gy)), 1))'
                    sA = g.P(gp + 'sa', f'1 - {f(1 - SHOCK)} * max(0, -1 * {up})', L2, gate)
                    sB = g.P(gp + 'sb', f'1 - {f(1 - SHOCK)} * max(0, {up})', L2, gate)
                    wn = f"({f(Aa['im'])} + {cna} * {cna} * {f(Aa['ii'])}) * {sA} + ({f(Bb['im'])} + {cnb} * {cnb} * {f(Bb['ii'])}) * {sB}"
                    wt = f"({f(Aa['im'])} + {cta} * {cta} * {f(Aa['ii'])}) * {sA} + ({f(Bb['im'])} + {ctb} * {ctb} * {f(Bb['ii'])}) * {sB}"
                    dvx = f"({vax} - ({B[Bo]['u']} - {B[Bo]['o']} * {rby}))"
                    dvy = f"({vay} - ({B[Bo]['v']} + {B[Bo]['o']} * {rbx}))"
                else:
                    sA = None
                    wn = f"{f(Aa['im'])} + {cna} * {cna} * {f(Aa['ii'])}"
                    wt = f"{f(Aa['im'])} + {cta} * {cta} * {f(Aa['ii'])}"
                    dvx, dvy = vax, vay
                wnv = g.P(gp + 'wn', wn, L2, gate)
                vn = g.P(gp + 'vn', f'{dvx} * {nx} + {dvy} * {ny}', L2, gate)
                vt = f'({dvy} * {nx} - {dvx} * {ny})'
                # remove the overlap this step's approach created, plus at most MAXCORR of any
                # older overlap, so deep tangles separate over a few steps instead of popping
                lam = g.P(gp + 'l', f'max(0, min({dbar} - {SLOP}, max(0, -1 * {vn}) * {h} + {MAXCORR})) / {wnv}', L2, gate)
                # restitution folded into the positional impulse: J*h moves the body as if the
                # bounce velocity had been applied; the velocity rederivation picks it up
                bounce = f'{has} * sign(max(0, -1 * {vn} - {BOUNCE_THR}))'
                pn = g.P(gp + 'pn', f'{lam} + {bounce} * {f(E)} * -1 * {vn} / {wnv} * {h}', L2, gate)
                lt = g.P(gp + 'lt', f'{has} * clamp(-{MU} * {pn}, -1 * {vt} * {h} / ({wt}), {MU} * {pn})', L2, gate)
                Px = g.P(gp + 'X', f'{pn} * {nx} - {lt} * {ny}', L2, gate)
                Py = g.P(gp + 'Y', f'{pn} * {ny} + {lt} * {nx}', L2, gate)
                mA = f' * {sA}' if sA else ''
                dsum.setdefault(A_, []).append((
                    f"{Px} * {f(Aa['im'])}{mA}", f"{Py} * {f(Aa['im'])}{mA}",
                    f"({rax} * {Py} - {ray} * {Px}) * {f(Aa['ii'])}{mA}", gate, gp + 'a'))
                if Bo is not None:
                    dsum.setdefault(Bo, []).append((
                        f"-1 * {Px} * {f(Bb['im'])} * {sB}", f"-1 * {Py} * {f(Bb['im'])} * {sB}",
                        f"({rby} * {Px} - {rbx} * {Py}) * {f(Bb['ii'])} * {sB}", gate, gp + 'b'))
            for body, terms in dsum.items():
                dx, dy, da = [], [], []
                for tx, ty, tt, gate, dp in terms:
                    dx.append(g.P(dp + 'x', tx, L2, gate))
                    dy.append(g.P(dp + 'y', ty, L2, gate))
                    da.append(g.P(dp + 't', tt, L2, gate))
                vp = f'{p}v{bi}_{body}'
                vgate = terms[0][3] if len(terms) == 1 else f'{p}nw{body}'
                for fl, dl in (('x', dx), ('y', dy), ('a', da)):
                    g.P(vp + fl, f"{latest(body, fl)} + {' + '.join(dl)}", L2, vgate, syntax='*')
                newver[body] = vp
        for body, vp in newver.items():
            vhist[body].append(vp)

    new = {}
    for i, b in enumerate(BODIES):
        d = B[i]
        for fl in 'xya':
            new[(i, fl)] = g.P(f's{k + 1}{fl}{i}', latest(i, fl), L2)
        new[(i, 'vx')] = g.P(f's{k + 1}vx{i}', f"({new[(i, 'x')]} - {d['X']}) / {h}", L2)
        new[(i, 'vy')] = g.P(f's{k + 1}vy{i}', f"({new[(i, 'y')]} - {d['Y']}) / {h}", L2)
        new[(i, 'w')] = g.P(f's{k + 1}w{i}', f"({new[(i, 'a')]} - {d['A']}) / {h}", L2)
    st = new

# ---- final: gate by live/reset, clamp, wrap angle -------------------------------
LF = 3 * S
for i in range(N):
    for fl in FIELDS:
        lo, hi = RANGES[fl]
        c0 = V(f'{fl.upper()}{i}')
        expr = f'{live} * {st[(i, fl)]} + (1 - {live}) * {c0}'
        if fl == 'a':
            expr = f'mod({expr}, {f(2 * math.pi)})'
        g.P(f'N{fl}{i}', f'var(--rst) * var(--i{fl}{i}) + (1 - var(--rst)) * clamp({lo}, {expr}, {hi})', LF)
g.P('NTP', 'var(--now)', LF)
g.P('NDB', f'clamp(0, {avail} - {consE}, 0.1)', LF)
g.P('NGI', 'var(--rst) * 0 + (1 - var(--rst)) * var(--G)', LF)
g.P('NGX', 'var(--gox)', LF)
g.P('NGY', 'var(--goy)', LF)
NLEV = g.levels

REGS = [('TP', 'NTP', 0, 100), ('DB', 'NDB', 0, 0.1), ('GI', 'NGI', 0, 10), ('GX', 'NGX', -150, 150), ('GY', 'NGY', -150, 150)]
for i in range(N):
    for fl in FIELDS:
        lo, hi = RANGES[fl]
        REGS.append((f'{fl.upper()}{i}', f'N{fl}{i}', lo, hi))

# ---- minimal inheritance: only props read (or used as a gate) below their own level ----
import re as _re
decl_level = {name: lev for lev, gate, name, expr in g.decl}
need = set()
for lev, gate, name, expr in g.decl:
    for ref in _re.findall(r'var\(--([A-Za-z0-9_]+)', expr):
        if ref in decl_level and decl_level[ref] < lev:
            need.add(ref)
    if gate is not None and decl_level.get(gate, -1) < lev - 1:
        need.add(gate)
# consumed by registers/bodies/ring below the last level
for name in list(decl_level):
    if name.startswith('N'):
        need.add(name)
for name, (syn, inh, init) in list(g.props.items()):
    if name in decl_level and name not in need:
        g.props[name] = (syn, False, init)

# ---- emit ----------------------------------------------------------------------
out = []
w = out.append
for name, (syn, inh, init) in g.props.items():
    if syn == '*':
        w(f"@property --{name}{{syntax:'*';inherits:{'true' if inh else 'false'}}}")
    else:
        w(f"@property --{name}{{syntax:'{syn}';inherits:{'true' if inh else 'false'};initial-value:{init}}}")
w('@keyframes clk{from{--now:0}to{--now:100}}')
for ri, (rn, nn, lo, hi) in enumerate(REGS):
    w(f'@keyframes q{ri}{{from{{--{rn}:{f(lo)}}}to{{--{rn}:{f(hi)}}}}}')

names = ['clk'] + [f'q{ri}' for ri in range(len(REGS))]
tl = ['auto'] + [f'--t{ri}' for ri in range(len(REGS))]
w('#L0{')
w(f'timeline-scope:{",".join(tl[1:])};')
w(f'animation-name:{",".join(names)};')
w(f'animation-duration:{",".join(["100s"] + ["auto"] * len(REGS))};')
w(f'animation-iteration-count:{",".join(["infinite"] + ["1"] * len(REGS))};')
w('animation-timing-function:linear;animation-fill-mode:both;')
w(f'animation-timeline:{",".join(tl)};')
w('--TP:var(--now);--DB:0;--GI:0;--GX:0;--GY:0;')
for i in range(N):
    for fl in FIELDS:
        w(f'--{fl.upper()}{i}:var(--i{fl}{i});')
w('}')

blocks = OrderedDict()
for lev, gate, name, expr in g.decl:
    blocks.setdefault((lev, gate), []).append(f'--{name}:calc({expr})')
for (lev, gate), ds in blocks.items():
    rule = f'#L{lev}{{{";".join(ds)}}}'
    w(rule if gate is None else f'@container style(--{gate}: 1){{{rule}}}')


def scene_decls(sn):
    return ';'.join(f'--i{fl}{i}:{f(val)}' for i in range(N) for fl, val in zip(FIELDS, SCENES[sn][i]))


w(f'#app{{--gx:0;--gy:{f(GRAV)};--att:0;--mx:{f(W / 2)};--my:{f(H / 2)};--kick:0;--rst:0;{scene_decls(SCENE_NAMES[0])}}}')
for sn in SCENE_NAMES[1:]:
    w(f'#app:has(#sc-{sn}:checked){{{scene_decls(sn)}}}')
for sn in SCENE_NAMES:   # pressing a scene label loads it at once (the radio flips on mouseup)
    w(f'#app:has(#lb-{sn}:active){{{scene_decls(sn)}}}')
for ri, (rn, nn, lo, hi) in enumerate(REGS):
    w(f'#r{ri}{{view-timeline:--t{ri};top:calc(({HS} - clamp(0, (var(--{nn}) - {f(lo)}) / {f(hi - lo)}, 1) * {HS + 1}) * 1px)}}')
PHYS_CSS = '\n'.join(out)

body_css, body_html = [], []
for i, b in enumerate(BODIES):
    wv, hv = (2 * b['hw'], 2 * b['hh']) if b['k'] == 'box' else (2 * b['r'], 2 * b['r'])
    body_css.append(
        f'#b{i}{{width:calc({wv} * var(--u));height:calc({hv} * var(--u));--c:{b["col"]};'
        f'outline:calc(var(--Neq{i}) * 2px) solid var(--acc);outline-offset:2px;'
        f'transform:translate(calc(var(--Nx{i}) * var(--u) - 50%),calc(var(--Ny{i}) * var(--u) - 50%)) rotate(calc(var(--Na{i}) * 1rad))}}')
    body_html.append(f'<i class="b {"bx" if b["k"] == "box" else "ci"}" id="b{i}"></i>')
reg_html = ''.join(f'<i id="r{ri}"></i>' for ri in range(len(REGS)))

GC, GR = int(os.environ.get("GC", 80)), int(os.environ.get("GR", 50))
grid_css = []
for cx in range(GC):
    grid_css.append(f'#app:has(.gr>i:nth-child({GC}n+{cx + 1}):hover){{--mx:{f((cx + 0.5) * W / GC)}}}')
for ry in range(GR):
    grid_css.append(f'#app:has(.gr>i:nth-child(n+{ry * GC + 1}):nth-child(-n+{(ry + 1) * GC}):hover){{--my:{f((ry + 0.5) * H / GR)}}}')

UI_CSS = open(os.path.join(HERE, 'ui.css')).read()
html = open(os.path.join(HERE, 'page.html')).read()
rep = {
    '/*PHYS*/': PHYS_CSS, '/*UI*/': UI_CSS, '/*GRID*/': '\n'.join(grid_css), '/*BODIES*/': '\n'.join(body_css),
    '<!--NEST_OPEN-->': ''.join(f'<div class="lv" id="L{l}">' for l in range(NLEV)),
    '<!--NEST_CLOSE-->': '</div>' * NLEV,
    '<!--BODIES-->': ''.join(body_html), '<!--REGS-->': reg_html, '<!--GRID-->': '<i></i>' * (GC * GR),
    '<!--SCENES-->': ''.join(
        f'<input type="radio" name="sc" id="sc-{sn}"{" checked" if si == 0 else ""}><label id="lb-{sn}" for="sc-{sn}">{sn}</label>'
        for si, sn in enumerate(SCENE_NAMES)),
    '__GC__': str(GC), '__GR__': str(GR), '__W__': str(W), '__H__': str(H), '__HS__': str(HS),
    '__NPROPS__': f'{len(g.decl):,}', '__S__': str(S), '__NC__': str(NCAND), '__NLEV__': str(NLEV),
}
for a_, b_ in rep.items():
    html = html.replace(a_, b_)
dst = sys.argv[2] if len(sys.argv) > 2 else 'rigid.html'
open(dst, 'w').write(html)
print(f'{dst}: {len(g.decl)} props declared ({sum(1 for d in g.decl if d[1] is None)} ungated), '
      f'{NCAND} candidate contacts x {S} substeps, {NLEV} levels, {len(REGS)} registers, {len(html) // 1024} KB',
      file=sys.stderr)
