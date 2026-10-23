#!/usr/bin/env python3
"""Generator for rigid3d.css: a 3D rigid body physics engine in pure CSS (no JavaScript).

  readback   13 registers per body (position, orientation quaternion, linear and angular velocity, sleep
             counter) read back from layout through view timelines, two per register element (top, left)
  #LS / #LT  the state registers, then the clock and time budget (a sleeping scene restyles nothing below)
  L0         predict (gravity, grab spring, kick), quaternion integration, rotation matrices, broadphase
             flags, neighbourhood digests (decimal words), mouse ray cast on the first pass of a press
  L1         narrowphase for near box pairs: box/box SAT face axes, sphere/box closest point
  batches    one element per Gauss-Seidel batch: the tray planes, then round-robin rounds in which each
             body meets at most one other. A contact's geometry and solve (split impulse, friction,
             torsion, rolling resistance, shock propagation) sit in its round's element; each body's
             running totals (position, rotation and their position-only shares) are inherited props,
             renewed by an alias in the next element after a round that touched the body
  final      the next state and its writeback into the registers' top/left

Every rule that belongs to a body, or to a pair whose lower index is that body, names the container
b<i>; the levels carry that name only while the body is awake or near an awake one, so the rules of a
sleeping neighbourhood are rejected before their style() query is evaluated.

Usage: gen3d.py [engine.json]   (NBOX/NSPH bodies, SCENE=name picks the scene that loads first)
"""
import json, math, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simp import simplify as _simplify
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py'))
import csslabel as lbl     # section and group comments in the output (../../shared/README.md#labels-in-generated-css)
SIMPLIFY = os.environ.get('SIMPLIFY', '1') == '1'
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
HS = 1_000_000          # register scroller height (CSS px); keep << 33.5M / DPR
STEP = 1 / float(os.environ.get("RATE", 90))   # 1/60 lets stacks sink; 1/120 is stiffer but slower
GRAV = 1600.0
MU = 0.5
E = 0.35
BOUNCE_THR = 220.0
LIN_DAMP = 0.05
ANG_DAMP = float(os.environ.get("ANG_DAMP", 0.35))
SLOP = 0.3
MAXCORR = float(os.environ.get("MAXCORR", 1.0))
MARGIN = 3.0
REF_TOL = 1.0
SKIN = 0.5
SHOCK = 0.1
ROLL = float(os.environ.get('ROLL', 0.06))   # rolling resistance arm, as a fraction of the radius
ROLLB = float(os.environ.get('ROLLB', 0))
PATCHW = os.environ.get('PATCHW', 'soft')      # box/plane patch: 'soft' (one contact), 'even' or 'depth' (8 corners)
PATCHB = os.environ.get('PATCHB', 'corners')   # box/box: 'corners' (clipped incident corners) or 'soft'
PATCHC = float(os.environ.get('PATCHC', 1.0))  # 'even': weight = depth + PATCHC for penetrating corners  # same for boxes, as a fraction of the smallest half extent
DENS = 0.00001

# tray: floor y = 0 (y points down, as in CSS), walls at x = +-WX, z = +-WZ, ceiling y = -CEIL
# (TRAY scales the floor for big sparse scenes; the camera doesn't follow, so it's for benchmarks)
TRAY = float(os.environ.get('TRAY', 1))
WX, WZ, CEIL = int(280 * TRAY), int(180 * TRAY), 280   # ceiling at the top edge of the default view
# contact groups per body against the tray: floor and ceiling as fixed planes, and the two
# opposite walls of each axis as ONE group whose normal faces away from the nearer wall
# (a body can't touch both at once): 4 groups instead of 6
WALLS = {'X': 0, 'Z': 2}
PLANES = {  # name: (normal into the tray, point on plane)
    'F': ((0, -1, 0), (0, 0, 0)), 'C': ((0, 1, 0), (0, -CEIL, 0)),
    'L': ((1, 0, 0), (-WX, 0, 0)), 'R': ((-1, 0, 0), (WX, 0, 0)),
    'B': ((0, 0, 1), (0, 0, -WZ)), 'N': ((0, 0, -1), (0, 0, WZ)),
}

# camera (must match the CSS transform on .cam exactly; picking unprojects through it)
VIEW_W, VIEW_H = 900, 560
PERSP = 1500.0
TILT = -28.0            # degrees, rotateX
CAM_TY = 95.0           # translateY, world units
CAM_DIST = -260.0       # translateZ(-DIST); negative pulls the camera in

BODIES = [
    dict(k='box', h=(25, 25, 25), col='#f2b134'),
    dict(k='box', h=(25, 25, 25), col='#ed6a5a'),
    dict(k='box', h=(36, 18, 18), col='#9b8cff'),
    dict(k='box', h=(62, 9, 32), col='#d6d3cc', dens=0.6),
    dict(k='sph', r=28, col='#5aa9e6'),
    dict(k='sph', r=22, col='#ff8fb1'),
    dict(k='sph', r=18, col='#7bd389'),
    dict(k='sph', r=24, col='#ff9f43'),
]
# BODIES_JSON=file replaces the 8 hand-made bodies (4 boxes, then 4 spheres) and, with "scenes", the hand-placed
# scenes: {"bodies": [{"k": "box", "h": [hx, hy, hz], "col": "#rgb"}, {"k": "sph", "r": r, …}, …],
# "scenes": {"name": [{"p": [x, y, z], "rot": […], "v": […], "w": […]}, …]}} (experiments/widgets)
_BJ = json.load(open(os.environ['BODIES_JSON'])) if os.environ.get('BODIES_JSON') else {}
if 'bodies' in _BJ:
    BODIES = _BJ['bodies']
# extra bodies (NBOX / NSPH environment knobs) for scaling tests and bigger scenes
_XBOX = [((20, 20, 20), '#e9c46a'), ((30, 15, 15), '#2a9d8f'), ((22, 22, 22), '#f4a261'), ((40, 10, 20), '#8ecae6'),
         ((18, 18, 18), '#e76f51'), ((26, 13, 26), '#b5838d'), ((24, 24, 24), '#90be6d'), ((34, 12, 17), '#c3aed6')]
_XSPH = [(20, '#43aa8b'), (16, '#f9c74f'), (26, '#577590'), (14, '#f94144'), (21, '#f8961e'), (18, '#9d4edd'),
         (23, '#4cc9f0'), (15, '#ffafcc')]
for j in range(int(os.environ.get('NBOX', 8)) - 4):
    hh_, c_ = _XBOX[j % len(_XBOX)]
    BODIES.insert(4 + j, dict(k='box', h=hh_, col=c_))
for j in range(int(os.environ.get('NSPH', 8)) - 4):
    r_, c_ = _XSPH[j % len(_XSPH)]
    BODIES.append(dict(k='sph', r=r_, col=c_))
N = len(BODIES)
for b in BODIES:
    d = DENS * b.get('dens', 1)
    if b['k'] == 'box':
        hx, hy, hz = b['h']
        b['m'] = d * 8 * hx * hy * hz
        b['I'] = (b['m'] / 3 * (hy * hy + hz * hz), b['m'] / 3 * (hx * hx + hz * hz), b['m'] / 3 * (hx * hx + hy * hy))
        b['R'] = math.sqrt(hx * hx + hy * hy + hz * hz)
    else:
        b['m'] = d * 4 / 3 * math.pi * b['r'] ** 3
        b['I'] = (0.4 * b['m'] * b['r'] ** 2,) * 3
        b['R'] = b['r']
    b['im'] = 1 / b['m']
    b['ii'] = tuple(1 / v for v in b['I'])



def quat(ax=0.0, ay=0.0, az=0.0):
    """quaternion (w, x, y, z) for intrinsic rotations x, then y, then z (radians)"""
    def q(axis, a):
        s = math.sin(a / 2)
        return (math.cos(a / 2), axis[0] * s, axis[1] * s, axis[2] * s)
    def mul(a, b):
        aw, ax_, ay_, az_ = a; bw, bx, by, bz = b
        return (aw * bw - ax_ * bx - ay_ * by - az_ * bz, aw * bx + ax_ * bw + ay_ * bz - az_ * by,
                aw * by - ax_ * bz + ay_ * bw + az_ * bx, aw * bz + ax_ * by - ay_ * bx + az_ * bw)
    return mul(mul(q((0, 0, 1), az), q((0, 1, 0), ay)), q((1, 0, 0), ax))


def S(x, y, z, rot=(0, 0, 0), v=(0, 0, 0), w=(0, 0, 0)):
    return (x, y, z) + quat(*rot) + tuple(v) + tuple(w)


SCENES = {
    'tower': [
        S(70, -25, 10), S(70, -75, 10, (0, 0.5, 0)), S(70, -118, 10, (0, 0.2, 0)), S(70, -145, 10, (0, -0.15, 0)),
        S(-220, -28, 40, v=(520, 0, -60)), S(-240, -22, -90, v=(430, 0, 110)), S(-160, -240, 70, v=(320, 0, -70)),
        S(230, -24, 130, v=(-320, 0, -260)),
    ],
    'rain': [
        S(-120, -200, -40, (0.4, 0.3, 0.9), w=(3, -2, 4)), S(-20, -255, 30, (1.1, 0.2, 0.5), w=(-4, 2, 1)),
        S(80, -225, -20, (0.2, 1.3, 0.7), w=(2, 5, -2)), S(30, -120, 10, (0.3, 0.6, 0.2), w=(1, -3, 2)),
        S(-180, -150, 80, v=(120, 0, -60)), S(150, -230, -90, v=(-100, 0, 50)), S(190, -100, 100),
        S(-60, -250, -100, v=(40, 0, 80)),
    ],
    'calm': [
        S(-200, -25, -60, (0, 0.3, 0)), S(-60, -25, 60, (0, 0.9, 0)), S(80, -18, -60, (0, 0.5, 0)), S(150, -9, 80, (0, 0.2, 0)),
        S(-200, -28, 100), S(0, -22, -120), S(220, -18, -120), S(240, -24, 40),
    ],
    'pair': [
        S(0, -25, 0), S(-200, -25, 100), S(-200, -18, -100), S(150, -9, 100),
        S(52, -28, 0), S(200, -22, -120), S(220, -18, 0), S(-60, -24, -120),
    ],
    'stack': [
        S(-60, -25, 0), S(-60, -75, 0), S(-60, -118, 0), S(-60, -145, 0),
        S(-200, -28, -100), S(120, -22, 60), S(200, -18, -80), S(60, -24, -120),
    ],
    'field': [],    # every body at rest on the floor, shelf-packed (the sparse-regime benchmark scene)
}
for _k, _v in _BJ.get('scenes', {}).items():
    SCENES[_k] = [S(*o['p'], o.get('rot', (0, 0, 0)), o.get('v', (0, 0, 0)), o.get('w', (0, 0, 0))) for o in _v]
import random as _rnd


def _field():
    """shelf-pack all bodies on the floor, axis-aligned, so the whole scene starts asleep; what doesn't
    fit is dropped from just above the pile"""
    fp = []
    for i, b in enumerate(BODIES):
        w, d, hgt = (2 * b['h'][0], 2 * b['h'][2], b['h'][1]) if b['k'] == 'box' else (2 * b['r'],) * 2 + (b['r'],)
        fp.append((i, w, d, hgt))
    fp.sort(key=lambda t: -t[2])
    GAP = float(os.environ.get('FIELD_GAP', 6))
    res = [None] * N
    x, z, rowd = -WX + GAP, -WZ + GAP, 0
    rest = []
    for i, w, d, hgt in fp:
        if x + w > WX - GAP:
            x, z, rowd = -WX + GAP, z + rowd + GAP, 0
        if z + d > WZ - GAP:
            rest.append((i, w, d, hgt)); continue
        res[i] = S(x + w / 2, -hgt, z + d / 2)
        x += w + GAP; rowd = max(rowd, d)
    rng = _rnd.Random(11)
    for k, (i, w, d, hgt) in enumerate(rest):
        res[i] = S(rng.uniform(-WX + w, WX - w), -90 - 70 * (k // 12), rng.uniform(-WZ + d, WZ - d))
    return res


def _extend(scene, name):
    """place bodies beyond the hand-made 8: resting on a non-overlapping grid clear of the hand-placed
    ones; once the floor is full, further layers are dropped from a little above, offset by half a
    cell ('rain' drops everything from random heights)"""
    if name == 'field':
        return _field()
    rng = _rnd.Random(7 + len(name))
    base = list(scene)
    order = [i for i, b in enumerate(BODIES) if b['k'] == 'box'] + [i for i, b in enumerate(BODIES) if b['k'] == 'sph']
    hand_box, hand_sph = base[:4], base[4:]
    res = [None] * N
    bi = si = 0
    SP = 66
    xs = [-231 + SP * c for c in range(8)]
    zs = [-132 + SP * r for r in range(5)]
    layer0 = [(x, z) for z in zs for x in xs]
    if name != 'rain':     # keep clear of the hand-placed bodies
        layer0 = [(x, z) for x, z in layer0 if all(math.hypot(x - b_[0], z - b_[2]) > 75 for b_ in base)]
    rng.shuffle(layer0)
    up = [(x + SP / 2, z + SP / 2) for z in zs[:-1] for x in xs[:-1]]
    rng.shuffle(up)
    slots = [(x, z, 0) for x, z in layer0] + [(x, z, 1 + k // len(up)) for k in range(4 * len(up)) for x, z in [up[k % len(up)]]]
    rslots = [(x, z) for z in (-120, -40, 40, 120) for x in (-220, -150, -80, 80, 150, 220)]
    _rnd.Random(7 + len(name)).shuffle(rslots)
    k = 0
    for i in order:
        b = BODIES[i]
        if b['k'] == 'box' and bi < 4:
            res[i] = hand_box[bi]; bi += 1; continue
        if b['k'] == 'sph' and si < 4:
            res[i] = hand_sph[si]; si += 1; continue
        if name == 'rain':
            # the original 24 drop columns; beyond those, a second set offset by half a column, higher up
            x, z = rslots[k % len(rslots)]
            if k >= len(rslots):
                x, z = x + 35, z + 40
            hgt = -60 - 190 * rng.random() if k < len(rslots) else -120 - 140 * rng.random()
            k += 1
            res[i] = S(x * 0.8, hgt, z * 0.8, (rng.random() * 3, rng.random() * 3, rng.random() * 3),
                       w=(rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-3, 3)))
            continue
        x, z, lay = slots[k]; k += 1
        if False:
            pass
        else:
            hy = b['h'][1] if b['k'] == 'box' else b['r']
            res[i] = S(x, -hy - 75 * lay, z, (0, rng.random(), 0))
    return res


SCENES = {k: _extend(v, k) for k, v in SCENES.items()}
if os.environ.get('SCENE'):
    k0 = os.environ['SCENE']
    SCENES = {k0: SCENES[k0], **{k: v for k, v in SCENES.items() if k != k0}}
SCENE_NAMES = [k for k in SCENES if k in os.environ.get('SCENE_LIST', 'tower,rain,stack').split(',') or k == os.environ.get('SCENE')]

FIELDS = ['x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'vx', 'vy', 'vz', 'wx', 'wy', 'wz']
RANGES = dict(x=(-420, 420), y=(-760, 200), z=(-420, 420), qw=(-1, 1), qx=(-1, 1), qy=(-1, 1), qz=(-1, 1),
              vx=(-5000, 5000), vy=(-5000, 5000), vz=(-5000, 5000), wx=(-150, 150), wy=(-150, 150), wz=(-150, 150))


def f(v):
    if isinstance(v, str):
        return v
    s = repr(round(float(v), 9))
    return s[:-2] if s.endswith('.0') else s


class Gen:
    def __init__(self):
        self.props = OrderedDict()
        self.decl = []
        self.levels = 0

    def reg(self, name, inherits=True, syntax='<number>', init='0'):
        assert name not in self.props, name
        self.props[name] = (syntax, inherits, init)
        return f'var(--{name})'

    def P(self, name, expr, level, gate=None, syntax='<number>'):
        v = self.reg(name, True, syntax)
        self.decl.append((level, gate, name, expr))
        self.levels = max(self.levels, level + 1)
        return v

    def P3(self, name, exprs, level, gate=None):
        return tuple(self.P(name + c, e, level, gate) for c, e in zip('xyz', exprs))

    def A(self, name, expr, level, gate):
        """an alternative declaration of an already registered property under another gate"""
        assert name in self.props, name
        self.decl.append((level, gate, name, expr))


g = Gen()
V = lambda n: f'var(--{n})'


_ALIAS = re.compile(r'^\(?(-?\d+(\.\d+)?(e-?\d+)?|(-1 \* )?var\(--[A-Za-z0-9_]+\))\)?$')


def PE(name, expr, lev, gate, syntax='<number>'):
    """a prop, unless the expression simplifies to a constant or a plain (negated) alias"""
    s_ = _simplify(expr)
    if _ALIAS.match(s_):
        return s_ if ' ' not in s_ else f'({s_})'
    return g.P(name, expr, lev, gate, syntax)


def P3E(name, exprs, lev, gate):
    return tuple(PE(name + c, e, lev, gate) for c, e in zip('xyz', exprs))




# ---- small vector algebra on expression strings ------------------------------------
def is0(e):
    return e in ('0', '-0', '0.0')


def mul(a, b):
    if is0(a) or is0(b):
        return '0'
    if a == '1':
        return b
    if b == '1':
        return a
    if a == '-1':
        return f'(-1 * {b})'
    if b == '-1':
        return f'(-1 * {a})'
    return f'{a} * {b}'


def add(*ts):
    ts = [t for t in ts if not is0(t)]
    return '(' + ' + '.join(ts) + ')' if ts else '0'


def sub(a, b):
    if is0(b):
        return a
    if is0(a):
        return f'(-1 * {b})'
    return f'({a} - {b})'


def dot(a, b):
    return add(*(mul(x, y) for x, y in zip(a, b)))


def cross(a, b):
    return (sub(mul(a[1], b[2]), mul(a[2], b[1])), sub(mul(a[2], b[0]), mul(a[0], b[2])),
            sub(mul(a[0], b[1]), mul(a[1], b[0])))


def vsub(a, b):
    return tuple(sub(x, y) for x, y in zip(a, b))


def vscale(a, s):
    return tuple(mul(x, s) for x in a)


def num3(v):
    return tuple(f(x) for x in v)


# ---- time ----------------------------------------------------------------------
# Everything that changes every pass even when the whole scene sleeps (the clock, the time
# registers, the pointer, the camera yaw) is kept NON-inherited on #LS, or zeroed there: then a
# sleeping scene leaves the solver levels' inherited data unchanged and they aren't restyled.
g.reg('now', inherits=False)
for c in ['gy', 'att', 'sx', 'sy', 'kick', 'rst', 'sxg', 'syg', 'yawg', 'tk', 'tm', 'tdx', 'tdy', 'tgi', 'tdxg', 'tdyg', 'tgig', 'held']:
    g.reg(c)
for c in ['tgx', 'tgy', 'fox', 'foy']:   # touch input, on #TI only
    g.reg(c, inherits=False)
for i in range(N):
    for fl in FIELDS:
        g.reg(f'i{fl}{i}')
        g.reg(f'{fl.upper()}{i}')
TP, DB = g.reg('TP', inherits=False), g.reg('DB', inherits=False)
for _n in ('raw', 'avail', 'consE', 'NTP', 'NDB'):
    g.reg(_n, inherits=False)
live = g.reg('live', inherits=False, syntax='<integer>')   # used on #LS only: the levels see ac/as
g.reg('any', syntax='<integer>')
FFQ = os.environ.get('FFQ', '1') == '1'   # Firefox-only rules: the re-match clock (see #LM below) and the names
if FFQ:
    g.reg('ffk')
g.reg('mix', syntax='<integer>')
g.reg('anyrd', syntax='<integer>')
g.reg('GIr', syntax='<integer>')
g.reg('pick', syntax='<integer>')
g.reg('tpk', syntax='<integer>')
g.reg('tho', syntax='<integer>')
# sleeping: a body still for SLEEP_K passes stops being simulated until something wakes it
SLEEP_K = int(os.environ.get('SLEEP_K', 45))
SLEEP_DX, SLEEP_DA = 0.03, 0.0008
GYP = g.reg('GYP')
for i in range(N):
    g.reg(f'SC{i}')
    g.reg(f'aw{i}', syntax='<integer>')
    g.reg(f'ac{i}', syntax='<integer>')   # awake and this pass advances time: simulate
    g.reg(f'as{i}', syntax='<integer>')   # asleep and this pass advances time: wake checks only
    g.reg(f'rd{i}', syntax='<integer>')   # ready: still for K passes, awake
    g.reg(f'mf{i}', syntax='<integer>')   # moving: stillness count just reset
    g.reg(f'nr{i}', syntax='<integer>')   # not ready
AW = lambda i, v=1: (f'ac{i}', v)
AS = lambda i: (f'as{i}', 1)
LS_TIME = (f'--raw:calc(mod(var(--now) - var(--TP) + 100, 100));--avail:calc(min(var(--DB) + var(--raw), 0.05));'
           f'--live:calc(sign(max(0, var(--avail) - {f(STEP * 0.5)})));--consE:calc(var(--live) * {f(STEP)});'
           f'--NTP:var(--now);--NDB:calc(clamp(0, var(--avail) - var(--consE), 0.1));--tk:calc(var(--now) * var(--kick));'
           f'--sx:0;--sy:0;--yaw:0;')
h = f(STEP)
L0, L1, LC, L2, LF = 0, 1, 1, 2, 3   # (LC: formerly a separate level for box/box corner tests)

cur = {i: {fl: V(f'{fl.upper()}{i}') for fl in FIELDS} for i in range(N)}

# ---- mouse ray (L0, only while pressed) -----------------------------------------
AT = 'att'
GI, GOX, GOY, GOZ, GT = (g.reg(n) for n in ('GI', 'GOX', 'GOY', 'GOZ', 'GT'))
ct, st_ = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
cyw = g.P('cyw', 'cos(var(--yawg))', 0, AT)
syw = g.P('syw', 'sin(var(--yawg))', 0, AT)
# camera space: eye (0,0,PERSP), dir (sx, sy, -PERSP); undo translate, then rotateX(-t), rotateY(-yaw)
oc = (0.0, -CAM_TY, PERSP + CAM_DIST)
o_y = oc[1] * ct + oc[2] * st_
o_z1 = -oc[1] * st_ + oc[2] * ct
d_y = f"(var(--syg) * {f(ct)} + {f(-PERSP * st_)})"
d_z1 = f"(-1 * var(--syg) * {f(st_)} + {f(-PERSP * ct)})"
RO = g.P3('ro', (f'-1 * {f(o_z1)} * {syw}', f(o_y), f'{f(o_z1)} * {cyw}'), 0, AT)
RD = g.P3('rd', (f'var(--sxg) * {cyw} - {d_z1} * {syw}', d_y, f'var(--sxg) * {syw} + {d_z1} * {cyw}'), 0, AT)

# ---- predict + rotation matrices + broadphase (L0) ------------------------------
B = {}
for i, b in enumerate(BODIES):
    c = cur[i]
    kx = f'2600 * sin(var(--tk) * 23 + {f(i * 2.1)})'
    kz = f'2600 * cos(var(--tk) * 19 + {f(i * 1.3)})'
    damp = f'(1 - {LIN_DAMP} * {h})'
    # the cheap common case; grabbing (att) and shaking (kick) declare fuller alternatives in
    # blocks that come later in the cascade
    acc0 = ('0', 'var(--gy)', '0')
    accG = ('var(--gax)', 'var(--gy) + var(--gay)', 'var(--gaz)')
    accK = (kx, 'var(--gy) - 2600', kz)
    vexp = lambda acc: tuple(f"({c['v' + a]} + ({e}) * {h}) * {damp}" if not is0(e) else f"{c['v' + a]} * {damp}"
                             for a, e in zip('xyz', acc))
    vel = g.P3(f'u{i}', vexp(acc0), L0, AW(i))
    for a, e in zip('xyz', vexp(accG)):
        g.A(f'u{i}{a}', e, L0, ('GIr', i + 1))
    for a, e in zip('xyz', vexp(accK)):
        g.A(f'u{i}{a}', e, L0, ('kick', 1))
    om = g.P3(f'o{i}', tuple(f"{c['w' + a]} * {f(1 - ANG_DAMP * STEP)}" for a in 'xyz'), L0, AW(i))
    for a in 'xyz':
        g.A(f'o{i}{a}', f"({c['w' + a]} + var(--gal{a}) * {h}) * {f(1 - (ANG_DAMP + 3) * STEP)}", L0, ('GIr', i + 1))
    pos = g.P3(f'p{i}', tuple(f"{c[a]} + {v} * {h}" for a, v in zip('xyz', vel)), L0, AW(i))
    for a in 'xyz':
        g.A(f'p{i}{a}', c[a], L0, AW(i, 0))
    qw, qx, qy, qz = c['qw'], c['qx'], c['qy'], c['qz']
    wx, wy, wz = om
    hh = f(0.5 * STEP)
    qn = (f'{qw} - {hh} * ({wx} * {qx} + {wy} * {qy} + {wz} * {qz})',
          f'{qx} + {hh} * ({qw} * {wx} + {wy} * {qz} - {wz} * {qy})',
          f'{qy} + {hh} * ({qw} * {wy} + {wz} * {qx} - {wx} * {qz})',
          f'{qz} + {hh} * ({qw} * {wz} + {wx} * {qy} - {wy} * {qx})')
    # predicted orientation is left unnormalized (the final one is normalized); box rotation
    # matrices divide by |q|^2 instead
    if b['k'] == 'box':
        q = [g.P(f'q{i}{k}', e, L0, AW(i)) for k, e in zip('wxyz', qn)]
        for k in 'wxyz':
            g.A(f'q{i}{k}', c['q' + k], L0, AW(i, 0))
    else:
        q = None    # a sphere's orientation never enters a collision: integrate once at the end
    d = dict(v=vel, o=om, p=pos, q=q, X=tuple(c[a] for a in 'xyz'))
    if b['k'] == 'box':
        w_, x_, y_, z_ = q
        il = g.P(f'il{i}', f'2 / ({w_} * {w_} + {x_} * {x_} + {y_} * {y_} + {z_} * {z_})', L0, AW(i))
        R = [[f'1 - {il} * ({y_} * {y_} + {z_} * {z_})', f'{il} * ({x_} * {y_} - {z_} * {w_})', f'{il} * ({x_} * {z_} + {y_} * {w_})'],
             [f'{il} * ({x_} * {y_} + {z_} * {w_})', f'1 - {il} * ({x_} * {x_} + {z_} * {z_})', f'{il} * ({y_} * {z_} - {x_} * {w_})'],
             [f'{il} * ({x_} * {z_} - {y_} * {w_})', f'{il} * ({y_} * {z_} + {x_} * {w_})', f'1 - {il} * ({x_} * {x_} + {y_} * {y_})']]
        Rv = [[g.P(f'R{i}{r}{cc}', R[r][cc], L0, AW(i)) for cc in range(3)] for r in range(3)]
        for r in range(3):
            for cc in range(3):
                g.A(f'R{i}{r}{cc}', R[r][cc], L1, f'nb{i}')
        g.A(f'il{i}', f'2 / ({w_} * {w_} + {x_} * {x_} + {y_} * {y_} + {z_} * {z_})', L1, f'nb{i}')
        d['col'] = [tuple(Rv[r][k] for r in range(3)) for k in range(3)]   # body axes in world
    B[i] = d

boxes = [i for i, b in enumerate(BODIES) if b['k'] == 'box']
CORN = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

groups = []
for i in range(N):
    for pl in ('F', 'C', 'X', 'Z'):
        groups.append(dict(id=f'w{i}{pl}', a=i, b=None, plane=pl))
for x in range(N):
    for y in range(x + 1, N):
        groups.append(dict(id=f'p{x}_{y}', a=x, b=y, plane=None))

for gr in groups:
    a, bb, pl = gr['a'], gr['b'], gr['plane']
    Ra = BODIES[a]['R']
    gr['l0touch'] = False
    if pl:
        # planes: the exact touch test is cheap (support of a box along n), so the broadphase flag
        # is the touch flag and there is no narrowphase block at all
        if pl in WALLS:
            ax_ = WALLS[pl]
            half = WX if pl == 'X' else WZ
            d0 = f"(abs({B[a]['p'][ax_]}) - {half})"
        else:
            n, P0 = PLANES[pl]
            d0 = dot(num3(n), vsub(num3(P0), B[a]['p']))
            ax_ = [k for k in range(3) if n[k]][0]
        if BODIES[a]['k'] == 'box':
            e = add(d0, *(mul(f(BODIES[a]['h'][k]), f"abs({B[a]['col'][k][ax_]})") for k in range(3)))
        else:
            e = add(f(BODIES[a]['r']), d0)
        gr['l0touch'] = True
    elif BODIES[a]['k'] == 'sph' and BODIES[bb]['k'] == 'sph':
        dv = vsub(B[a]['p'], B[bb]['p'])
        e = f"{f(BODIES[a]['r'] + BODIES[bb]['r'])} - hypot({', '.join(dv)})"
        gr['l0touch'] = True
    else:
        rr = Ra + BODIES[bb]['R'] + MARGIN
        dv = vsub(B[a]['p'], B[bb]['p'])
        e = f"{f(rr)} - hypot({', '.join(dv)})"
    gr['flag'] = f'n{gr["id"]}'
    g.P(gr['flag'], f'sign(max(0, {e}))', L0, AW(a), syntax='<integer>')
    if not pl:
        g.A(gr['flag'], f'sign(max(0, {e}))', L0, AW(bb))
# Neighbourhood digests. Each awake body j sums its near flags into decimal words (body i is digit
# i % 6 of word i // 6; a registered number survives var() with 6 significant digits, so a word holds
# six bodies, each counting up to 9 awake neighbours). Summing the words over all bodies (asleep ones
# contribute nothing: their words are undeclared) tells every body at once whether an awake body is
# near it, whether a moving one is, and whether one that isn't ready to sleep is: one digit each
# instead of a sum over every possible partner per body.
NW = (N + 5) // 6
pflag = {(gr['a'], gr['b']): gr['flag'] for gr in groups if not gr['plane']}
fl_ = lambda i, j: V(pflag[(min(i, j), max(i, j))])
for j in range(N):
    for m in range(NW):
        terms = [mul(fl_(i, j), str(10 ** (i % 6))) for i in range(6 * m, min(N, 6 * m + 6)) if i != j]
        if terms:
            g.P(f'nm{j}_{m}', ' + '.join(terms), L0, AW(j))
for m in range(NW):
    ws = [V(f'nm{j}_{m}') for j in range(N) if (f'nm{j}_{m}') in g.props]
    g.P(f'SN{m}', ' + '.join(ws), L0, ('mix', 1))
    g.P(f'SP{m}', ' + '.join(f'{w} * var(--mf{j})' for j, w in zip([j for j in range(N) if f'nm{j}_{m}' in g.props], ws)), L0, ('mix', 1))
    g.P(f'SB{m}', ' + '.join(f'{w} * var(--nr{j})' for j, w in zip([j for j in range(N) if f'nm{j}_{m}' in g.props], ws)), L0, ('anyrd', 1))
dig = lambda S, i: f'sign(mod(round(down, var(--{S}{i // 6}) / {10 ** (i % 6)}), 10))'
for i in range(N):
    g.P(f'pk{i}', dig('SP', i), L0, AS(i), syntax='<integer>')    # asleep, near a body that is moving
    g.P(f'bk{i}', dig('SB', i), L0, (f'rd{i}', 1), syntax='<integer>')   # ready, touching one that isn't
    g.P(f'nb{i}', dig('SN', i), L0, AS(i), syntax='<integer>')   # asleep, near an awake body (all-pairs digest)

# ---- grab (L0, gated on the pointer being down) ----------------------------------
# Two phases. Picking (pointer down, nothing held yet: --pick at #LS) ray-casts every body once and
# latches the hit (GI = body, GT = ray parameter, GO = offset in the body's frame). Holding (GIr > 0)
# only reads the held body's state, through blocks gated on its index: no per-body work at all.
GRAB_K, GRAB_C, GRAB_AMAX = 1400.0, 55.0, 40000.0
PK = ('pick', 1)
# rotation of the CURRENT state (not the predicted one: that depends on the grab torque,
# which would make a dependency cycle and invalidate the whole chain)
def rot_of(w_, x_, y_, z_):
    return [[f'1 - 2 * ({y_} * {y_} + {z_} * {z_})', f'2 * ({x_} * {y_} - {z_} * {w_})', f'2 * ({x_} * {z_} + {y_} * {w_})'],
            [f'2 * ({x_} * {y_} + {z_} * {w_})', f'1 - 2 * ({x_} * {x_} + {z_} * {z_})', f'2 * ({y_} * {z_} - {x_} * {w_})'],
            [f'2 * ({x_} * {z_} - {y_} * {w_})', f'2 * ({y_} * {z_} + {x_} * {w_})', f'1 - 2 * ({x_} * {x_} + {y_} * {y_})']]
CC = {}
for i in boxes:
    R = rot_of(*(cur[i][k] for k in ('qw', 'qx', 'qy', 'qz')))
    Rv = [[g.P(f'gR{i}{r}{c}', R[r][c], 0, PK) for c in range(3)] for r in range(3)]
    CC[i] = [tuple(Rv[r][k] for r in range(3)) for k in range(3)]
tvals = []
for i, b in enumerate(BODIES):
    c = cur[i]
    pc = tuple(c[a] for a in 'xyz')
    if b['k'] == 'sph':
        oc_ = vsub(RO, pc)
        bq = g.P(f'gb{i}', dot(oc_, RD), 0, PK)
        dd = dot(RD, RD)
        cc = f"{dot(oc_, oc_)} - {f(b['r'] ** 2)}"
        disc = g.P(f'gd{i}', f'{bq} * {bq} - {dd} * ({cc})', 0, PK)
        t = f'(-1 * {bq} - sqrt(max({disc}, 0))) / {dd}'
        hit = f'sign(max(0, {disc})) * sign(max(0, {t}))'
        tv = g.P(f'gt{i}', f'{hit} * {t} + (1 - {hit}) * 1000000000', 0, PK)
    else:
        col = CC[i]
        rel = vsub(RO, pc)
        ol = [g.P(f'go{i}{k}', dot(col[k], rel), 0, PK) for k in range(3)]
        dl = [g.P(f'gq{i}{k}', dot(col[k], RD), 0, PK) for k in range(3)]
        ts1, ts2 = [], []
        for k in range(3):
            hk = b['h'][k]
            ds = f'(max(abs({dl[k]}), 0.000000001) * (sign({dl[k]}) + 1 - abs(sign({dl[k]}))))'
            t1 = g.P(f'gs{i}{k}', f'({-hk} - {ol[k]}) / {ds}', 0, PK)
            t2 = g.P(f'ge{i}{k}', f'({hk} - {ol[k]}) / {ds}', 0, PK)
            ts1.append(f'min({t1}, {t2})'); ts2.append(f'max({t1}, {t2})')
        tn = g.P(f'gn{i}', f"max({', '.join(ts1)})", 0, PK)
        tf = g.P(f'gf{i}', f"min({', '.join(ts2)})", 0, PK)
        hit = f'sign(max(0, {tf} - {tn})) * sign(max(0, {tn}))'
        tv = g.P(f'gt{i}', f'{hit} * {tn} + (1 - {hit}) * 1000000000', 0, PK)
    tvals.append(tv)
tmin = g.P('gtm', f"min({', '.join(tvals)})", 0, PK)
anyhit = f'sign(max(0, 100000000 - {tmin}))'
pick = g.P('gpick', f"{anyhit} * (" + ' + '.join(f'{i + 1} * sign(max(0, {tmin} + 0.001 - {t}))' for i, t in enumerate(tvals)) + ')', 0, PK)
# a press that hits nothing latches N + 1 ("missed") so the ray isn't cast again until release
G = g.P('G', f'var(--GIr) + (1 - sign(var(--GIr))) * ({pick} + (1 - sign({pick})) * {N + 1})', 0, AT)
eqs = [g.P(f'eq{i}', f'1 - min(1, abs({pick} - {i + 1}))', 0, PK) for i in range(N)]
# Touch (--tm: 1, ARCHITECTURE.md "Touch"): the body comes from the handle the finger is on (--tgig = index + 1, never
# 0 while att is 1), and the latched "offset" GO is the body's centre in world coordinates, the anchor the drag is added
# to. No ray is cast: --pick is 0 in touch mode, --tpk replaces it.
TPK, THO = ('tpk', 1), ('tho', 1)
g.A('gpick', 'var(--tgig)', 0, TPK)
for i in range(N):
    g.A(f'eq{i}', f'1 - min(1, abs({pick} - {i + 1}))', 0, TPK)
sel = lambda terms: add(*(mul(e, t) for e, t in zip(eqs, terms) if not is0(t)))
# the pick pass latches where the ray hit and the hit point in the body's frame
tG = g.P('gtG', GT, 0, AT)
g.A('gtG', sel(tvals), 0, PK)
hitp = tuple(add(r, mul(tG, dv)) for r, dv in zip(RO, RD))
pGp = tuple(sel([cur[i][a] for i in range(N)]) for a in 'xyz')
colGp = [tuple(sel([CC[i][k][r] if BODIES[i]['k'] == 'box' else '0' for i in range(N)]) for r in range(3)) for k in range(3)]
isboxp = sel(['1' if b['k'] == 'box' else '0' for b in BODIES])
off = [g.P(f'gof{k}', prev, 0, AT) for k, prev in enumerate((GOX, GOY, GOZ))]
for k in range(3):
    g.A(f'gof{k}', f'{isboxp} * {dot(colGp[k], vsub(hitp, pGp))}', 0, PK)
    g.A(f'gof{k}', pGp[k], 0, TPK)
# holding: the held body's state, declared by the one block whose index matches
HOLD = ['gpx', 'gpy', 'gpz', 'gqw', 'gqx', 'gqy', 'gqz', 'gvx', 'gvy', 'gvz', 'gwx', 'gwy', 'gwz', 'gim', 'gii0', 'gii1', 'gii2', 'giso', 'gimx']
for i, b in enumerate(BODIES):
    c = cur[i]
    vals = [c['x'], c['y'], c['z']] + ([c['qw'], c['qx'], c['qy'], c['qz']] if b['k'] == 'box' else ['1', '0', '0', '0']) + \
        [c['vx'], c['vy'], c['vz'], c['wx'], c['wy'], c['wz'], f(b['im'])] + \
        ([f(b['ii'][k]) for k in range(3)] if b['k'] == 'box' else ['0', '0', '0']) + \
        ['0' if b['k'] == 'box' else f(b['ii'][0]), f(max(b['ii']))]
    for nm, v in zip(HOLD, vals):
        (g.P if i == 0 else g.A)(nm, v, 0, ('GIr', i + 1))
hv = {nm: V(nm) for nm in HOLD}
pG = (hv['gpx'], hv['gpy'], hv['gpz'])
RG = rot_of(hv['gqw'], hv['gqx'], hv['gqy'], hv['gqz'])
colG = [tuple(g.P(f'gc{k}{r}', RG[r][k], 0, AT) for r in range(3)) for k in range(3)]
r = g.P3('grr', tuple(add(*(mul(off[k], colG[k][a]) for k in range(3))) for a in range(3)), 0, AT)
for a in 'xyz':     # touch grabs the centre
    g.A(f'grr{a}', '0', 0, THO)
gp = g.P3('Ngw', tuple(add(pG[a], r[a]) for a in range(3)), 0, AT)
target = g.P3('gtg', tuple(add(o, mul(tG, dv)) for o, dv in zip(RO, RD)), 0, AT)
# touch: the anchor plus the drag, which the handle measured in world units on the camera-facing plane through the body:
# its x and y axes are the ray's derivatives along the screen's x and y (unit, orthogonal)
EX = (cyw, '0', syw)
EY = (f'{f(st_)} * {syw}', f(ct), f'{f(-st_)} * {cyw}')
for k, a in enumerate('xyz'):
    g.A(f'gtg{a}', add(off[k], mul('var(--tdxg)', EX[k]), mul('var(--tdyg)', EY[k])), 0, THO)
vG = (hv['gvx'], hv['gvy'], hv['gvz'])
wG = (hv['gwx'], hv['gwy'], hv['gwz'])
vp = tuple(add(v, c) for v, c in zip(vG, cross(wG, r)))
imG = hv['gim']
iiG = [hv['gii0'], hv['gii1'], hv['gii2']]
weff = f"({imG} + ({dot(r, r)}) * ({hv['gimx']}))"
F = g.P3('gF', tuple(f'clamp(-{GRAB_AMAX}, {GRAB_K} * {sub(tg, gq)} - {GRAB_C} * {v}, {GRAB_AMAX}) / {weff}'
                     for tg, gq, v in zip(target, gp, vp)), 0, AT)
for a, Fa in zip('xyz', F):
    g.P(f'ga{a}', f'{Fa} * {imG}', 0, AT)
tau = g.P3('gtau', cross(r, F), 0, AT)
# world inverse inertia: boxes via their axes, spheres are isotropic
tb = [g.P(f'gtb{k}', dot(colG[k], tau), 0, AT) for k in range(3)]
for a, ax in zip(range(3), 'xyz'):
    g.P(f'gal{ax}', add(*(mul(mul(iiG[k], tb[k]), colG[k][a]) for k in range(3)), mul(hv['giso'], tau[a])), 0, AT)
# tether: project the grab point to the screen for a 2D line to the pointer
x1 = f'({gp[0]} * {cyw} + {gp[2]} * {syw})'
z1 = f'(-1 * {gp[0]} * {syw} + {gp[2]} * {cyw})'
y3 = f'({gp[1]} * {f(ct)} - {z1} * {f(st_)} + {f(CAM_TY)})'
z3 = f'({gp[1]} * {f(st_)} + {z1} * {f(ct)} - {f(CAM_DIST)})'
g.P('Ngsx', f'{x1} * {f(PERSP)} / ({f(PERSP)} - {z3})', 0, AT)
g.P('Ngsy', f'{y3} * {f(PERSP)} / ({f(PERSP)} - {z3})', 0, AT)
# the overlay's pointer end: the pointer, or with touch the target projected to the screen
g.P('Nosx', 'var(--sxg)', 0, AT)
g.P('Nosy', 'var(--syg)', 0, AT)
x1 = f'({target[0]} * {cyw} + {target[2]} * {syw})'
z1 = f'(-1 * {target[0]} * {syw} + {target[2]} * {cyw})'
y3 = f'({target[1]} * {f(ct)} - {z1} * {f(st_)} + {f(CAM_TY)})'
z3 = f'({target[1]} * {f(st_)} + {z1} * {f(ct)} - {f(CAM_DIST)})'
g.A('Nosx', f'{x1} * {f(PERSP)} / ({f(PERSP)} - {z3})', 0, THO)
g.A('Nosy', f'{y3} * {f(PERSP)} / ({f(PERSP)} - {z3})', 0, THO)

# Gauss-Seidel schedule: batch 0 = every body's planes, then round-robin rounds in which each body
# meets at most one other. Each batch is its own element (level LB + batch); a pair's contact
# geometry is declared at its own batch level, next to its solve (one block instead of two).
LB = 2
_ring = list(range(N)) + ([None] if N % 2 else [])
SCHED = []
for _r in range(len(_ring) - 1):
    SCHED.append([(min(_ring[t], _ring[-1 - t]), max(_ring[t], _ring[-1 - t])) for t in range(len(_ring) // 2)
                  if _ring[t] is not None and _ring[-1 - t] is not None])
    _ring = [_ring[0]] + [_ring[-1]] + _ring[1:-1]
# (planes first: solved last, a stack's floor push never reaches the bodies above it in the same
# step and the stack settles into a state with phantom downward velocities that never sleeps)
PLANE_LEV = LB
PAIR_LEV = {pr: LB + 1 + r for r, rnd in enumerate(SCHED) for pr in rnd}

# ---- narrowphase (L1) ---------------------------------------------------------------
for gr in groups:
    gate = gr['flag']
    a, bb, pl = gr['a'], gr['b'], gr['plane']
    gid = gr['id']
    gr['cd'] = []

    def add_contact(cp, a_, b_, dd, n, pt, act=None, lev=L1, gt=None, prop=True):
        actv = g.P(cp + 'a', act or f'sign(max(0, {dd}))', lev, gt or gate, syntax='<integer>') if prop else act
        gr['cd'].append(dict(a=a_, bb=b_, dd=dd, n=n, pt=pt, act=actv, sg=cp + 'a'))

    ka = BODIES[a]['k']
    LP = PLANE_LEV if pl else PAIR_LEV[(a, bb)]
    if pl:
        if pl in WALLS:
            ax_ = WALLS[pl]
            sgw = g.P(f'{gid}sg', f"-1 * sign({B[a]['p'][ax_]})", LP, gate)
            nn = tuple(sgw if k == ax_ else '0' for k in range(3))
            d0e = f"abs({B[a]['p'][ax_]}) - {WX if pl == 'X' else WZ}"
        else:
            n, P0 = PLANES[pl]
            nn = num3(n)
            d0e = dot(nn, vsub(num3(P0), B[a]['p']))
        if ka == 'box' and PATCHW == 'soft':
            # one contact at a soft support patch: per box axis k, e_k = h_k (n . col_k) is half the
            # depth difference between the box's two faces across that axis. The deepest corner is
            # d0 + sum |e_k|; the patch centre sits -sign(e_k) h_k * w_k along each axis, with
            # w_k = |e_k| / (PATCHC + depth - |e_k|): the even-weighted centroid of the penetrating
            # corners of a box that rests (nearly) flat, the corner itself once it stands on it
            col = B[a]['col']
            hb = BODIES[a]['h']
            d0 = PE(f'{gid}d0', d0e, LP, gate)
            e = [g.P(f'{gid}e{k}', mul(f(hb[k]), dot(nn, col[k])), LP, gate) for k in range(3)]
            dm = g.P(f'{gid}dm', add(d0, *(f'abs({e[k]})' for k in range(3))), LP, gate)
            ok = [g.P(f'{gid}o{k}', f'-1 * sign({e[k]}) * {f(hb[k])} * min(1, abs({e[k]}) / max({PATCHC} + {dm} - abs({e[k]}), 0.000001))', LP, gate)
                  for k in range(3)]
            add_contact(f'{gid}c0', a, None, dm, nn, None, '1', prop=False)
            gr['cd'][-1]['roff'] = tuple(add(*(mul(ok[k], col[k][c]) for k in range(3))) for c in range(3))
        elif ka == 'box':
            # corner j = p + sum_k s_jk h_k col_k, so its depth is affine in the corner signs:
            # dd_j = d0 - sum_k s_jk e_k with e_k = h_k (n . col_k); no corner positions needed
            col = B[a]['col']
            d0 = PE(f'{gid}d0', d0e, LP, gate)
            e = [g.P(f'{gid}e{k}', mul(f(BODIES[a]['h'][k]), dot(nn, col[k])), LP, gate) for k in range(3)]
            for j, sg in enumerate(CORN):
                dd = add(d0, *(mul(f(-s_), e[k]) for k, s_ in enumerate(sg)))
                add_contact(f'{gid}c{j}', a, None, dd, nn, None, f'sign(max(0, {dd}))', prop=False)
                gr['cd'][-1]['cs'] = sg
        else:
            rr = BODIES[a]['r']
            dd = add(f(rr), f'({d0e})')
            roff = tuple(mul(nk, f(-rr)) for nk in nn)
            add_contact(f'{gid}c0', a, None, dd, nn, tuple(add(pa, o) for pa, o in zip(B[a]['p'], roff)),
                        '1', prop=False)
            gr['cd'][-1]['roff'] = roff
        continue
    kb = BODIES[bb]['k']
    if ka == 'sph' and kb == 'sph':
        ra, rb = BODIES[a]['r'], BODIES[bb]['r']
        dv = vsub(B[a]['p'], B[bb]['p'])
        tg = gate     # the broadphase flag is already the touch test
        dist = g.P(f'{gid}di', f"max(hypot({', '.join(dv)}), 0.000001)", LP, tg)
        n = g.P3(f'{gid}n', tuple(f'{t} / {dist}' for t in dv), LP, tg)
        dd = f'({f(ra + rb)} - {dist})'
        add_contact(f'{gid}c0', a, bb, dd, n, tuple(sub(pa, mul(nk, f(ra))) for pa, nk in zip(B[a]['p'], n)),
                    '1', prop=False)
        gr['cd'][-1]['roff'] = tuple(mul(nk, f(-ra)) for nk in n)
    elif ka != kb:
        si, bi = (a, bb) if ka == 'sph' else (bb, a)
        r_ = BODIES[si]['r']
        hb = BODIES[bi]['h']
        col = B[bi]['col']
        rel = vsub(B[si]['p'], B[bi]['p'])
        tg = f'tc{gid}'
        l = [g.P(f'{gid}l{k}', dot(col[k], rel), L1, gate) for k in range(3)]
        e = [g.P(f'{gid}e{k}', f'{l[k]} - clamp({-hb[k]}, {l[k]}, {hb[k]})', L1, gate) for k in range(3)]
        dist = g.P(f'{gid}di', f"hypot({', '.join(e)})", L1, gate)
        # touching iff the closest point is within r (a centre inside the box has dist 0)
        gr['touch'] = f'sign(max(0, {f(r_)} - {dist}))'
        o = g.P(f'{gid}o', f'sign({dist})', LP, tg)
        pen = [f'({hb[k]} - abs({l[k]}))' for k in range(3)]
        fx = g.P(f'{gid}fx', f'sign(max(0, min({pen[1]}, {pen[2]}) - {pen[0]}))', LP, tg)
        fy = g.P(f'{gid}fy', f'(1 - {fx}) * sign(max(0, {pen[2]} - {pen[1]}))', LP, tg)
        fz = f'(1 - {fx} - {fy})'
        fl_ = (fx, fy, fz)
        nl = [f'({o} * {e[k]} / max({dist}, 0.000001) + (1 - {o}) * {fl_[k]} * sign({l[k]}))' for k in range(3)]
        dd = g.P(f'{gid}d', f"{o} * ({r_} - {dist}) + (1 - {o}) * ({r_} + min({', '.join(pen)}))", LP, tg)
        n = g.P3(f'{gid}n', tuple(add(*(mul(nl[k], col[k][c]) for k in range(3))) for c in range(3)), LP, tg)
        add_contact(f'{gid}c0', si, bi, dd, n, tuple(sub(pa, mul(nk, f(r_))) for pa, nk in zip(B[si]['p'], n)),
                    '1', prop=False)
        gr['cd'][-1]['roff'] = tuple(mul(nk, f(-r_)) for nk in n)
    else:
        # box vs box: C[k][m] = axis k of a . axis m of bb
        cA, cB = B[a]['col'], B[bb]['col']
        C = [[g.P(f'{gid}C{k}{m}', dot(cA[k], cB[m]), L1, gate) for m in range(3)] for k in range(3)]
        refs = {}
        for Rb, Ib in ((a, bb), (bb, a)):
            rp = f'{gid}r{Rb}'
            Crow = (lambda k, m: C[k][m]) if Rb == a else (lambda k, m: C[m][k])   # axis k of R . axis m of I
            hR, hI = BODIES[Rb]['h'], BODIES[Ib]['h']
            colR = B[Rb]['col']
            rel = vsub(B[Ib]['p'], B[Rb]['p'])
            o_ = [g.P(f'{rp}o{k}', dot(colR[k], rel), L1, gate) for k in range(3)]
            ov = [f"({hR[k]} + {add(*(mul(f(hI[m]), f'abs({Crow(k, m)})') for m in range(3)))} - abs({o_[k]}))" for k in range(3)]
            ovv = [g.P(f'{rp}v{k}', ov[k], L1, gate) for k in range(3)]
            ovm = g.P(f'{rp}om', f"min({', '.join(ovv)})", L1, gate)
            # everything else about this reference face is only needed if it is the one in use
            ug = f'{gid}uA' if Rb == a else f'{gid}uB'
            fx = g.P(f'{rp}fx', f'sign(max(0, min({ovv[1]}, {ovv[2]}) - {ovv[0]}))', LP, ug)
            fy = g.P(f'{rp}fy', f'(1 - {fx}) * sign(max(0, {ovv[2]} - {ovv[1]}))', LP, ug)
            fz = g.P(f'{rp}fz', f'1 - {fx} - {fy}', LP, ug)
            fk = (fx, fy, fz)
            sgn = [f'sign({o_[k]})' for k in range(3)]
            nR = g.P3(f'{rp}n', tuple(add(*(mul(mul(fk[k], sgn[k]), colR[k][c]) for k in range(3))) for c in range(3)), LP, ug)
            # fx + fy + fz = 1, so write these as base + differences (constant for cubes)
            sel3 = lambda vals: add(f(vals[2]), mul(fx, f(vals[0] - vals[2])), mul(fy, f(vals[1] - vals[2])))
            hn = PE(f'{rp}hn', sel3([hR[k] for k in range(3)]), LP, ug)
            hl1 = PE(f'{rp}h1', sel3([hR[(k + 1) % 3] for k in range(3)]), LP, ug)
            hl2 = PE(f'{rp}h2', sel3([hR[(k + 2) % 3] for k in range(3)]), LP, ug)
            # incident corner local coordinates along (normal, lateral1, lateral2) are affine in the corner signs
            oa = g.P(f'{rp}oa', add(*(mul(mul(fk[k], sgn[k]), o_[k]) for k in range(3))), LP, ug)
            o1 = g.P(f'{rp}m1', add(*(mul(fk[k], o_[(k + 1) % 3]) for k in range(3))), LP, ug)
            o2 = g.P(f'{rp}m2', add(*(mul(fk[k], o_[(k + 2) % 3]) for k in range(3))), LP, ug)
            Am = [g.P(f'{rp}A{m}', add(*(mul(mul(fk[k], sgn[k]), Crow(k, m)) for k in range(3))) + f' * {hI[m]}', LP, ug) for m in range(3)]
            B1 = [g.P(f'{rp}P{m}', add(*(mul(fk[k], Crow((k + 1) % 3, m)) for k in range(3))) + f' * {hI[m]}', LP, ug) for m in range(3)]
            B2 = [g.P(f'{rp}Q{m}', add(*(mul(fk[k], Crow((k + 2) % 3, m)) for k in range(3))) + f' * {hI[m]}', LP, ug) for m in range(3)]
            ax1 = g.P3(f'{rp}e', tuple(add(*(mul(fk[k], colR[(k + 1) % 3][c]) for k in range(3))) for c in range(3)), LP, ug)
            ax2 = g.P3(f'{rp}g', tuple(add(*(mul(fk[k], colR[(k + 2) % 3][c]) for k in range(3))) for c in range(3)), LP, ug)
            refs[Rb] = dict(I=Ib, ovm=ovm, n=nR, hn=hn, hl1=hl1, hl2=hl2, oa=oa, o1=o1, o2=o2, A=Am, B1=B1, B2=B2, rp=rp,
                            ax1=ax1, ax2=ax2, R=Rb)
        # exactly one reference face per pair (ties go to `a`): with lateral clipping either face
        # yields the right patch, so testing both would only double the work
        gr['refsel'] = (refs[a], refs[bb])
        # face-axis SAT early out: separated along any face normal -> no corner tests at all
        ovl = g.P(f'{gid}ov', f"sign(max(0, min({refs[a]['ovm']}, {refs[bb]['ovm']})))", L1, gate, syntax='<integer>')
        useA = g.P(f'{gid}uA', f"{ovl} * (1 - sign(max(0, {refs[a]['ovm']} - {refs[bb]['ovm']})))", L1, gate, syntax='<integer>')
        g.P(f'{gid}uB', f'{ovl} - {useA}', L1, gate, syntax='<integer>')
        for Rb, ug in ((a, f'{gid}uA'), (bb, f'{gid}uB')):
            rf = refs[Rb]
            if PATCHB == 'soft':
                # (experimental: leaning box piles jitter and never sleep with it)
                # one contact at the incident box's soft support patch (as for the tray planes), its
                # centre clamped to the reference face: the deepest incident corner's depth is
                # hn - oa + sum |A_m|, and each incident axis m moves the patch -sign(A_m) w_m of the way
                cp = f"{rf['rp']}c0"
                absA = [f"abs({rf['A'][m]})" for m in range(3)]
                dm = g.P(cp + 'dm', f"{rf['hn']} - {rf['oa']} + {' + '.join(absA)}", LP, ug)
                wv = [g.P(cp + f'k{m}', f"-1 * sign({rf['A'][m]}) * min(1, {absA[m]} / max({PATCHC} + {dm} - {absA[m]}, 0.000001))", LP, ug)
                      for m in range(3)]
                lat1 = add(rf['o1'], *(mul(wv[m], rf['B1'][m]) for m in range(3)))
                lat2 = add(rf['o2'], *(mul(wv[m], rf['B2'][m]) for m in range(3)))
                l1c = g.P(cp + 'u', f"clamp(-1 * {rf['hl1']}, {lat1}, {rf['hl1']})", LP, ug)
                l2c = g.P(cp + 'w', f"clamp(-1 * {rf['hl2']}, {lat2}, {rf['hl2']})", LP, ug)
                add_contact(cp, rf['I'], Rb, dm, rf['n'], None, '1', LP, ug, prop=False)
                gr['cd'][-1].update(ref=rf, l1=l1c, l2=l2c, ug=ug)
                continue
            for j, sg in enumerate(CORN):
                cp = f"{rf['rp']}c{j}"
                lin = lambda base, coef: add(base, *(mul(f(s_), cf) for s_, cf in zip(sg, coef)))
                along = g.P(cp + 'al', lin(rf['oa'], rf['A']), LP, ug)
                lat1 = lin(rf['o1'], rf['B1'])
                lat2 = lin(rf['o2'], rf['B2'])
                dd = f"({rf['hn']} - {along})"
                # clip the corner laterally to the reference face: for crossed or overhanging boxes
                # the clipped points are the corners of the real overlap patch
                l1c = g.P(cp + 'u', f"clamp(-1 * {rf['hl1']}, {lat1}, {rf['hl1']})", LP, ug)
                l2c = g.P(cp + 'w', f"clamp(-1 * {rf['hl2']}, {lat2}, {rf['hl2']})", LP, ug)
                act = f"sign(max(0, min({dd}, {along} + {rf['hn']})))"
                add_contact(cp, rf['I'], Rb, dd, rf['n'], None, act, LP, ug)
                gr['cd'][-1].update(ref=rf, l1=l1c, l2=l2c, ug=ug)

# ---- touch flags (LC): the solve runs only for groups with an active contact -------------
# (a contact's q = act * max(0, depth - moved) needs act = 1, so this is exact, and most
# broadphase-near pairs are not actually touching)
for gr in groups:
    if gr['l0touch']:
        gr['tflag'] = gr['flag']
        continue
    gr['tflag'] = f'tc{gr["id"]}'
    if 'refsel' in gr:
        # box/box: no touch flag; the corner tests and the whole solve are declared in both
        # reference-face blocks (as alternatives), so a pair costs 3 blocks instead of 6
        gr['dup'] = (f"{gr['id']}uA", f"{gr['id']}uB")
    else:
        g.P(gr['tflag'], gr.get('touch') or 'sign(' + ' + '.join(cd['act'] for cd in gr['cd']) + ')', L1, gr['flag'], syntax='<integer>')
for i in range(N):
    g.P(f'tw{i}', 'sign(' + ' + '.join(V(gr['tflag']) for gr in groups if gr['plane'] and gr['a'] == i) + ')',
        L0, AW(i), syntax='<integer>')

# ---- solve (L2) ------------------------------------------------------------------------
pair_of = {(gr['a'], gr['b']): gr for gr in groups if not gr['plane']}
rounds = [[[pair_of[pr]] for pr in rnd] for rnd in SCHED]
batches = [[[gr for gr in groups if gr['plane'] and gr['a'] == i] for i in range(N)]] + rounds

# Each batch is its own element in the chain (levels LB, LB+1, ...). A body's running totals
# (position, rotation, and the position-only "pseudo" shares of both) are inherited '*' props K:
# a batch that touches the body computes the new totals J (named by batch parity) and the NEXT
# element aliases K = J. Reading the latest total is then one var() with no fallback chain, and
# the final state needs no sum over every group the body could have been in.
NBT = len(batches)
LFIN = LF = LB + NBT     # final state and writeback (the last batch is read directly, no aliases)
ACC = ('x', 'y', 'z', 'tx', 'ty', 'tz', 'ex', 'ey', 'ez', 'gx', 'gy', 'gz')
# a sphere's rotation never enters a contact, so it skips the pseudo share of rotation
ACCB = {i: ACC if BODIES[i]['k'] == 'box' and os.environ.get('PSEUDOROT', '1') == '1' else ACC[:9] for i in range(N)}
for i in range(N):
    for c in ACCB[i]:
        g.reg(f'K{i}{c}', syntax='*')
        g.reg(f'JP{i}{c}', syntax='*')
        for par in (0, 1):
            g.reg(f'J{par}{i}{c}')
has_acc = set()          # bodies that may already have K declared (statically)


def Kr(i, c):
    init = B[i]['p']['xyz'.index(c)] if c in ('x', 'y', 'z') else '0'
    if c not in ACCB[i]:
        return '0'
    return f'var(--K{i}{c}, {init})' if i in has_acc else init


def Kfin(i, c):
    """final total: the plane batch's (it is last, so it isn't aliased) or the pairs' latest"""
    return f'var(--JP{i}{c}, {Kr(i, c)})' if c in ACCB[i] else '0'


def moved(i):
    if i not in has_acc:
        return ('0', '0', '0')
    return tuple(sub(Kr(i, a), B[i]['p'][k]) for k, a in enumerate('xyz'))


def inv_inertia(i, vec, sname):
    """world-space I^-1 * vec for body i"""
    b = BODIES[i]
    if b['k'] == 'sph':
        return vscale(vec, f(b['ii'][0]))
    col = B[i]['col']
    dk = [g.P(f'{sname}{k}', dot(col[k], vec), L2, curgate) for k in range(3)]
    return tuple(add(*(mul(mul(f(b['ii'][k]), dk[k]), col[k][a]) for k in range(3))) for a in range(3))


def rot_iso(i, r, t):
    """approx t-direction rotational inverse mass at lever r: mean(I^-1) * |r x t|^2, t unit"""
    b = BODIES[i]
    im = sum(b['ii']) / 3
    return f"{f(im)} * ({dot(r, r)} - pow({dot(r, t)}, 2))"


def rot_w(i, cvec):
    """c . I^-1 c for a world vector c"""
    b = BODIES[i]
    if b['k'] == 'sph':
        return mul(f(b['ii'][0]), dot(cvec, cvec))
    col = B[i]['col']
    return add(*(mul(f(b['ii'][k]), f'pow({dot(col[k], cvec)}, 2)') for k in range(3)))


for bi, batch in enumerate(batches):
    L2 = LB + bi
    par = bi % 2
    newacc = []
    for unit in batch:
        contrib = {}
        for gr in unit:
            A_, Bo = gr['a'], gr['b']
            curgate = gate = gr['tflag']
            gp_ = f'b{bi}{gr["id"]}'
            qs = []
            # displacement of each body from earlier batches, read once per group (each read of
            # a version is a var() fallback chain, and every token is re-parsed every pass)
            mA_, mB_ = moved(A_), (moved(Bo) if Bo is not None else ('0', '0', '0'))
            one = len(gr['cd']) == 1     # a single contact reads the displacement once: inline
            # (box/box reads them once per reference block: inline too)
            inl = one or 'ref' in gr['cd'][0]
            dA = P3E(gp_ + 'mA', mA_, L2, gate) if not (inl or all(map(is0, mA_))) else mA_
            dB = P3E(gp_ + 'mB', mB_, L2, gate) if not (inl or all(map(is0, mB_))) else mB_
            dAB = tuple(sub(x, y) for x, y in zip(dA, dB))
            isref = 'ref' in gr['cd'][0]
            rAB = None
            if isref:
                # box/box: everything that depends on the chosen reference face is declared in that
                # face's own block (uA / uB) as alternatives of the same names; the touch block
                # then reads Q, H, D, n, ra, rb without caring which face it was
                first = True
                for Rb in (A_, Bo):
                    mine = [(ci, cd) for ci, cd in enumerate(gr['cd']) if cd['ref']['R'] == Rb]
                    rf, ug = mine[0][1]['ref'], mine[0][1]['ug']
                    sgn = 1 if mine[0][1]['a'] == A_ else -1
                    e = dot(dAB, rf['n'])
                    mv = '0' if is0(e) else g.P(f'{gp_}M{Rb}', e if sgn > 0 else f'-1 * ({e})', L2, ug)
                    ql = []
                    for ci, cd in mine:
                        qe = f"max(0, {cd['dd']})" if is0(mv) else f"max(0, {cd['dd']} - {mv})"
                        ql.append((g.P(f'{gp_}q{ci}', f"{cd['act']} * {qe}", L2, ug), cd))
                    D_ = (g.P if first else g.A)
                    kw = {} if not first else {}
                    Qr = D_(gp_ + 'Q', ' + '.join(q for q, _ in ql), L2, ug)
                    Qv = V(gp_ + 'Q')
                    iqr = f'(1 / max({Qv}, 0.000000001))'
                    D_(gp_ + 'H', f'sign({Qv})', L2, ug)
                    D_(gp_ + 'D', '(' + ' + '.join(f'{q} * {q}' for q, _ in ql) + f') * {iqr}', L2, ug)
                    S1 = g.P(f'{gp_}U{Rb}', ' + '.join(f"{q} * {cd['l1']}" for q, cd in ql), L2, ug)
                    S2 = g.P(f'{gp_}W{Rb}', ' + '.join(f"{q} * {cd['l2']}" for q, cd in ql), L2, ug)
                    # patch point relative to the reference body's centre
                    rr = tuple(f"{mul(rf['hn'], rf['n'][c])} + ({S1} * {rf['ax1'][c]} + {S2} * {rf['ax2'][c]}) * {iqr}" for c in range(3))
                    oth = Bo if Rb == A_ else A_
                    ro = tuple(f"{B[Rb]['p'][c]} + {V(gp_ + ('ra' if Rb == A_ else 'rb') + 'xyz'[c])} - {B[oth]['p'][c]}" for c in range(3))
                    ra_e, rb_e = (rr, ro) if Rb == A_ else (ro, rr)
                    for c in range(3):
                        D_(gp_ + 'ra' + 'xyz'[c], ra_e[c], L2, ug)
                        D_(gp_ + 'rb' + 'xyz'[c], rb_e[c], L2, ug)
                        D_(gp_ + 'n' + 'xyz'[c], f"-1 * {rf['n'][c]}" if Rb == A_ else rf['n'][c], L2, ug)
                    first = False
                Q, has, dbar = V(gp_ + 'Q'), V(gp_ + 'H'), V(gp_ + 'D')
                n = tuple(V(gp_ + 'n' + c) for c in 'xyz')
                rAB = (tuple(V(gp_ + 'ra' + c) for c in 'xyz'), tuple(V(gp_ + 'rb' + c) for c in 'xyz'))
                roff = pb = None
            else:
                mvcache = {}
                for ci, cd in enumerate(gr['cd']):
                    n, a_ = cd['n'], cd['a']
                    sgn = 1 if a_ == A_ else -1
                    key = (n, sgn)
                    if key not in mvcache:      # contacts sharing a normal (a box face) share this
                        e = dot(dAB, n)
                        if sgn < 0:
                            e = f'(-1 * {e})'
                        mvcache[key] = e
                    mv = mvcache[key]
                    if is0(mv):     # nothing moved yet (first batch): act * max(0, dd) = max(0, dd)
                        qe = f"max(0, {cd['dd']})"
                    elif cd['act'] == '1':
                        qe = f"max(0, {cd['dd']} - {mv})"
                    else:
                        qe = f"{cd['act']} * max(0, {cd['dd']} - {mv})"
                    qv = PE(f'{gp_}q{ci}', qe, L2, gate)
                    qs.append((qv, cd, '' if a_ == A_ else '-1 * '))
                single = len(qs) == 1
                Q = qs[0][0] if single else PE(gp_ + 'Q', ' + '.join(q for q, _, _ in qs), L2, gate)
                iq = f'(1 / max({Q}, 0.000000001))'
                has = PE(gp_ + 'H', f'sign({Q})', L2, gate)
                dbar = Q if single else PE(gp_ + 'D', '(' + ' + '.join(f'{q} * {q}' for q, _, _ in qs) + f') * {iq}', L2, gate)
                roff = qs[0][1].get('roff') if single else None
                if roff is not None:
                    pb = None     # the lever arms follow from the contact's offset from its own body
                elif 'cs' in qs[0][1]:
                    # box on a plane: patch point = p + sum_k h_k col_k (sum_j q_j s_jk) / Q, so the
                    # lever arm is the second term alone
                    if PATCHW == 'depth':
                        Sk = [PE(f'{gp_}S{k}', ' + '.join(mul(f(cd['cs'][k]), q) for q, cd, _ in qs), L2, gate) for k in range(3)]
                        iqw = iq
                    else:
                        # weight the penetrating corners more evenly than by depth: depth weighting
                        # puts the push next to the deepest corner, which over-levels a slightly
                        # tilted box and leaves it rocking every other step
                        wq = [PE(f'{gp_}k{j}', f'sign({q}) * ({PATCHC} + {q})', L2, gate) for j, (q, cd, _) in enumerate(qs)]
                        Sk = [PE(f'{gp_}S{k}', ' + '.join(mul(f(cd['cs'][k]), w_) for w_, (q, cd, _) in zip(wq, qs)), L2, gate) for k in range(3)]
                        iqw = f"(1 / max({PE(gp_ + 'K', ' + '.join(wq), L2, gate)}, 0.000000001))"
                    hb = BODIES[A_]['h']
                    roff = tuple(f"({add(*(mul(mul(f(hb[k]), Sk[k]), B[A_]['col'][k][c]) for k in range(3)))}) * {iqw}" for c in range(3))
                    pb = None
                else:
                    pb = P3E(gp_ + 'p', tuple('(' + ' + '.join(f'{q} * {cd["pt"][c]}' for q, cd, _ in qs) + f') * {iq}'
                                               for c in range(3)), L2, gate)
                if len(qs) == 1 or len({(cd['n'], sg_) for _, cd, sg_ in qs}) == 1:
                    # one contact, or all contacts share one normal (a plane): no averaging needed
                    n = qs[0][1]['n']
                    if qs[0][2]:
                        n = tuple(f'(-1 * {c})' for c in n)
                else:
                    nb_ = tuple('(' + ' + '.join(f"{s}{q} * {cd['n'][c]}" for q, cd, s in qs) + ')' for c in range(3))
                    nl = PE(gp_ + 'nl', f"max(hypot({', '.join(nb_)}), 0.000000001)", L2, gate)
                    n = P3E(gp_ + 'n', tuple(f'{c} / {nl}' for c in nb_), L2, gate)
            Aa = BODIES[A_]
            if rAB is not None:
                rA, rB_e = rAB
            elif roff is not None:
                own = qs[0][1]['a']
                other = Bo if own == A_ else A_
                if own == A_:
                    rA = P3E(gp_ + 'ra', roff, L2, gate)
                    rB_e = vsub(tuple(add(x, y) for x, y in zip(B[A_]['p'], roff)), B[Bo]['p']) if Bo is not None else None
                else:
                    rB_e = roff
                    rA = P3E(gp_ + 'ra', vsub(tuple(add(x, y) for x, y in zip(B[Bo]['p'], roff)), B[A_]['p']), L2, gate)
            else:
                rA = P3E(gp_ + 'ra', vsub(pb, B[A_]['p']), L2, gate)
                rB_e = vsub(pb, B[Bo]['p']) if Bo is not None else None
            # a sphere's lever arm to its own surface point along n is parallel to n: no normal
            # torque, and its tangential rotational mass is the constant ii * r^2
            sphA = roff is not None and Aa['k'] == 'sph'
            sphB = roff is not None and Bo is not None and BODIES[Bo]['k'] == 'sph'
            cAn = ('0', '0', '0') if sphA else P3E(gp_ + 'ca', cross(rA, n), L2, gate)
            vA = tuple(add(v, c) for v, c in zip(B[A_]['v'], cross(B[A_]['o'], rA)))
            wA = add(f(Aa['im']), rot_w(A_, cAn))
            if Bo is not None:
                Bb = BODIES[Bo]
                rB = rB_e if rAB is not None else P3E(gp_ + 'rb', rB_e, L2, gate)
                cBn = ('0', '0', '0') if sphB else P3E(gp_ + 'cb', cross(rB, n), L2, gate)
                vB = tuple(add(v, c) for v, c in zip(B[Bo]['v'], cross(B[Bo]['o'], rB)))
                vrel = P3E(gp_ + 'vr', vsub(vA, vB), L2, gate)
                up = f"(-1 * {dot(n, ('0', 'var(--gy)', '0'))} / max(abs(var(--gy)), 1))"
                # a sleeping partner is frozen this pass, so it acts as immovable (inverse mass 0)
                sA = PE(gp_ + 'sa', f'(1 - {f(1 - SHOCK)} * max(0, -1 * {up})) * var(--aw{A_})', L2, gate)
                sB = PE(gp_ + 'sb', f'(1 - {f(1 - SHOCK)} * max(0, {up})) * var(--aw{Bo})', L2, gate)
                wn = f"({wA}) * {sA} + ({add(f(Bb['im']), rot_w(Bo, cBn))}) * {sB}"
            else:
                vrel = P3E(gp_ + 'vr', vA, L2, gate)
                sA = sB = None
                wn = wA
            wnv = PE(gp_ + 'wn', wn, L2, gate)
            vn = PE(gp_ + 'vn', dot(vrel, n), L2, gate)
            vt = P3E(gp_ + 'vt', tuple(sub(vrel[c], mul(vn, n[c])) for c in range(3)), L2, gate)
            vtl = PE(gp_ + 'tl', f"max(hypot({', '.join(vt)}), 0.000001)", L2, gate)
            # split impulse: lvel cancels this step's approach whenever there is any overlap and
            # carries velocity; the rest pushes out older overlap (beyond the slop, capped) and is
            # removed again from the rederived velocity, so depenetration never launches bodies
            appr = f'max(0, -1 * {vn}) * {h}'
            lvel = PE(gp_ + 'lv', f'max(0, min({dbar}, {appr})) / {wnv}', L2, gate)
            lam = PE(gp_ + 'l', f'max({lvel}, max(0, min({dbar} - {SLOP}, {appr} + {MAXCORR})) / {wnv})', L2, gate)
            lex = PE(gp_ + 'le', f'{lam} - {lvel}', L2, gate)
            bounce = f'{has} * sign(max(0, -1 * {vn} - {BOUNCE_THR}))'
            pn = PE(gp_ + 'pn', f'{lam} + {bounce} * {f(E)} * -1 * {vn} / {wnv} * {h}', L2, gate)
            # friction: effective inverse mass along the sliding direction t (not the normal's:
            # at a box's bottom patch the lever arm is perpendicular to t, ~2.5x more compliant)
            iso_s = lambda b_: f(b_['im'] + b_['ii'][0] * b_['r'] ** 2)
            if not (sphA and (Bo is None or sphB)):
                tt = P3E(gp_ + 'td', tuple(f'{c} / {vtl}' for c in vt), L2, gate)
            wt = iso_s(Aa) if sphA else add(f(Aa['im']), rot_iso(A_, rA, tt))
            if Bo is not None:
                wt = f"({wt}) * {sA} + ({iso_s(Bb) if sphB else add(f(Bb['im']), rot_iso(Bo, rB, tt))}) * {sB}"
            wtv = PE(gp_ + 'wt', wt, L2, gate)
            lt = PE(gp_ + 'lt', f'{has} * min({MU} * {pn}, {vtl} * {h} / {wtv}) / {vtl}', L2, gate)
            Pv = P3E(gp_ + 'P', tuple(sub(mul(pn, n[c]), mul(lt, vt[c])) for c in range(3)), L2, gate)
            # torsional friction: one reduced contact point can't resist spin about the normal,
            # so cancel relative spin about n directly, limited by mu * normal impulse * patch radius
            rp_ = min(min(BODIES[x_]['h']) if BODIES[x_]['k'] == 'box' else 2.0 for x_ in (A_, Bo) if x_ is not None) * 0.6
            spin = dot(vsub(B[A_]['o'], B[Bo]['o']) if Bo is not None else B[A_]['o'], n)
            iimA = f(sum(Aa['ii']) / 3)
            wtor = iimA if Bo is None else f"{iimA} * {sA} + {f(sum(BODIES[Bo]['ii']) / 3)} * {sB}"
            lto = PE(gp_ + 'to', f'clamp(-1 * {MU} * {pn} * {f(rp_)}, -1 * ({spin}) * {h} / max({wtor}, 0.000000001), {MU} * {pn} * {f(rp_)})', L2, gate)
            # rolling resistance (a sphere in the contact): cancel relative angular velocity
            # perpendicular to n, limited by ROLL * radius * normal impulse, so balls come to rest
            rl = tuple('0' for _ in range(3))
            # boxes get a smaller arm: it stands in for the support polygon damping the rocking a
            # one-point patch otherwise keeps up (period-2 tilt flips that never let it sleep)
            sph_r = [BODIES[x_]['r'] * ROLL if BODIES[x_]['k'] == 'sph' else min(BODIES[x_]['h']) * ROLLB
                     for x_ in (A_, Bo) if x_ is not None and (BODIES[x_]['k'] == 'sph' or ROLLB > 0)]
            if sph_r and min(sph_r) > 0:
                wrel = vsub(B[A_]['o'], B[Bo]['o']) if Bo is not None else B[A_]['o']
                wrt = P3E(gp_ + 'rw', tuple(sub(wrel[k], mul(f'({spin})', n[k])) for k in range(3)), L2, gate)
                wrl = PE(gp_ + 'rl', f"max(hypot({', '.join(wrt)}), 0.000001)", L2, gate)
                # cancel at most half the relative spin per contact: every contact reads the same
                # predicted spin, so a ball touching two things would otherwise flip it each step
                lr = PE(gp_ + 'rr', f"min({f(min(sph_r))} * {pn}, {wrl} * {f(0.5 * STEP)} / max({wtor}, 0.000000001)) / {wrl}", L2, gate)
                rl = tuple(f'(-1 * {lr} * {c})' for c in wrt)
            tAe = tuple(add(c, mul(lto, n[k]), rl[k]) for k, c in enumerate(cross(rA, Pv)))
            # spheres use the torque once (isotropic inertia), boxes three times
            tA = tAe if Aa['k'] == 'sph' else P3E(gp_ + 'ta', tAe, L2, gate)
            dthA = inv_inertia(A_, tA, gp_ + 'ia')
            mA = (lambda e: f'{e} * {sA}') if sA else (lambda e: e)
            # the position change is used twice (version, pseudo part): cheaper inline than as props
            dx = tuple('(' + mA(f"{Pv[c]} * {f(Aa['im'])}") + ')' for c in range(3))
            dt = P3E(gp_ + 'qa', tuple(mA(e) for e in dthA), L2, gate)
            # split impulse, cheaply: the position-only share of this group's correction is the
            # fraction lex / pn of what it applied (exact for the normal part); the same share of
            # the rotation must not become spin either (a resting box would rock and never sleep)
            fr = PE(gp_ + 'fr', f'{lex} / max({pn}, 0.000000001)', L2, gate)
            contrib.setdefault(A_, []).append((dx, dt, fr))
            if Bo is not None:
                tBe = tuple(add(c, mul(lto, n[k]), rl[k]) for k, c in enumerate(cross(rB, Pv)))
                tB = tBe if Bb['k'] == 'sph' else P3E(gp_ + 'tb', tBe, L2, gate)
                dthB = inv_inertia(Bo, tB, gp_ + 'ib')
                dxb = tuple(f"(-1 * {Pv[c]} * {f(Bb['im'])} * {sB})" for c in range(3))
                dtb = P3E(gp_ + 'qb', tuple(f'-1 * {e} * {sB}' for e in dthB), L2, gate)
                contrib.setdefault(Bo, []).append((dxb, dtb, fr))
        last = bi == NBT - 1
        for body, cl in contrib.items():
            vgate = unit[0]['tflag'] if len(unit) == 1 else f'tw{body}'
            # the last batch's totals are '*' (left as text for the final to evaluate) and are read
            # there directly, with a fallback to K: no alias, no separate evaluation
            JN = (lambda c: f'JP{body}{c}') if last else (lambda c: f'J{par}{body}{c}')
            vals = {}
            for k, a in enumerate('xyz'):
                vals[a] = add(Kr(body, a), *(t[0][k] for t in cl))
                vals['t' + a] = add(Kr(body, 't' + a), *(t[1][k] for t in cl))
                vals['e' + a] = add(Kr(body, 'e' + a), *(mul(t[2], t[0][k]) for t in cl))
                vals['g' + a] = add(Kr(body, 'g' + a), *(mul(t[2], t[1][k]) for t in cl))
            for c in ACCB[body]:
                g.A(JN(c), vals[c], L2, vgate)
            if not last:
                # box/box has no single touch flag (its solve is duplicated into the two reference-face
                # blocks); its face-overlap flag covers both
                agate = f"{unit[0]['id']}ov" if 'dup' in unit[0] else vgate
                for c in ACCB[body]:
                    g.A(f'K{body}{c}', f'var(--J{par}{body}{c})', L2 + 1, agate)
            newacc.append(body)
    has_acc.update(newacc)

# box/box solve blocks: duplicate into the two reference-face blocks
_dup = {gr['tflag']: gr['dup'] for gr in groups if 'dup' in gr}
_nd = []
for lev, gate, name, expr in g.decl:
    if isinstance(gate, str) and gate in _dup:
        for ug in _dup[gate]:
            _nd.append((lev, ug, name, expr))
    else:
        _nd.append((lev, gate, name, expr))
g.decl = _nd

# final state per body
L2 = LFIN
new = {}
for i, b in enumerate(BODIES):
    d = B[i]
    # the totals are read many times below: evaluate them once
    pos = [g.P(f's{i}{a}', Kfin(i, a), L2, AW(i)) for a in 'xyz']
    if d['q'] is not None:
        th = [g.P(f'th{i}{a}', Kfin(i, 't' + a), L2, AW(i)) for a in 'xyz']
    else:   # sphere: this step's whole rotation (it has no predicted orientation)
        th = [g.P(f'th{i}{a}', f"{f(STEP)} * {o} + {Kfin(i, 't' + a)}", L2, AW(i)) for a, o in zip('xyz', d['o'])]
    # still this step? displacement and rotation below thresholds (velocity is no good: resting
    # boxes carry a bounded phantom velocity from the split impulse)
    # still if this step's motion is tiny, or if it just undoes the previous step's (a resting box
    # can rock back and forth by a hair every other step, which is not motion worth simulating)
    dsx = [sub(pos[k], d['X'][k]) for k in range(3)]
    rot1 = [f'{o} * {h} + {t}' for o, t in zip(d['o'], th)] if d['q'] is not None else th
    vstore = [cur[i]['v' + a] for a in 'xyz']
    lin = f"min(hypot({', '.join(dsx)}), hypot({', '.join(f'{x} + {v} * {h}' for x, v in zip(dsx, vstore))}))"
    ang = f"min(hypot({', '.join(rot1)}), hypot({', '.join(f'{r} + {o} * {h}' for r, o in zip(rot1, d['o']))}))"
    g.P(f'mv{i}', f"sign(max(0, {lin} - {SLEEP_DX}, {ang} - {SLEEP_DA})) + 1 - min(1, abs(var(--GIr) - {i + 1}))", L2, AW(i), syntax='<integer>')
    if d['q'] is not None:
        w_, x_, y_, z_ = d['q']
        tx, ty, tz = th
    else:
        w_, x_, y_, z_ = (cur[i][k] for k in ('qw', 'qx', 'qy', 'qz'))
        tx, ty, tz = th
    qn = (f'{w_} - 0.5 * ({tx} * {x_} + {ty} * {y_} + {tz} * {z_})',
          f'{x_} + 0.5 * ({w_} * {tx} + {ty} * {z_} - {tz} * {y_})',
          f'{y_} + 0.5 * ({w_} * {ty} + {tz} * {x_} - {tx} * {z_})',
          f'{z_} + 0.5 * ({w_} * {tz} + {tx} * {y_} - {ty} * {x_})')
    qr = [g.P(f'sq{i}{k}', e, L2, AW(i)) for k, e in zip('wxyz', qn)]
    ql = g.P(f'sl{i}', f'max(hypot({", ".join(qr)}), 0.000001)', L2, AW(i))
    # canonical sign (qw >= 0) so qw can be rederived from the other three
    cs_ = f"(1 - 2 * sign(max(0, -1 * {qr[0]})))"
    for k, e in zip('wxyz', qr):
        new[(i, 'q' + k)] = f'{cs_} * {e} / {ql}'
    for k, a in enumerate('xyz'):
        new[(i, a)] = pos[k]
        pe = Kfin(i, 'e' + a)
        new[(i, 'v' + a)] = f'({pos[k]} - {d["X"][k]} - {pe}) / {h}'
        pt_ = Kfin(i, 'g' + a)
        new[(i, 'w' + a)] = f'{d["o"][k]} + ({Kfin(i, "t" + a)} - {pt_}) / {h}'

for i in range(N):
    for fl in FIELDS:
        if fl == 'qw':
            continue
        lo, hi = RANGES[fl]
        c0 = V(f'{fl.upper()}{i}')
        # the register's own top: clamp() bounds the range, so no clamp here
        # awake & live: the new state; no time budget: hold; asleep: hold pose, zero velocity;
        # reset (checked last, wins): the scene's initial state
        # only the awake & live case is declared: otherwise the register falls back to the
        # current value (universal syntax: undeclared = guaranteed-invalid -> var() fallback).
        # A body about to fall asleep stores zero velocity, so it also wakes from rest.
        ne = new[(i, fl)]
        if fl[0] in 'vw':
            ne = f'var(--zs{i}) * ({ne})'
        g.P(f'N{fl}{i}', ne, LF, AW(i), syntax='*')
        g.A(f'N{fl}{i}', f'var(--i{fl}{i})', LF, ('rst', 1))
    # (the counter is tested against half-integers here and on #LS: it comes back from its register off by ~1e-6,
    # 46 as 45.999999. Chrome's var() rounds that away (6 significant digits); WebKit's keeps it (6 decimal places),
    # and an exact test woke every sleeping body on every pass)
    g.P(f'zs{i}', f'1 - sign(max(0, var(--NSC{i}) - {SLEEP_K + 0.5}))', LF, AW(i))
    sc = V(f'SC{i}')
    # awake: count still passes up to K (ready); a ready body that isn't blocked goes to K+1 (asleep)
    cnt = f'min({SLEEP_K}, {sc} + 1)'   # (only declared on passes that advance time)
    ready = f'sign(max(0, {sc} - {SLEEP_K - 0.5}))'
    # '*': undeclared on passes that don't advance time, so the register keeps its value
    g.P(f'NSC{i}', f'(1 - var(--rst)) * (1 - min(1, var(--mv{i}))) * ({cnt} + {ready} * (1 - var(--bk{i})))', LF, AW(i), syntax='*')
    g.A(f'NSC{i}', f'(1 - min(1, var(--pk{i}) + 1 - min(1, abs(var(--GIr) - {i + 1})))) * {sc}', LF, AS(i))
    g.A(f'NSC{i}', f'var(--isc{i}, 0)', LF, ('rst', 1))
g.P('NGI', '(1 - var(--rst)) * var(--G)', LF)
for k, nm in enumerate(('NGOX', 'NGOY', 'NGOZ')):
    g.P(nm, V(f'gof{k}'), LF)
g.P('NGT', V('gtG'), LF)
g.P('NGYP', 'var(--gy)', LF)
NLEV = g.levels

REGS = [('TP', 'NTP', 0, 100), ('DB', 'NDB', 0, 0.1), ('GI', 'NGI', 0, N + 1), ('GOX', 'NGOX', -800, 800),
        ('GOY', 'NGOY', -800, 800), ('GOZ', 'NGOZ', -800, 800), ('GT', 'NGT', 0, 4), ('GYP', 'NGYP', -2000, 2000)]
for i in range(N):
    REGS.append((f'SC{i}', f'NSC{i}', 0, SLEEP_K + 4))
for i in range(N):
    for fl in FIELDS:
        if fl == 'qw':      # derived: qw = sqrt(1 - |v|^2), quaternions kept with qw >= 0
            continue
        lo, hi = RANGES[fl]
        REGS.append((f'{fl.upper()}{i}', f'N{fl}{i}', lo, hi))

# ---- inliner: substitute cheap or single-use properties into their consumers -----------
# measured in Chrome: a registered property costs ~2.3us, each var() reference ~0.7us.
# A property with r references used k times is worth inlining when k*r*0.7 < 2.3 + 0.7*(r + k).
INL_R, INL_K, INL_LEN = int(os.environ.get('INL_R', 1)), int(os.environ.get('INL_K', 1)), int(os.environ.get('INL_LEN', 200))


def inline_pass():
    keep = set()
    for lev, gate, name, expr in g.decl:
        if gate:
            keep.add(gate[0] if isinstance(gate, tuple) else gate)
    for name, (syn, inh, init) in g.props.items():
        if syn != '<number>' or name.startswith('N') or name in ('G',):
            keep.add(name)
    pat = re.compile(r'var\(--([A-Za-z0-9_]+)\)')
    changed = True
    rounds = 0
    while changed and rounds < int(os.environ.get('INL_ROUNDS', 2)):
        changed = False
        rounds += 1
        info = {name: (lev, gate, expr) for lev, gate, name, expr in g.decl}
        uses = {}
        for lev, gate, name, expr in g.decl:
            for m in pat.finditer(expr):
                uses.setdefault(m.group(1), []).append(name)
        dead = set()
        subst = {}
        for name, (lev, gate, expr) in info.items():
            if name in keep or name not in uses:
                continue
            users = uses[name]
            if any(u in subst or u in dead for u in users):
                continue
            k = len(users)
            r = expr.count('var(')
            if not (r <= INL_R and k <= INL_K and len(expr) <= INL_LEN):
                continue
            if any(info[u][0] != lev or info[u][1] != gate and gate is not None for u in users if u in info):
                continue
            if any(u not in info for u in users):
                continue
            subst[name] = f'({expr})'
            dead.add(name)
        if not subst:
            break
        newdecl = []
        for lev, gate, name, expr in g.decl:
            if name in dead:
                continue
            e2 = pat.sub(lambda m: subst.get(m.group(1), m.group(0)), expr)
            newdecl.append((lev, gate, name, e2))
        g.decl = newdecl
        for nm in dead:
            g.props.pop(nm, None)
        changed = True
    return rounds

def inline2():
    """substitute small or single-use props into consumers in the same (level, gate) block.
    A registered prop costs ~2.5us per pass on top of its tokens, so an alias like
    --x:calc(var(--y)) or a one-use intermediate is pure overhead."""
    TOKR = re.compile(r'var\(--[A-Za-z0-9_]+|-?\d+\.?\d*(?:e-?\d+)?|[+*/]|(?<=\s)-(?=\s)|[a-z]+\(')
    pat = re.compile(r'var\(--([A-Za-z0-9_]+)\)')
    ndecl = {}
    for lev, gate, name, expr in g.decl:
        ndecl[name] = ndecl.get(name, 0) + 1
    gates = set()
    for lev, gate, name, expr in g.decl:
        if gate:
            gates.add(gate[0] if isinstance(gate, tuple) else gate)
    info = {name: (lev, gate, expr) for lev, gate, name, expr in g.decl}
    uses = {}
    for idx, (lev, gate, name, expr) in enumerate(g.decl):
        for m in re.finditer(r'var\(--([A-Za-z0-9_]+)', expr):
            uses.setdefault(m.group(1), []).append(idx)
    subst = {}
    for name, (lev, gate, expr) in info.items():
        syn = g.props[name][0]
        if ndecl[name] != 1 or syn not in ('<number>', '<integer>') or name in gates or name.startswith('N') or name not in uses:
            continue
        us = uses[name]
        if any(g.decl[u][0] != lev or g.decl[u][1] != gate for u in us):
            continue
        if any(f'var(--{name},' in g.decl[u][3] for u in us):
            continue
        nt = len(TOKR.findall(expr)) + 1
        k = len(us)
        # prop ~ 3.5us + 0.3us per token (its own and each reference); inlined ~ k copies
        if k == 1 if os.environ.get('INL_ONLY1', '1') == '1' else 8.3 + nt + k > k * nt:
            subst[name] = expr
    # keep nesting shallow: a substituted body may mention at most one more level of substitutes
    MAXD = int(os.environ.get('INL_DEPTH', 2))
    while True:
        depth = {}
        def dep(nm, seen=()):
            if nm in depth:
                return depth[nm]
            d = 1 + max([dep(m.group(1), seen + (nm,)) for m in pat.finditer(subst[nm]) if m.group(1) in subst] or [0])
            depth[nm] = d
            return d
        bad = [nm for nm in subst if dep(nm) > MAXD]
        if not bad:
            break
        for nm in bad:
            subst.pop(nm, None)
    def expand(e):
        for _ in range(MAXD + 1):
            e = pat.sub(lambda m: f'({subst[m.group(1)]})' if m.group(1) in subst else m.group(0), e)
        return e
    out2 = [(lev, gate, name, expand(expr)) for lev, gate, name, expr in g.decl if name not in subst]
    left = [m.group(1) for _, _, _, e in out2 for m in pat.finditer(e) if m.group(1) in subst]
    assert not left, left[:5]
    g.decl = out2
    for nm in subst:
        g.props.pop(nm, None)
    return len(subst)


if os.environ.get('INLINE2', '1') == '1':
    _k = inline2()
    print(f'inline2: removed {_k} props', file=sys.stderr)

if os.environ.get('NOINLINE', '1') != '1':
    _n0 = len(g.decl)
    _r = inline_pass()
    print(f'inliner: {_n0} -> {len(g.decl)} props in {_r} rounds', file=sys.stderr)

# ---- minimal inheritance -------------------------------------------------------------
decl_level = {}
for lev, gate, name, expr in g.decl:
    decl_level[name] = min(lev, decl_level.get(name, lev))
need = set()
for lev, gate, name, expr in g.decl:
    for ref in re.findall(r'var\(--([A-Za-z0-9_]+)', expr):
        if ref in decl_level and decl_level[ref] < lev:
            need.add(ref)
    gname = gate[0] if isinstance(gate, tuple) else gate
    if gname is not None and decl_level.get(gname, -1) < lev - 1:
        need.add(gname)
for name in decl_level:
    if name.startswith('N'):
        need.add(name)
need.add('G')
for name, (syn, inh, init) in list(g.props.items()):
    if name in decl_level and name not in need:
        g.props[name] = (syn, False, init)

# ---- shared names for level-local props -----------------------------------------------
# A prop declared and read only on one batch level (a contact's intermediates) is invisible to every
# other level (non-inherited), so the props of different levels can share names: the contacts of round
# r and round r' reuse the same few thousand names instead of each pair registering its own (this
# shrinks the stylesheet by a third at 64 bodies; @property rules alone were 12 MB).
if os.environ.get('SHARE', '1') == '1':
    _lv_decl, _lv_ref, _gates = {}, {}, set()
    for lev, gate, name, expr in g.decl:
        _lv_decl.setdefault(name, set()).add(lev)
        for ref in re.findall(r'var\(--([A-Za-z0-9_]+)', expr):
            _lv_ref.setdefault(ref, set()).add(lev)
        if gate:
            _gates.add(gate[0] if isinstance(gate, tuple) else gate)
    _local = {}
    for name, levs in _lv_decl.items():
        syn, inh, init = g.props[name]
        if inh or syn not in ('<number>', '<integer>') or name in _gates or name[0] in 'NG' or len(levs) != 1:
            continue
        lev = next(iter(levs))
        if lev < 2 or not _lv_ref.get(name, set()) <= {lev}:
            continue
        _local[name] = (lev, syn, init)
    _cnt, _ren = {}, {}
    for name, (lev, syn, init) in _local.items():
        key = (lev, syn, init)
        k = _cnt.get(key, 0); _cnt[key] = k + 1
        _ren[name] = f"z{'i' if syn == '<integer>' else 'n'}{k}"
    for name in _ren:
        g.props.pop(name)
    for name, (lev, syn, init) in _local.items():
        g.props.setdefault(_ren[name], (syn, False, init))
    _pat = re.compile(r'var\(--([A-Za-z0-9_]+)')
    g.decl = [(lev, gate, _ren.get(name, name), _pat.sub(lambda m: 'var(--' + _ren.get(m.group(1), m.group(1)), expr))
              for lev, gate, name, expr in g.decl]
    print(f'shared names: {len(_ren)} level-local props -> {len(set(_ren.values()))} names', file=sys.stderr)

# ---- emit ----------------------------------------------------------------------------
out = []
w = out.append
w(lbl.section('Registered properties', f'the {N}-body engine: every value it computes, with its syntax, inheritance and initial value'))
for name, (syn, inh, init) in g.props.items():
    if syn == '*':
        w(f"@property --{name}{{syntax:'*';inherits:{'true' if inh else 'false'}}}")
    else:
        w(f"@property --{name}{{syntax:'{syn}';inherits:{'true' if inh else 'false'};initial-value:{init}}}")
w(lbl.section('Clock and register keyframes', '--now counts 0 to 100 every 100 s; one keyframes rule per register maps its view timeline onto its value range'))
w('@keyframes clk{from{--now:0}to{--now:100}}')
for ri, (rn, nn, lo, hi) in enumerate(REGS):
    w(f'@keyframes q{ri}{{from{{--{rn}:{f(lo)}}}to{{--{rn}:{f(hi)}}}}}')
# #LS reads the state registers; #LT, inside it, runs the clock and the time budget. In a sleeping
# scene the state registers don't move, so #LS isn't restyled at all; #LT is (every pass, for the
# clock), but nothing it passes down changes: the levels below are left alone.
names = [f'q{ri}' for ri in range(2, len(REGS))]
tl = [f'--t{ri}' for ri in range(2, len(REGS))]
w(lbl.section('Pointer gating (#RB, .rz)', 'the pointer, camera yaw and touch drag reach the solver only while a body is held'))
w(f'#RB{{--sxg:calc(var(--sx) * var(--att));--syg:calc(var(--sy) * var(--att));--yawg:calc(var(--yaw) * var(--att));'
  '--tdxg:calc(var(--tdx) * var(--att));--tdyg:calc(var(--tdy) * var(--att));--tgig:calc(var(--tgi) * var(--att))}')
w('.rt,.rt *{--NTP:inherit;--NDB:inherit}.rz{--sx:0;--sy:0;--yaw:0;--tdx:0;--tdy:0;--tgi:0}')
w(lbl.section('State read-back (#LS)', 'animates the registers into each body\'s state; sleep and wake flags'))
w('#LS{')
w(f'animation-name:{",".join(names)};')
w(f'animation-duration:{",".join(["auto"] * len(names))};')
w(f'animation-iteration-count:1;')
w('animation-timing-function:linear;animation-fill-mode:both;')
w(f'animation-timeline:{",".join(tl)};')
w('--GI:0;--GOX:0;--GOY:0;--GOZ:0;--GT:0;--sx:0;--sy:0;--yaw:0;')
w('--GIr:calc(round(var(--GI)));--pick:calc(var(--att) * (1 - sign(var(--GIr))) * (1 - var(--tm)));'
  '--tpk:calc(var(--att) * (1 - sign(var(--GIr))) * var(--tm));--tho:calc(var(--att) * var(--tm));')
for i in range(N):
    for fl in FIELDS:
        if fl == 'qw':
            w(f'--QW{i}:calc(sqrt(max(0, 1 - var(--QX{i}) * var(--QX{i}) - var(--QY{i}) * var(--QY{i}) - var(--QZ{i}) * var(--QZ{i}))));')
        else:
            w(f'--{fl.upper()}{i}:var(--i{fl}{i});')
    # awake unless still for SLEEP_K passes; shake, reset, a gravity change or grabbing wakes it
    # (SC and GYP come back from their registers a hair off, so they're compared with a margin of 0.5: see NSC)
    w(f'--SC{i}:var(--isc{i}, 0);--aw{i}:calc(min(1, sign(max(0, {SLEEP_K + 0.5} - var(--SC{i}))) + var(--kick) + var(--rst) + '
      f'sign(max(0, abs(var(--gy) - var(--GYP)) - 0.5)) + 1 - min(1, abs(var(--GI) - {i + 1}))));'
      f'--nr{i}:calc(sign(max(0, {SLEEP_K - 0.5} - var(--SC{i}))));--mf{i}:calc(sign(max(0, 1.5 - var(--SC{i}))));')
w('--any:calc(sign(' + ' + '.join(f'var(--aw{i})' for i in range(N)) + '));')
w('--GYP:var(--gy);}')
w(lbl.section('Clock and time budget (#LT)', 'the clock and the time bank: whether this pass advances time by one step, and which bodies it simulates'))
w('#LT{animation-name:clk,q0,q1;animation-duration:100s,auto,auto;animation-iteration-count:infinite,1,1;'
  'animation-timing-function:linear;animation-fill-mode:both;animation-timeline:auto,--t0,--t1;')
w('--TP:var(--now);--DB:0;' + LS_TIME)
for i in range(N):
    w(f'--ac{i}:calc(var(--aw{i}) * var(--live));--as{i}:calc((1 - var(--aw{i})) * var(--live) * var(--any));'
      f'--rd{i}:calc(var(--ac{i}) * (1 - var(--nr{i})));')
# something awake and something asleep / some body ready to sleep: the neighbourhood digests are needed
w('--mix:calc(var(--live) * var(--any) * sign(' + ' + '.join(f'1 - var(--aw{i})' for i in range(N)) + '));')
w('--anyrd:calc(sign(' + ' + '.join(f'var(--rd{i})' for i in range(N)) + '));')
w('}')
blocks = OrderedDict()
for lev, gate, name, expr in g.decl:
    blocks.setdefault((lev, gate), []).append(f'--{name}:calc({_simplify(expr) if SIMPLIFY else expr})')
# reset overrides must come last in the cascade
_ord_key = lambda kv: 1.2 if isinstance(kv[0][1], tuple) and kv[0][1][0] == 'GIr' else \
    {('att', 1): 1, ('tho', 1): 1.1, ('pick', 1): 1.5, ('tpk', 1): 1.6, ('kick', 1): 2, ('rst', 1): 3}.get(kv[0][1], 0)
_ord = sorted(blocks.items(), key=_ord_key)
# Named gates: a container query that names a container no ancestor has is rejected almost for
# free, while an ordinary style() query costs ~2.5us per rule per pass whether it matches or not.
# L0 and L1 carry the container name b<i> only while body i is awake or near an awake body, and
# every rule belonging to body i, or to a pair whose lower index is i, names b<i>: the rules of a
# sleeping neighbourhood cost nothing at all. (Rules at level >= 2 then evaluate their gate on L1,
# which holds every gate value: they are all computed at L0/L1 and inherited.)
_OWN = [re.compile(p) for i_, p in enumerate((r'^np(\d+)_\d+$', r'^tcp(\d+)_\d+$', r'^p(\d+)_\d+(uA|uB|ov)$', r'^nw(\d+)[FCXZ]$',
                                r'^(?:tw|nb|ac|as)(\d+)$')) if str(i_) in os.environ.get('OWNSET', '01234')]


OWNLEV = int(os.environ.get('OWNLEV', 999))
# (off by default: Firefox's style(--flag) is true whenever a registered flag has a value, i.e. always; Chrome's
# style(--flag: 1) costs within the noise at 48 bodies)
BOOLQ = os.environ.get('BOOLQ', '0') == '1'


def owner(gn):
    for rx in _OWN:
        m = rx.match(gn)
        if m:
            return int(m.group(1))
    return None


# flags tested against a value other than 0 or 1 somewhere are not 0/1 flags: BOOLQ must not shorten their gates
_MULTI = {gt[0] for _l, gt, _n, _e in g.decl if isinstance(gt, tuple) and len(gt) == 2 and isinstance(gt[1], (int, float))
          and gt[1] not in (0, 1)}
w(lbl.section(f'Solver levels (#L0–#L{NLEV - 1})', f'one element per level: L0 predict and broadphase, L1 narrowphase, '
                f'L{LB}–L{LFIN - 1} the Gauss–Seidel batches, L{LFIN} the next state'))
# the blocks in cascade order: what every step computes, then the input overrides (reset last)
_GROUPS = {0: 'The step: predict, contacts, solve, next state', 1: 'Grab: pointer down', 1.1: 'Touch hold', 1.2: 'Holding: the held body\'s state, one block per body',
           1.5: 'Pick: the ray cast on the first pass of a press', 1.6: 'Touch pick', 2: 'Shake', 3: 'Reset (last in the cascade)'}
_grp = None
for (lev, gate), ds in _ord:
    _k = _ord_key(((lev, gate), ds))
    if _k != _grp:
        _grp = _k
        w(lbl.group(_GROUPS[_k]))
    rule = f'#L{lev}{{{";".join(ds)}}}'
    if gate is None:
        w(rule)
    else:
        gn, gv = gate if isinstance(gate, tuple) else (gate, 1)
        own = owner(gn) if lev <= OWNLEV and lev >= 1 else None
        if own is not None:
            assert decl_level.get(gn, -1) <= 1, gn
        # style(--flag) is true iff the registered flag differs from its initial 0: the same test as
        # style(--flag: 1) for a 0/1 flag, at about 0.4 us per rule instead of 0.7
        # (only for real 0/1 flags: GIr holds the held body's index + 1, and style(--GIr) for body 0's block was true
        # whenever ANY body was held, so dragging anything also pulled body 0; tools/statcheck.py, grabtest.js)
        q = f'style(--{gn})' if BOOLQ and gv == 1 and gn not in _MULTI and g.props.get(gn, ('', '', '0'))[2] == '0' else f'style(--{gn}: {gv})'
        w(f'@container {f"b{own} " if own is not None else ""}{q}{{{rule}}}')
_names = ' '.join(f'var(--A{i})' for i in range(N))
w(lbl.section('Container names (named gates)', 'body i\'s rules name container bi, which the levels carry only while it is awake or near an awake body'))
w('#L0{' + ''.join(f'--A{i}:if(style(--ac{i}: 1): b{i}; style(--nb{i}: 1): b{i}; else: );' for i in range(N)) + f'--AN:q {_names}}}')
if FFQ:
    # Without if() (Firefox; Safari before 27.x) every body is always named. The names only let a sleeping
    # neighbourhood's rules be skipped unevaluated; with all of them present every rule evaluates its own gate, with
    # the same result. Without this the --A are the if() text, container-name is invalid and no named rule matches.
    w('@supports not (width: if(style(--x: 1): 1px; else: 2px)){#L0{' + ''.join(f'--A{i}:b{i};' for i in range(N)) + '}}')
# every level carries the names, so a named rule always resolves to its parent (Chrome only forces
# a re-match of rules that depend on a style container for that container's children)
w(','.join(f'#L{l}' for l in range(NLEV)) + '{container-name:var(--AN)}#L1{--sxg:0;--syg:0;--yawg:0;--tdxg:0;--tdyg:0;--tgig:0}')
# Firefox only (FFQ): Gecko doesn't re-match rules that depend on a style container when the container's value
# changed through an animation (and every state value here comes from one), so the gates would keep their first
# result. It re-matches the whole subtree of a size container whose size changed: #LM's content box follows the clock
# while anything is awake (two incommensurate periods, so it changes every frame) and stays put once all sleep.
# (Changing only its padding, i.e. its content box, doesn't trigger the re-match: the frame's size must change.) #LW
# then takes the arena's size again (--u is the arena's width / VW), so the grab overlay on #L0, positioned in
# percentages of it, stays put. Chrome never sees it: a size container there would move the subtree's style recalc
# into layout.
if FFQ:
    w(lbl.group('Firefox only: the size-container clock that re-matches the gates (#LM, #LW)'))
    w('@supports (-moz-appearance: none){#LT{--ffk:calc(var(--any) * var(--now))}'
      '#LM{container-type:size;right:auto;bottom:auto;width:calc(1000px + mod(var(--ffk) * 6000, 600) * 1px);'
      'height:calc(1000px + mod(var(--ffk) * 6000, 583) * 1px)}'
      f'#LW{{right:auto;bottom:auto;width:calc({VIEW_W} * var(--u));height:calc({VIEW_H} * var(--u))}}}}')


def _canon(st):
    st = list(st)
    if st[3] < 0:       # q and -q are the same rotation; keep qw >= 0
        st[3:7] = [-x for x in st[3:7]]
    return st


def scene_decls(sn):
    # bodies placed at rest start asleep (sleep counter past the threshold): a big scene loads settled
    # -- only bodies actually touching the floor: anything placed above it (upper grid layers, hand-built
    # stacks) starts awake and settles on its own, else it would hang in mid-air until jostled
    def on_floor(i):
        st = SCENES[sn][i]
        if any(abs(v) > 1e-9 for v in st[7:]):
            return False
        b = BODIES[i]
        if b['k'] == 'box':
            w_, x_, y_, z_ = st[3:7]
            r1 = (2 * (x_ * y_ + w_ * z_), 1 - 2 * (x_ * x_ + z_ * z_), 2 * (y_ * z_ - w_ * x_))
            ext = sum(abs(a) * h for a, h in zip(r1, b['h']))
        else:
            ext = b['r']
        return abs(st[1] + ext) < 0.5
    rest = [sn != 'rain' and on_floor(i) for i in range(N)]
    # every body's start counter is declared in every scene's rule, 0 when it doesn't start asleep: the scene rules
    # cascade over the first scene's, so an undeclared counter kept that scene's value and bodies started asleep in
    # mid-air in the next scene (tools/floatcheck.js, tools/statcheck.py)
    return ';'.join(f'--i{fl}{i}:{f(val)}' for i in range(N) for fl, val in zip(FIELDS, _canon(SCENES[sn][i]))) + \
        ''.join(f';--isc{i}:{SLEEP_K + 1 if rest[i] else 0}' for i in range(N))


# the scene's initial state lives on this engine's .ini element (not on #app, which restyles on
# every control change) and is picked by the scene radios
w(lbl.section('Scene start states (#INI)', 'every body\'s start state for each scene; the checked or pressed scene\'s rule wins'))
w(f'#INI{{{scene_decls(SCENE_NAMES[0])}}}')
for sn in SCENE_NAMES[1:]:
    w(f'#app:has(#sc-{sn}:checked) #INI{{{scene_decls(sn)}}}')
for sn in SCENE_NAMES:
    w(f'#app:has(#lb-{sn}:active) #INI{{{scene_decls(sn)}}}')
# each register element holds two registers, one per axis (top and left in a scroller HS square):
# half the elements, and an element that moves costs its view timelines about as much as one
def _rpos(ri):
    rn, nn, lo, hi = REGS[ri]
    src = f'var(--{nn}, var(--{rn}))' if g.props.get(nn, ('',))[0] == '*' else f'var(--{nn})'
    return f'calc(({HS} - clamp(0, ({src} - {f(lo)}) / {f(hi - lo)}, 1) * {HS + 1}) * 1px)'
NREGEL = (len(REGS) + 1) // 2
# The timeline names are declared on a nest of small wrappers (.ts > .ts > ...) rather than one
# ancestor: a restyled element with view timelines looks its names up in the scope lists, and short
# lists make that ~3x cheaper (it's paid by every register element on every pass)
NTS = max(1, -(-NREGEL // 24))
w(lbl.section('Registers (#r0, #r1, …)', f'{len(REGS)} registers, two per element: its top and left are the next state, its view timelines read them back'))
w(lbl.group('Timeline scopes (.ts wrappers)'))
for s_ in range(NTS):
    ks = range(s_ * 24, min(NREGEL, s_ * 24 + 24))
    w(f'#ts{s_}{{timeline-scope:' + ','.join(f'--t{ri}' for k in ks for ri in (2 * k, 2 * k + 1) if ri < len(REGS)) + '}')
w(lbl.group('Register positions'))
w(f'#r0{{view-timeline:--t0 block,--t1 inline;top:{_rpos(0)};left:{_rpos(1)}}}')
for k in range(1, NREGEL):
    a, b = 2 * k, 2 * k + 1
    if b < len(REGS):
        w(f'#r{k}{{view-timeline:--t{a} block,--t{b} inline;top:{_rpos(a)};left:{_rpos(b)}}}')
    else:
        w(f'#r{k}{{view-timeline:--t{a} block;top:{_rpos(a)}}}')
PHYS_CSS = '\n'.join(out)

# ---- render ----------------------------------------------------------------------------
LIGHT = (-0.35, -1.0, 0.5)
ln = math.sqrt(sum(c * c for c in LIGHT))
LIGHT = tuple(c / ln for c in LIGHT)
FACES = [  # (axis k, sign, css transform to place the face, width axis, height axis)
    (2, 1, 'translateZ({hz})', 0, 1), (2, -1, 'rotateY(180deg) translateZ({hz})', 0, 1),
    (0, 1, 'rotateY(90deg) translateZ({hx})', 2, 1), (0, -1, 'rotateY(-90deg) translateZ({hx})', 2, 1),
    (1, -1, 'rotateX(90deg) translateZ({hy})', 0, 2), (1, 1, 'rotateX(-90deg) translateZ({hy})', 0, 2),
]
render_css, render_html, shadow_html = [], [], []
HD_PAD = 14     # touch handle radius = bounding radius + this (world units)
HD_L = 3000     # a handle scrolls up to this far from its rest offset (world units)
RIDX = {rn: ri for ri, (rn, nn, lo, hi) in enumerate(REGS)}
# Each body's wrapper animates its own pose from the registers' view timelines into generic
# NON-inherited props (--Rx.. --Rk, --Rg). Changing non-inherited values don't restyle descendants;
# only children that ask with an explicit `inherit` are recomputed, which is ~3x cheaper than letting
# inherited registered props flow into every face.
RF = [('x', 'Rx'), ('y', 'Ry'), ('z', 'Rz'), ('qx', 'Ri'), ('qy', 'Rj'), ('qz', 'Rk')]
render_css.append(lbl.section('Bodies', 'each body\'s wrapper animates its pose from the registers\' timelines; boxes get six faces, spheres a disc'))
render_css.append(lbl.group('Pose keyframes'))
for i in range(N):
    for fl, rp in RF:
        rn = f'{fl.upper()}{i}'
        ri = RIDX[rn]
        lo, hi = REGS[ri][2], REGS[ri][3]
        render_css.append(f'@keyframes v{ri}{{from{{--{rp}:{f(lo)}}}to{{--{rp}:{f(hi)}}}}}')
_gi = RIDX['GI']
render_css.append(f'@keyframes v{_gi}{{from{{--Rg:{f(REGS[_gi][2])}}}to{{--Rg:{f(REGS[_gi][3])}}}}}')
for i, b in enumerate(BODIES):
    render_css.append(lbl.group(f'Body {i}: {"box" if b["k"] == "box" else "sphere"}'))
    ris = [RIDX[f'{fl.upper()}{i}'] for fl, rp in RF] + [_gi]
    base = ';'.join(f'--{rp}:var(--i{fl}{i})' for fl, rp in RF)
    render_css.append(
        f'#w{i}{{animation-name:{",".join(f"v{r}" for r in ris)};animation-timeline:{",".join(f"--t{r}" for r in ris)};'
        f'{base};--c:{b["col"]}}}#b{i}{{--sel:calc(1 - min(1, abs(var(--Rg) - {i + 1})))}}')
    if b['k'] == 'box':
        faces = []
        for fi, (k, sg, tf, wa, ha) in enumerate(FACES):
            wv, hv = 2 * b['h'][wa], 2 * b['h'][ha]
            hx, hy, hz = b['h']
            t = tf.format(hx=f'{f(hx)}px', hy=f'{f(hy)}px', hz=f'{f(hz)}px')
            render_css.append(f'#b{i} .f{fi}{{width:{f(wv)}px;height:{f(hv)}px;margin:{f(-hv / 2)}px 0 0 {f(-wv / 2)}px;transform:{t}}}')
            faces.append(f'<i class="f f{fi}"></i>')
        inner = f'<div class="bd bx" id="b{i}">{"".join(faces)}</div>'
    else:
        render_css.append(f'#w{i}{{--r:{f(b["r"])}}}')
        inner = f'<i class="disc"></i><div class="bd sp" id="b{i}"><i class="eq"></i><i class="eq eq2"></i></div>'
    R_ = b['R'] if b['k'] == 'sph' else max(b['h'][0], b['h'][2]) * 1.1
    render_css.append(f'#s{i}{{width:{f(2 * R_)}px;height:{f(2 * R_)}px;margin:{f(-R_)}px 0 0 {f(-R_)}px}}')
    # (the shadow comes first: it cuts through its own body's lower faces, and Firefox doesn't split intersecting
    # planes as Chrome does but draws them in document order)
    # touch handle: a camera-facing disc over the body that a finger scrolls (ARCHITECTURE.md "Touch"); a little bigger
    # than the body, for fingers
    render_css.append(f'#h{i}{{--hr:{f(round(b["R"] + HD_PAD))};scroll-timeline:--H{i}x x,--H{i}y y}}')
    render_html.append(f'<div class="bw" id="w{i}"><i class="sh" id="s{i}"></i>{inner}<i class="hd" id="h{i}"><b><i></i><u></u></b></i></div>')
# box face lighting: world normal of face (axis k, sign) is sign * column k of R (generic rules,
# the same for every engine)
LIT, LAMS = [], []      # (LAMS: each face's lighting term, for the art styles' own shading: art3d.py)
for fi, (k, sg, tf, wa, ha) in enumerate(FACES):
    lam = ' + '.join(f'var(--r{rr}{k}) * {f(sg * LIGHT[rr])}' for rr in range(3))
    LAMS.append(lam)
    LIT.append(f'--k{fi}:color-mix(in oklab,var(--cs) calc((0.42 + 0.58 * max(0, {lam})) * 100%),#07080a)')
SHARED_CSS = [lbl.section('Box face lighting', 'shared by every engine: each face\'s colour from its world normal'),
              '.bx{--cs:color-mix(in oklab,var(--c),var(--acc) calc(var(--sel) * 55%));' + ';'.join(LIT) + '}',
              ''.join(f'.bx .f{fi}{{--k{fi}:inherit;background:var(--k{fi})}}' for fi in range(6))]
# grab feedback, drawn flat over the scene in screen units (reads this engine's grab state)
render_css.append(lbl.section('Grab feedback (ring, pin, tether)', 'drawn flat over the scene in screen units'))
render_css.append("""#ENG .ring,#ENG .pin,#ENG .tether{position:absolute;left:50%;top:50%;pointer-events:none;opacity:clamp(0, (__NP1__ - var(--GIr)) * var(--GIr) * var(--att), 1)}
#ENG .ring{width:calc(16 * var(--u));height:calc(16 * var(--u));border:2px solid var(--acc);border-radius:50%;
  transform:translate(calc(var(--Nosx) * var(--u) - 50%),calc(var(--Nosy) * var(--u) - 50%))}
#ENG .pin{width:8px;height:8px;border-radius:50%;background:var(--acc);
  transform:translate(calc(var(--Ngsx) * var(--u) - 4px),calc(var(--Ngsy) * var(--u) - 4px))}
#ENG .tether{height:2px;background:var(--acc);transform-origin:0 50%;
  width:calc(hypot(var(--Nosx) - var(--Ngsx), var(--Nosy) - var(--Ngsy)) * var(--u));
  transform:translate(calc(var(--Ngsx) * var(--u)),calc(var(--Ngsy) * var(--u) - 1px))
    rotate(atan2(calc(var(--Nosy) - var(--Ngsy)), calc(var(--Nosx) - var(--Ngsx))))}""")
# Touch input (ARCHITECTURE.md "Touch"), only on touch screens. #TI sums the handles' scroll offsets (only the dragged
# one is off its rest offset) into the drag --tdx/--tdy and the dragged body's index + 1, --tgi: one additive animation
# per handle and axis. The index is a step function, 0 within 0.6 units of rest. #FO follows the sum by snapping to an
# area placed at it, but Chrome defers that re-snap while a scroll gesture is active, so #FO stands still while a finger
# drags and catches up in the frame the gesture ends: --held is "#FO lags the sum".
render_css.append(lbl.section('Touch input (#TS, #TI, #FO)', 'the handles\' scroll offsets summed into the drag and the dragged body'))
render_css.append(lbl.group('Handle keyframes'))
_hk = []
for i in range(N):
    for a in 'xy':
        render_css.append(f'@keyframes h{a}{i}{{0%{{--td{a}:{HD_L};--tg{a}:{i + 1}}}49.99%{{--tg{a}:{i + 1};animation-timing-function:step-start}}'
                          f'50.01%{{--tg{a}:0;animation-timing-function:step-start}}100%{{--td{a}:{-HD_L};--tg{a}:{i + 1}}}}}')
        _hk.append((f'h{a}{i}', f'--H{i}{a}', 'add'))
for a in 'xy':
    render_css.append(f'@keyframes hf{a}{{from{{--fo{a}:{HD_L}}}to{{--fo{a}:{-HD_L}}}}}')
    _hk.append((f'hf{a}', f'--F{a}', 'replace'))
render_css.append(lbl.group('The drag sum and the follower (touch screens only)'))
render_css.append('@media (pointer:coarse){'
                  '#TS{timeline-scope:' + ','.join(t for _n, t, _c in _hk) + '}'
                  '#TI{animation-name:' + ','.join(n for n, _t, _c in _hk) + ';animation-timeline:' + ','.join(t for _n, t, _c in _hk) +
                  ';animation-composition:' + ','.join(c for _n, _t, c in _hk) + ';animation-duration:auto;animation-timing-function:linear;'
                  'animation-fill-mode:both;--tgi:calc(max(var(--tgx), var(--tgy)));'
                  '--held:calc(sign(max(0, abs(var(--tdx) - var(--fox)) + abs(var(--tdy) - var(--foy)) - 0.01)));'
                  '--att:calc(var(--held) * sign(var(--tgi)))}'
                  f'#FO{{display:block;scroll-timeline:--Fx x,--Fy y}}#FO>i{{width:{2 * HD_L + 10}px;height:{2 * HD_L + 10}px}}'
                  f'#FO>i>b{{left:calc(({HD_L} - var(--tdx)) * 1px);top:calc(({HD_L} - var(--tdy)) * 1px)}}'
                  # (the scene doesn't read the drag: zeroed, a drag doesn't restyle it, as .view does for the pointer)
                  '#TI .view{--tdx:0;--tdy:0;--tgi:0}}')
# the clock registers (TP, DB) are written from #LS itself, the rest from the last level
reg_html = ''.join(f'<i id="r{k}"></i>' for k in range(1, NREGEL))
reg_rt = '<div class="regs rt"><div class="sc"><i id="r0"></i></div></div>'
ENG_HTML = ('<div class="eng" id="ENG"><div class="ini" id="INI"><div class="ptr">' +
            # (touch input: #TS scopes the handles' timelines, #TI turns them into the drag, #FO is the follower. Above
            # the registers' .ts wrappers, so a register's timeline lookup finds its name before it reaches #TS's list)
            '<div class="lv" id="TS"><div class="lv" id="TI"><div class="fo" id="FO"><i><b></b></i></div>' +
            ''.join(f'<div class="lv" id="ts{s_}">' for s_ in range(NTS)) +
            # (the pointer moves --sx/--sy on every hover; this wrapper zeroes them so #LS isn't restyled)
            '<div class="lv" id="RB"><div class="lv rz"><div class="lv" id="LS"><div class="lv" id="LT">' + reg_rt +
            # (a plain wrapper: the clock registers make #LS restyle all its children every pass, and
            # this keeps L0 out of that unless its inputs really changed)
            # (the grab overlay hangs off L0, the only level that uses the pointer; L1 zeroes the pointer
            # for everything below, so a pointer move alone restyles nothing past L1)
            # (two wrappers; in Firefox (FFQ) #LM is the size-container re-match clock and #LW restores the arena's size)
            '<div class="lv" id="LM"><div class="lv" id="LW">' + ''.join(f'<div class="lv" id="L{l}">' + ('<i class="tether"></i><i class="pin"></i><i class="ring"></i>' if l == 0 else '')
                                         for l in range(NLEV)) +
            '<div class="regs"><div class="sc">' + reg_html + '</div></div>' +
            '</div>' * (NLEV + 5) +
            '<div class="view"><div class="cam"><i class="floor"></i><i class="ceil"></i><i class="post p1"></i><i class="post p2"></i>'
            '<i class="post p3"></i><i class="post p4"></i><i class="rail rb"></i><i class="rail rl"></i><i class="rail rr"></i>'
            '<i class="rail rn"></i>' + ''.join(render_html) + '</div></div></div>' + '</div>' * NTS + '</div></div></div></div></div>')
ENG_CSS = (PHYS_CSS + '\n' + '\n'.join(render_css)).replace('__NP1__', str(N + 1)).replace('__HVW__', f(VIEW_W / 2)).replace('__HVH__', f(VIEW_H / 2))
# Firefox negates hypot() by negating its arguments, which leaves it unchanged: x - hypot(3, 4) is x + 5, also
# inside a subtracted min/max/sign/sum and through var(). A product stops the negation there (hypot(..) * 1 is
# folded away, 1 * hypot(..) of numbers is not: of lengths it is too), so every hypot is written 1 * hypot (after
# simp.py, which would drop it). An unreported Firefox bug: ../../bugs/firefox-hypot-negation.html.
if os.environ.get('HYPOT1', '1') == '1':
    ENG_CSS = re.sub(r'(?<![\w-])hypot\(', '1 * hypot(', ENG_CSS)

# ---- per-engine names ------------------------------------------------------------------
# Several engines share one page, so every engine-owned name gets a prefix: custom properties
# (minified to short names), timelines, keyframes and element ids. Shared names (the controls'
# variables, the generic render props) stay as they are.
PFX = os.environ.get('PFX', '')
MINIFY = os.environ.get('MINIFY', '1' if PFX else '0') == '1'
SHARED_NAMES = {'gy', 'att', 'sx', 'sy', 'kick', 'rst', 'tm', 'held'}
if PFX or MINIFY:
    eng_names = [n for n in g.props if n not in SHARED_NAMES] + [f't{ri}' for ri in range(len(REGS))] + \
        [f'H{i}{a}' for i in range(N) for a in 'xy'] + ['Fx', 'Fy']
    def b36(k):
        d = '0123456789abcdefghijklmnopqrstuvwxyz'
        o = ''
        while True:
            o = d[k % 36] + o
            k //= 36
            if not k:
                return o
    ren = {}
    for n in eng_names:
        if n not in ren:
            ren[n] = f'{PFX}{b36(len(ren))}' if MINIFY else f'{PFX}{n}'
    ids = r'(RB|LS|LT|LM|LW|L\d+|r\d+|ts\d+|w\d+|b\d+|s\d+|h\d+|ENG|INI|TS|TI|FO)'
    for b_ in BODIES:
        assert not re.fullmatch(r'#[rwbs]\d+', b_['col']), b_['col']
    def rename_css(t):
        t = re.sub(r'--([A-Za-z_][A-Za-z0-9_]*)', lambda m: '--' + ren.get(m.group(1), m.group(1)), t)
        t = re.sub(r'#' + ids + r'(?![0-9A-Za-z_-])', lambda m: '#' + PFX + m.group(1), t)
        t = re.sub(r'@keyframes (clk|q\d+|v\d+|h[xy]\d+|hf[xy])\{', lambda m: f'@keyframes {PFX}{m.group(1)}{{', t)
        t = re.sub(r'animation-name:([^;}]*)', lambda m: 'animation-name:' + ','.join(
            PFX + x if re.fullmatch(r'clk|q\d+|v\d+|h[xy]\d+|hf[xy]', x) else x for x in m.group(1).split(',')), t)
        return t
    ENG_CSS = rename_css(ENG_CSS)
    if MINIFY:      # spaces are only required around + and - in calc()
        ENG_CSS = ENG_CSS.replace(' * ', '*').replace(' / ', '/')
    ENG_HTML = re.sub(r'id="' + ids + '"', lambda m: f'id="{PFX}{m.group(1)}"', ENG_HTML)
    ENG_ID, INI_ID = PFX + 'ENG', PFX + 'INI'
else:
    ENG_ID, INI_ID = 'ENG', 'INI'

import json as _json
frag = dict(N=N, eng_id=ENG_ID, ini_id=INI_ID, css=ENG_CSS, shared_css='\n'.join(SHARED_CSS), lams=LAMS, html=ENG_HTML,
            scenes=SCENE_NAMES, grav=f(GRAV), nprops=len(g.decl), nlev=NLEV, nreg=len(REGS),
            bodyinfo=[dict(k=b['k'], h=b.get('h'), r=b.get('r')) for b in BODIES],
            consts=dict(VW=VIEW_W, VH=VIEW_H, HS=HS, PERSP=f(PERSP), TILT=f(TILT), TY=f(CAM_TY), DIST=f(CAM_DIST),
                        WX=WX, WZ=WZ, CEIL=CEIL))
dst = sys.argv[1] if len(sys.argv) > 1 else 'engine.json'
open(dst, 'w').write(_json.dumps(frag))
print(f'{dst}: N={N} {len(g.decl)} props ({sum(1 for d in g.decl if d[1] is None)} ungated), {len(groups)} groups, '
      f'{NLEV} levels, {len(REGS)} registers, css {len(ENG_CSS) // 1024} KB', file=sys.stderr)
