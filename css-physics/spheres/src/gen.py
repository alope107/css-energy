#!/usr/bin/env python3
"""Generator for spheres.css: a 3D particle engine in pure CSS (no JavaScript), built for many bodies.

rigid3d spends 100+ registered declarations per body (rotation matrices, SAT, impulses) and keeps a rule per pair of
bodies. A declaration costs 2.5-5 us, a token inside one about 0.1 us. This engine is shaped around that: few
declarations, short writebacks, nothing quadratic.

  bodies     spheres as Verlet particles: the state is the position and the previous position, plus a type (radius and
             colour; negative while held). Contacts are position projections: no impulses, no spin, no rotation.
  slots      the spheres live in N slots kept sorted by x. Slot s only ever meets slots s+1 .. s+K. Each step ends with
             two odd-even compare-and-swap phases folded into the writeback, so a sphere's state moves to the
             neighbouring slot when two cross. Everything that belongs to a sphere travels with it.
  one level  every declaration of a step sits on one element (#LC): custom properties on one element may read each
             other, so the solver needs no chain of levels. The register elements below it read its results.
  step       p   = x + (x - u)(1 - damping) + g h^2                       (prediction)
             k   = max(0, (r_s + r_t) / |p_s - p_t| - 1) per window pair   (K declarations per slot)
             q   = p + w (p Ks - sum_t k p_t),  Ks = sum_t k               (one Jacobi projection)
             m   = q clamped into the tray (mirrored with restitution), friction on the floor and in contact
             n   = m, or x if the step moves the sphere less than EPS: a settled pile stops changing, and with it every
                   restyle (so it costs nothing, without any sleep logic)
             sort: swap flags on n_x for even pairs, then odd pairs, folded into the register rules
  pacing     one step per frame: the second style pass of a frame (Chrome re-runs style after layout when view timelines
             moved) sees TP = now and only holds the registers. Slow frames run in slow motion.

Usage: gen.py [engine.json]   (N spheres, K window, SCENE=name picks the scene that loads first)
"""
import math, sys, os, json, random, re

E_ = os.environ.get
N = int(E_('N', 64))
WX, WZ, CEIL = int(E_('WX', 280)), int(E_('WZ', 180)), int(E_('CEIL', 300))   # tray: |x| < WX, |z| < WZ, -CEIL < y < 0
RMIN, RMAX = float(E_('RMIN', 13)), float(E_('RMAX', 17))
NTYPE = 6
RADII = [RMIN + (RMAX - RMIN) * t / (NTYPE - 1) for t in range(NTYPE)]
# the window must hold every sphere within one diameter in x (spheres/model/model.js: 1.1x the spheres in a slab 2 RMAX
# wide, plus one, had no missed contacts at 128 and 256 with two sort phases per step)
K = min(int(E_('K', max(6, math.ceil(1.15 * N * 2 * RMAX / (2 * WX)) + 1))), N - 1)
RATE = float(E_('RATE', 60))
h = 1 / RATE
GRAV = 1600.0
OMEGA = float(E_('OMEGA', 1.0))      # Jacobi relaxation (the push per pair is OMEGA/2 of the overlap each side)
DAMP = float(E_('DAMP', 0.01))       # velocity damping per step
FRIC = float(E_('FRIC', 0.25))       # share of the horizontal move the floor takes away per step
PFRIC = float(E_('PFRIC', 0.08))     # share of the horizontal move contact with another sphere takes away per step
E = float(E_('E', 0.45))             # restitution against the tray
VTH = float(E_('VTH', 90))           # px/s of approach below which the floor doesn't bounce
EPS = float(E_('EPS', 0.015))        # a step that moves a sphere less than this (px) leaves it where it was
GAS = E_('GAS') == '1'               # benchmark: no gravity, elastic, frictionless: the spheres never come to rest
if GAS:
    DAMP, FRIC, PFRIC, E, VTH = 0.0, 0.0, 0.0, 1.0, 0.0
GRAB_K, GRAB_C, GRAB_AMAX = 900.0, 40.0, 30000.0
HS = 1_000_000                       # register scroller size (px)
RBG = int(E_('RBG', 32))             # readback animations per element (more on one element cost quadratically)
TS_NAMES = 24                        # timeline names per timeline-scope wrapper
ABL = E_('ABL', '').split(',')       # cost bisection: nok (no contacts), nosort
FROZEN = E_('FROZEN')                # benchmark: a register snapshot (tools/snap.js) as constants with a wobble
VIEW_W, VIEW_H = 900, 560            # camera (must match .cam in ui.css; the pick unprojects through it)
PERSP, TILT, CAM_TY, CAM_DIST = 1500.0, -28.0, 95.0, -260.0


def f(v):
    if isinstance(v, str):
        return v
    s = repr(round(float(v), 9))
    return s[:-2] if s.endswith('.0') else s


H_ = f(h)

# ---- scenes: per sphere (x, y, z, vx, vy, vz, type) --------------------------------------------
rng0 = random.Random(5)
TYPES = [rng0.randrange(NTYPE) for _ in range(N)]


def _rain(rng):
    out = []
    for i in range(N):
        r = RADII[TYPES[i]]
        for _ in range(500):
            p = (rng.uniform(-WX + r, WX - r), -rng.uniform(r + 40, CEIL - r), rng.uniform(-WZ + r, WZ - r))
            if all(math.dist(p, o[:3]) > r + RADII[o[6]] + 1 for o in out):
                break
        out.append(p + (rng.uniform(-200, 200), rng.uniform(-100, 100), rng.uniform(-200, 200), TYPES[i]))
    return out


def _heap():
    """a block of spheres in a cubic lattice in the middle of the tray: it collapses and spreads"""
    gap = 2 * RMAX + 0.5
    side = max(2, round((N / 1.5) ** (1 / 3) * 1.25))
    out = []
    for i in range(N):
        a, b = i % side, (i // side) % side
        c = i // (side * side)
        out.append(((a - (side - 1) / 2) * gap, -RMAX - c * gap, (b - (side - 1) / 2) * gap, 0.0, 0.0, 0.0, TYPES[i]))
    return out


def _field():
    """every sphere at rest on the floor in a loose grid (the rest in rows above): loads at rest"""
    gap = 2 * RMAX + 2
    per, rows = int((2 * WX) // gap), int((2 * WZ) // gap)
    out = []
    for i in range(N):
        r = RADII[TYPES[i]]
        row, col = divmod(i, per)
        out.append((-WX + gap / 2 + col * gap, -r if row < rows else -r - 60 - 40 * row,
                    -WZ + gap / 2 + (row % rows) * gap, 0.0, 0.0, 0.0, TYPES[i]))
    return out


SCENES = {'rain': _rain(random.Random(3)), 'heap': _heap(), 'field': _field()}
if E_('SCENE'):
    SCENES = {E_('SCENE'): SCENES[E_('SCENE')], **{k: v for k, v in SCENES.items() if k != E_('SCENE')}}
SCENE_NAMES = [k for k in SCENES if k in E_('SCENE_LIST', 'rain,heap,field').split(',') or k == E_('SCENE')]
SCENES = {k: sorted(v, key=lambda t: t[0]) for k, v in SCENES.items()}

# ---- registers ------------------------------------------------------------------------------
# (name, lo, hi), two per register element (top, left). r0 holds the clock (TP, DB), written from #LT.
# A value v is stored as top = (hi - v) (HS + 1) / (hi - lo) - 1 px in an HS-tall scroller (the element is 1 px tall);
# its view timeline gives the progress (v - lo) / (hi - lo) back, and @keyframes q<k> {from {--v: lo} to {--v: hi}} turns it into v (out of range
# clamps at the ends).
REGS = [('TP', 0, 100), ('DB', 0, 0.1), ('GT', 0, 4), ('GQ', -2000, 2000)]   # GQ: the last step's gravity
XR, YR, ZR = (-WX - 60, WX + 60), (-CEIL - 200, 60), (-WZ - 60, WZ + 60)
for s in range(N):
    REGS += [(f'X{s}', *XR), (f'Y{s}', *YR), (f'Z{s}', *ZR), (f'U{s}', *XR), (f'V{s}', *YR), (f'W{s}', *ZR)]
for s in range(0, N, 2):
    REGS += [(f'T{s}', -NTYPE - 1, NTYPE + 1), ((f'T{s + 1}', -NTYPE - 1, NTYPE + 1) if s + 1 < N else ('TX', 0, 1))]
RIDX = {rn: ri for ri, (rn, lo, hi) in enumerate(REGS)}
NREGEL = (len(REGS) + 1) // 2
NTS = -(-NREGEL // TS_NAMES)
FIELDS = 'XYZUVWT'
INIT = {c: f'i{c.lower()}' for c in FIELDS}   # the scene's start values: --ix0 ...

props = {}   # name -> (syntax, inherits, initial)


def reg(name, syntax='<number>', inherits=True, init='0'):
    props.setdefault(name, (syntax, inherits, init))
    return name


V = lambda n: f'var(--{n})'
for n_ in ('now', 'TP', 'DB', 'NTP', 'NDB'):
    reg(n_, inherits=False)
reg('live', '<integer>', False)
for n_ in ('liv', 'held', 'pick'):
    reg(n_, '<integer>')
for n_ in ('gy', 'att', 'sx', 'sy', 'sxg', 'syg', 'kick', 'rst', 'tk', 'yawg'):
    reg(n_)
for rn, lo, hi in REGS:
    if rn not in ('TP', 'DB'):
        reg(rn)
for s in range(N):
    for c in INIT.values():
        reg(f'{c}{s}')
for c in ('Rx', 'Ry', 'Rz', 'Rt'):    # the render's copies (inherited: the render's children read them)
    reg(c)

# ---- the step: every declaration on #LC ------------------------------------------------------------
LC, LC_ATT, LC_KICK, LC_PICK = [], [], [], []   # ungated; replacing LC while the pointer is down / shaking / picking
# Activity: a slot computes its step only while a sphere within its window moves (ac); otherwise (in) it declares
# copies (p = n = x) for the active slots around it to read. A pair's factor is computed while anything within
# [s-K, s+2K] moves (pa), which covers every active slot that reads it. ACT=0: every slot always computes.
ACT = E_('ACT', '1') == '1'
BLK = {}
G = lambda kind, s: BLK.setdefault((kind, s), []) if ACT else LC


def P(name, expr, where=LC, syntax='<number>', inherits=False):
    """declare name: expr on #LC. Only what the register elements below read is inherited."""
    reg(name, syntax, inherits)
    where.append(f'--{name}:calc({expr})')
    return V(name)


R = lambda s: f'var(--r{s})'
HD = lambda s: f'max(0, -1 * sign(var(--T{s})))'          # held flag (a negative type)
for s in range(N):
    P(f'r{s}', f'{f(RMIN)} + (abs(var(--T{s})) - 1) * {f((RMAX - RMIN) / (NTYPE - 1))}', G('ac', s))
    if ACT:
        P(f'r{s}', f'{f(RMIN)} + (abs(var(--T{s})) - 1) * {f((RMAX - RMIN) / (NTYPE - 1))}', G('in', s))
        for a in 'xyz':
            P(f'p{a}{s}', f'var(--{a.upper()}{s})', G('in', s))
            P(f'n{a}{s}', f'var(--{a.upper()}{s})', G('in', s), inherits=True)

# camera ray (only while the pointer is down): eye and direction in world space
ct, st_ = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
oc = (0.0, -CAM_TY, PERSP + CAM_DIST)
o_y = oc[1] * ct + oc[2] * st_
o_z1 = -oc[1] * st_ + oc[2] * ct
cyw, syw = 'cos(var(--yawg))', 'sin(var(--yawg))'
d_y = f'(var(--syg) * {f(ct)} + {f(-PERSP * st_)})'
d_z1 = f'(-1 * var(--syg) * {f(st_)} + {f(-PERSP * ct)})'
RO = [P('rox', f'-1 * {f(o_z1)} * {syw}', LC_ATT), P('roy', f(o_y), LC_ATT), P('roz', f'{f(o_z1)} * {cyw}', LC_ATT)]
RD = [P('rdx', f'var(--sxg) * {cyw} - {d_z1} * {syw}', LC_ATT), P('rdy', d_y, LC_ATT),
      P('rdz', f'var(--sxg) * {syw} + {d_z1} * {cyw}', LC_ATT)]

# prediction (Verlet), with the grab spring and the shake as alternatives
damp = f(1 - DAMP)
g_ = '0' if GAS else 'var(--gy)'
for s in range(N):
    cur = {a: V(f'{a.upper()}{s}') for a in 'xyz'}
    prev = {'x': V(f'U{s}'), 'y': V(f'V{s}'), 'z': V(f'W{s}')}
    base = {a: f'{cur[a]} + ({cur[a]} - {prev[a]}) * {damp}' + (f' + {g_} * {f(h * h)}' if a == 'y' else '') for a in 'xyz'}
    for i, a in enumerate('xyz'):
        P(f'p{a}{s}', base[a], G('ac', s))
        # held: a spring-damper toward the point on the camera ray at the latched depth GT
        acc = (f'clamp(-{f(GRAB_AMAX)}, {f(GRAB_K)} * ({RO[i]} + var(--GT) * {RD[i]} - {cur[a]}) - '
               f'{f(GRAB_C / h)} * ({cur[a]} - {prev[a]}), {f(GRAB_AMAX)})')
        P(f'p{a}{s}', f'{base[a]} + {acc} * {f(h * h)}', BLK.setdefault(('GH', s), []))
    P(f'px{s}', f'{base["x"]} + 2600 * sin(var(--tk) * 23 + {f(s * 2.1)}) * {f(h * h)}', LC_KICK)
    P(f'py{s}', f'{base["y"]} - 2600 * {f(h * h)}', LC_KICK)
    P(f'pz{s}', f'{base["z"]} + 2600 * cos(var(--tk) * 19 + {f(s * 1.3)}) * {f(h * h)}', LC_KICK)
PV = lambda a, s: f'var(--p{a}{s})'

# contacts: one factor per window pair, one Jacobi projection
PAIRS = [] if 'nok' in ABL else [(s, s + k) for s in range(N) for k in range(1, K + 1) if s + k < N]
for a, b in PAIRS:
    # (1 * hypot: Firefox negates hypot() by negating its arguments, so x - hypot(..) would be x + hypot(..))
    d = f'max(1 * hypot({PV("x", a)} - {PV("x", b)}, {PV("y", a)} - {PV("y", b)}, {PV("z", a)} - {PV("z", b)}), 0.01)'
    P(f'k{a}_{b}', f'max(0, ({R(a)} + {R(b)}) / {d} - 1)', G('pa', a))
NB = {s: [] if ('nok' in ABL or 'noq' in ABL) else [t for t in range(max(0, s - K), min(N, s + K + 1)) if t != s] for s in range(N)}
KK = lambda s, t: f'var(--k{min(s, t)}_{max(s, t)})'
wgt = f(OMEGA / 2)
for s in range(N):
    P(f'Ks{s}', ' + '.join(KK(s, t) for t in NB[s]) or '0', G('ac', s))
    for a in 'xyz':
        terms = ' + '.join(f'{KK(s, t)} * {PV(a, t)}' for t in NB[s]) or '0'
        P(f'q{a}{s}', f'{PV(a, s)} + {wgt} * ({PV(a, s)} * var(--Ks{s}) - ({terms}))', G('ac', s))

# the tray: clamp, mirrored with restitution E (the floor only above VTH of approach, or resting spheres would hop),
# then floor friction and contact friction on the horizontal move
for s in range(N):
    r = R(s)
    Q = {a: V(f'q{a}{s}') for a in 'xyz'}
    cur = {a: V(f'{a.upper()}{s}') for a in 'xyz'}
    onfloor = f'sign(max(0, {Q["y"]} + {r} + 0.5))'
    inct = f'sign(var(--Ks{s}))'
    for a, lim in (('x', WX), ('z', WZ)):
        m = f'{Q[a]} + {f(1 + E)} * (max(0, {r} - {f(lim)} - {Q[a]}) - max(0, {Q[a]} + {r} - {f(lim)}))'
        P(f'm{a}{s}', f'{cur[a]} + ({m} - {cur[a]}) * (1 - {f(FRIC)} * {onfloor}) * (1 - {f(PFRIC)} * {inct})', G('ac', s))
    q = Q['y']
    P(f'my{s}', f'{q} - max(0, {q} + {r}) * (1 + {f(E)} * clamp(0, ({q} - {cur["y"]} - {f(VTH * h)}) / {f(max(VTH * h, 0.001))}, 1))'
                f' + {f(1 + E)} * max(0, {r} - {f(CEIL)} - {q})', G('ac', s))
    P(f'mv{s}', f'sign(max(0, 1 * hypot(var(--mx{s}) - {cur["x"]}, var(--my{s}) - {cur["y"]}, var(--mz{s}) - {cur["z"]})'
                f' - {f(EPS)}) + {HD(s)})', G('ac', s), syntax='<integer>')
    for a in 'xyz':
        P(f'n{a}{s}', f'{cur[a]} + var(--mv{s}) * (var(--m{a}{s}) - {cur[a]})', G('ac', s), inherits=True)

# the pick (pointer down, nothing held): every slot's ray hit; the nearest hit is held from the next step on
for s in range(N):
    c = [V(f'{a}{s}') for a in 'XYZ']
    oc_ = [f'({RO[i]} - {c[i]})' for i in range(3)]
    bq = P(f'gb{s}', ' + '.join(f'{oc_[i]} * {RD[i]}' for i in range(3)), LC_PICK)
    dd = ' + '.join(f'{RD[i]} * {RD[i]}' for i in range(3))
    cc = ' + '.join(f'{oc_[i]} * {oc_[i]}' for i in range(3)) + f' - {R(s)} * {R(s)}'
    disc = P(f'gd{s}', f'{bq} * {bq} - ({dd}) * ({cc})', LC_PICK)
    t = f'(-1 * {bq} - sqrt(max({disc}, 0))) / ({dd})'
    hit = f'sign(max(0, {disc})) * sign(max(0, {t}))'
    P(f'gt{s}', f'{hit} * {t} + (1 - {hit}) * 1000', LC_PICK)
tmin = P('gtm', f"min({', '.join(V(f'gt{s}') for s in range(N))})", LC_PICK)
for s in range(N):
    P(f'gp{s}', f'sign(max(0, {tmin} + 0.0001 - var(--gt{s}))) * sign(max(0, 999 - {tmin}))', LC_PICK, '<integer>', True)
P('NGT', 'var(--GT)', inherits=True)
P('NGT', f'min({tmin}, 4)', LC_PICK, inherits=True)

# ---- the sort (two odd-even phases), folded into the register rules -----------------------------
# what slot s hands to the sort per field: the next position, the current one as the next previous, the type (with the
# held flag set by the pick and cleared on release: only while the pointer is down)
OUT = {'X': lambda s: V(f'nx{s}'), 'Y': lambda s: V(f'ny{s}'), 'Z': lambda s: V(f'nz{s}'),
       'U': lambda s: V(f'X{s}'), 'V': lambda s: V(f'Y{s}'), 'W': lambda s: V(f'Z{s}'), 'T': lambda s: V(f'T{s}')}
OUT_ATT_T = lambda s: f'(abs(var(--T{s})) * (1 - 2 * max(var(--gp{s}), {HD(s)})))'
OUT_REL_T = lambda s: f'abs(var(--T{s}))'
for s in range(0, N - 1, 2):
    P(f'sa{s}', f'sign(max(0, var(--nx{s}) - var(--nx{s + 1})))', G('ws', s), '<integer>', True)
for s in range(N):
    o = OUT['X']
    e = (o(s) if s + 1 >= N else f'{o(s)} + var(--sa{s}) * ({o(s + 1)} - {o(s)})') if s % 2 == 0 else \
        f'{o(s)} + var(--sa{s - 1}) * ({o(s - 1)} - {o(s)})'
    P(f'ax{s}', e, G('ws', s), inherits=True)
for s in range(1, N - 1, 2):
    P(f'sb{s}', f'sign(max(0, var(--ax{s}) - var(--ax{s + 1})))', G('ws', s), '<integer>', True)


def sorted_out(o, s, is_x=False):
    """slot s's next content after both phases, given each slot's output o(s)"""
    if 'nosort' in ABL:
        return o(s)

    def a_(t):
        if t % 2 == 0:
            return o(t) if t + 1 >= N else f'({o(t)} + var(--sa{t}) * ({o(t + 1)} - {o(t)}))'
        return f'({o(t)} + var(--sa{t - 1}) * ({o(t - 1)} - {o(t)}))'
    A = (lambda t: V(f'ax{t}')) if is_x else a_
    if s % 2 == 1:
        return A(s) if s + 1 >= N else f'{A(s)} + var(--sb{s}) * ({A(s + 1)} - {A(s)})'
    return A(s) if s == 0 else f'{A(s)} + var(--sb{s - 1}) * ({A(s - 1)} - {A(s)})'


def mapped(ri, expr):
    """top (or left) for value expr: the 1 px register's view-timeline progress is (HS - top) / (HS + 1)"""
    rn, lo, hi = REGS[ri]
    return f'calc(({f(hi)} - ({expr})) * {f((HS + 1) / (hi - lo))}px - 1px)'


def slot_field(rn):
    m = re.match(r'([XYZUVWT])(\d+)$', rn)
    return (m.group(1), int(m.group(2))) if m else (None, None)


# ---- emit ---------------------------------------------------------------------------------------
out = []
w = out.append
w('/*PROPS*/')
w('@keyframes clk{from{--now:0}to{--now:100}}')
for ri, (rn, lo, hi) in enumerate(REGS):
    w(f'@keyframes q{ri}{{from{{--{rn}:{f(lo)}}}to{{--{rn}:{f(hi)}}}}}')
for t_ in range(NTS):
    ks = range(t_ * TS_NAMES, min(NREGEL, t_ * TS_NAMES + TS_NAMES))
    w(f'#ts{t_}{{timeline-scope:' + ','.join(f'--t{ri}' for k in ks for ri in (2 * k, 2 * k + 1) if ri < len(REGS)) + '}')
# readback: nested elements of RBG animations each, each also declaring its registers' base values
base = {'GT': '0', 'GQ': 'var(--gy)', 'TX': '0'}
for s in range(N):
    for F in FIELDS:
        base[f'{F}{s}'] = f'var(--{INIT[F]}{s})'
ris = list(range(2, len(REGS)))
groups = [ris[k:k + RBG] for k in range(0, len(ris), RBG)]
if FROZEN:
    snap = json.load(open(FROZEN))
    reg('wob')
    w('@keyframes wob{from{--wob:0}to{--wob:1}}#LS0{animation:wob 0.5s linear infinite alternate}')
    # FROZEN_MOVERS=a-b: only slots a..b wobble (0.01 px in x, so they count as moving); the rest stand still
    mv_ = [int(v) for v in E_('FROZEN_MOVERS', '').split('-')] if E_('FROZEN_MOVERS') else None
    def wob(rn):
        if mv_ is None:
            return ' + var(--wob) * 0.0001'
        F_, s_ = slot_field(rn)
        return ' + var(--wob) * 0.01' if F_ == 'X' and mv_[0] <= s_ <= mv_[1] else ''
    for gi, gr in enumerate(groups):
        w(f'#LS{gi}{{' + ''.join(f'--{REGS[ri][0]}:calc({f(snap.get(REGS[ri][0], 0))}{wob(REGS[ri][0])});' for ri in gr) + '}')
else:
    for gi, gr in enumerate(groups):
        w(f'#LS{gi}{{animation-name:{",".join(f"q{ri}" for ri in gr)};animation-duration:{",".join(["auto"] * len(gr))};'
          f'animation-timing-function:linear;animation-fill-mode:both;animation-timeline:{",".join(f"--t{ri}" for ri in gr)};'
          + ''.join(f'--{REGS[ri][0]}:{base[REGS[ri][0]]};' for ri in gr) + '}')
NLS = len(groups)
w('#RB{--sxg:calc(var(--sx) * var(--att));--syg:calc(var(--sy) * var(--att));--yawg:calc(var(--yaw) * var(--att))}')
w('.rz{--sx:0;--sy:0}')
held = 'sign(' + ' + '.join(HD(s) for s in range(N)) + ')'
# the clock: one step per frame (the frame's second pass sees TP = now); slow frames run in slow motion. TP only
# advances while anything moves (or is pressed, shaken, reset, or gravity changed): in a static scene nothing changes
# from pass to pass, so nothing below #LT is restyled at all
live = '1' if FROZEN else 'sign(max(0, var(--now) - var(--TP)))'
moving = ' + '.join(f'abs(var(--X{s_}) - var(--U{s_})) + abs(var(--Y{s_}) - var(--V{s_})) + abs(var(--Z{s_}) - var(--W{s_}))' for s_ in range(N))
anyv = f'sign(max(0, {moving} - 0.0001) + var(--att) + var(--kick) + var(--rst) + abs(var(--gy) - var(--GQ)))'
w(f'#LT{{animation-name:clk,q0,q1;animation-duration:100s,auto,auto;animation-iteration-count:infinite,1,1;'
  f'animation-timing-function:linear;animation-fill-mode:both;animation-timeline:auto,--t0,--t1;--TP:var(--now);--DB:0;'
  f'--live:calc({live});--liv:var(--live);--NTP:calc(var(--TP) + {anyv} * (var(--now) - var(--TP)));--NDB:0;'
  f'--tk:calc(var(--now) * var(--kick));--held:calc({held});--pick:calc(var(--att) * (1 - var(--held)))}}')
w('.rt,.rt *{--NTP:inherit;--NDB:inherit}')
# #LA (step passes only): the moving slots' running count C (C_s = C_(s-1) + moving_s, so a window's count is one
# subtraction), and from it per slot: active (ac: a mover within K slots), copies (in: within 2K, not active), pair
# owner (pa: a mover within [s-K, s+2K], which covers every active slot that reads the pair), writes its registers
# (wr: within K+2; beyond that a slot can't move or be swapped), declares its sort values (ws: within K+4, what a
# writing slot reads two slots away).
# A shake, a pick or a gravity change (GQ holds the last step's gravity) wakes every slot. GH: the held slot + 1.
for n_ in ('C', 'ac', 'in', 'pa', 'ws', 'wr'):
    for s_ in range(N):
        reg(f'{n_}{s_}', '<integer>')
reg('wake', '<integer>')
reg('GH', '<integer>')
la = ['--wake:calc(sign(var(--kick) + abs(var(--gy) - var(--GQ)) + var(--pick)))',
      '--GH:calc(var(--att) * (' + ' + '.join(f'{s_ + 1} * {HD(s_)}' for s_ in range(N)) + '))']
for s_ in range(N):
    mo = (f'sign(max(0, abs(var(--X{s_}) - var(--U{s_})) + abs(var(--Y{s_}) - var(--V{s_})) + abs(var(--Z{s_}) - var(--W{s_}))'
          f' - 0.0001) + {HD(s_)})')
    la.append(f'--C{s_}:calc({mo}' + (f' + var(--C{s_ - 1}))' if s_ else ')'))


def win(s_, lo, hi):
    a_, b_ = s_ + lo - 1, min(N - 1, s_ + hi)
    return f'var(--C{b_})' + (f' - var(--C{a_})' if a_ >= 0 else '') + ' + var(--wake)'


for s_ in range(N):
    la.append(f'--ac{s_}:calc(sign({win(s_, -K, K)}))')
    la.append(f'--in{s_}:calc(sign({win(s_, -2 * K, 2 * K)}) - var(--ac{s_}))')
    la.append(f'--pa{s_}:calc(sign({win(s_, -K, 2 * K)}))')
    la.append(f'--ws{s_}:calc(sign({win(s_, -K - 4, K + 4)}))')
    la.append(f'--wr{s_}:calc(sign({win(s_, -K - 2, K + 2)}))')
w('@container style(--live: 1){#LA{' + ';'.join(la) + '}}')
w('@container style(--liv: 1){#LC{' + ';'.join(LC) + '}}')
if 'nophys' in ABL:     # cost bisection: active slots run no physics, they copy (p = n = x) like the inactive ones
    for s_ in range(N):
        BLK[('ac', s_)] = list(BLK.get(('in', s_), []))
        BLK[('pa', s_)] = []
for s_ in range(N):
        for kind in ('in', 'ac', 'GH', 'pa', 'ws'):
            if BLK.get((kind, s_)):
                q_ = f'style(--GH: {s_ + 1})' if kind == 'GH' else f'style(--{kind}{s_}: 1)'
                w(f'@container {q_}{{#LC{{' + ';'.join(BLK[(kind, s_)]) + '}}')
w('@container style(--liv: 1) and style(--att: 1){#LC{' + ';'.join(LC_ATT) + '}}')
w('@container style(--liv: 1) and style(--kick: 1){#LC{' + ';'.join(LC_KICK) + '}}')
w('@container style(--liv: 1) and style(--pick: 1){#LC{' + ';'.join(LC_PICK) + '}}')
# registers: two per element. Holding (the frame's second pass) is the base rule; a live pass writes the sorted next
# state; reset writes the scene's start values; while the pointer is down the type registers carry the held flag.
pairs = [(2 * k, 2 * k + 1 if 2 * k + 1 < len(REGS) else None) for k in range(1, NREGEL)]


def regrule(k, a, b, val):
    tl = f'view-timeline:--t{a} block' + (f',--t{b} inline;' if b is not None else ';')
    return f'#r{k}{{{tl}top:{mapped(a, val(a))}' + (f';left:{mapped(b, val(b))}' if b is not None else '') + '}'


def hold(ri):
    return V(REGS[ri][0])


def nxt(o_t):
    def v(ri):
        rn = REGS[ri][0]
        F, s = slot_field(rn)
        if F is None:
            return {'GT': V('NGT'), 'GQ': V('gy')}.get(rn, '0')
        return sorted_out(o_t if F == 'T' else OUT[F], s, F == 'X')
    return v


def init(ri):
    rn = REGS[ri][0]
    F, s = slot_field(rn)
    return V(f'{INIT[F]}{s}') if F else ('0' if rn != 'GT' else V('GT'))


w(''.join(regrule(k + 1, a, b, hold) for k, (a, b) in enumerate(pairs)))


def wgate(a, b, extra=''):
    """the condition under which register element (a, b) writes: a live pass, and (ACT) one of its slots near a mover"""
    sl = sorted({slot_field(REGS[r_][0])[1] for r_ in (a, b) if r_ is not None and slot_field(REGS[r_][0])[0]})
    if not ACT or not sl:
        return f'style(--liv: 1){extra}'
    return ' or '.join(f'(style(--wr{s_}: 1){extra})' for s_ in sl)


for k, (a, b) in enumerate(pairs):
    w(f'@container {wgate(a, b)}{{{regrule(k + 1, a, b, nxt(OUT["T"]))}}}')
TPAIRS = [(k + 1, a, b) for k, (a, b) in enumerate(pairs) if slot_field(REGS[a][0])[0] == 'T']
for k, a, b in TPAIRS:
    w(f'@container {wgate(a, b, " and style(--att: 1)")}{{{regrule(k, a, b, nxt(OUT_ATT_T))}}}')
    w(f'@container {wgate(a, b, " and style(--att: 0)")}{{{regrule(k, a, b, nxt(OUT_REL_T))}}}')
w('@container style(--rst: 1){' + ''.join(regrule(k + 1, a, b, init) for k, (a, b) in enumerate(pairs)) + '}')
w(f'#r0{{view-timeline:--t0 block,--t1 inline;top:{mapped(0, "var(--NTP)")};left:{mapped(1, "var(--NDB)")}}}')
# render: per slot a wrapper (.bw) that reads its sphere's X, Y, Z, T registers with its own animations into inherited
# properties (--Rx ...), holding a billboard disc and a shadow. (Elements that read the solver's properties cost tens
# of us each per pass; non-inherited copies pulled into the children with an explicit inherit cost about 100 us each.)
RCOMP = {'X': 'Rx', 'Y': 'Ry', 'Z': 'Rz', 'T': 'Rt'}
for ri, (rn, lo, hi) in enumerate(REGS):
    F, s = slot_field(rn)
    if F in RCOMP:
        w(f'@keyframes v{ri}{{from{{--{RCOMP[F]}:{f(lo)}}}to{{--{RCOMP[F]}:{f(hi)}}}}}')
RENDER = E_('RENDER', 'anim')   # anim: the wrappers read the registers with their own animations | inh: the render sits in
                                # the readback chain and copies the solver's values
for s in range(N):
    rr = [RIDX[f'{c}{s}'] for c in 'XYZT']
    if RENDER == 'inh':
        w(f'#w{s}{{--Rx:var(--X{s});--Ry:var(--Y{s});--Rz:var(--Z{s});--Rt:var(--T{s})}}')
    else:
        w(f'#w{s}{{animation-name:{",".join(f"v{r_}" for r_ in rr)};animation-timeline:{",".join(f"--t{r_}" for r_ in rr)};'
          f'--Rx:var(--ix{s});--Ry:var(--iy{s});--Rz:var(--iz{s});--Rt:var(--it{s})}}')
sc = f'(({f(RMIN)} + (abs(var(--Rt)) - 1) * {f((RMAX - RMIN) / (NTYPE - 1))}) / {f(RMAX)})'
w('.bw{animation-duration:auto;animation-timing-function:linear;animation-fill-mode:both;'
  'transform:translate3d(calc(var(--Rx) * 1px),calc(var(--Ry) * 1px),calc(var(--Rz) * 1px))}'
  f'.bw .sp{{transform:rotateY(calc(var(--yaw) * -1rad)) rotateX({f(-TILT)}deg) translateZ(calc({f(RMAX * 0.6)}px * {sc})) scale(calc{sc});'
  '--c:hsl(calc(abs(var(--Rt)) * 61 + 10) 72% 56%);--hl:max(0, -1 * sign(var(--Rt)))}'
  f'.bw .sh{{transform:translateY(calc(var(--Ry) * -1px - 0.5px)) rotateX(90deg) scale(calc({sc} * (1 + var(--Ry) / -900)));'
  'opacity:calc(0.55 + var(--Ry) / 700)}')
ENG_CSS = '\n'.join(out).replace('/*PROPS*/', '\n'.join(
    f"@property --{n_}{{syntax:'{syn}';inherits:{'true' if inh else 'false'};initial-value:{init_}}}"
    for n_, (syn, inh, init_) in props.items()))

ENG_HTML = ('<div class="eng" id="ENG"><div class="ini" id="INI"><div class="ptr">' + ''.join(f'<div class="lv" id="ts{t_}">' for t_ in range(NTS)) +
            '<div class="lv" id="RB"><div class="lv rz">' + ''.join(f'<div class="lv" id="LS{gi}">' for gi in range(NLS)) +
            '<div class="lv" id="LT"><div class="regs rt"><div class="sc"><i id="r0"></i></div></div>'
            '<div class="lv" id="LA"><div class="lv" id="LC"><div class="regs"><div class="sc">' + ''.join(f'<i id="r{k}"></i>' for k in range(1, NREGEL)) +
            '</div></div></div></div></div>' + ('' if RENDER == 'inh' else '</div>' * NLS + '</div></div>') +
            '<div class="view"><div class="cam"><i class="floor"></i><i class="ceil"></i><i class="post p1"></i><i class="post p2"></i>'
            '<i class="post p3"></i><i class="post p4"></i><i class="rail rb"></i><i class="rail rl"></i><i class="rail rr"></i><i class="rail rn"></i>' +
            ''.join(f'<div class="bw" id="w{s}"><i class="sh"></i><i class="sp"></i></div>' for s in range(N)) +
            '</div></div>' + ('</div>' * NLS + '</div></div>' if RENDER == 'inh' else '') + '</div>' * NTS + '</div></div></div>')


def scene_decls(sn):
    out_ = []
    for s, (x, y, z, vx, vy, vz, ty) in enumerate(SCENES[sn]):
        if vx == vy == vz == 0 and y < -RADII[ty] - 0.5:
            vy = 1.0     # (a sphere at rest in mid-air would not be moving, so nothing would ever compute its fall)
        out_.append(f'--ix{s}:{f(x)};--iy{s}:{f(y)};--iz{s}:{f(z)};--iu{s}:{f(x - vx * h)};--iv{s}:{f(y - vy * h)};'
                    f'--iw{s}:{f(z - vz * h)};--it{s}:{ty + 1}')
    return ';'.join(out_)


SC_CSS = [f'#INI{{{scene_decls(SCENE_NAMES[0])}}}']
for sn in SCENE_NAMES[1:]:
    SC_CSS.append(f'#app:has(#sc-{sn}:checked) #INI{{{scene_decls(sn)}}}')
for sn in SCENE_NAMES:
    SC_CSS.append(f'#app:has(#lb-{sn}:active) #INI{{{scene_decls(sn)}}}')
ENG_CSS += '\n' + '\n'.join(SC_CSS)

PFX = E_('PFX', '')
if PFX:
    ids = r'RB|LS\d+|LT|LA|LC|r\d+|ts\d+|w\d+|ENG|INI'
    ENG_HTML = re.sub(r'id="(' + ids + ')"', lambda m: f'id="{PFX}{m.group(1)}"', ENG_HTML)
    ENG_CSS = re.sub(r'#(' + ids + r')\b', lambda m: f'#{PFX}{m.group(1)}', ENG_CSS)
    names = sorted((n for n in props if n not in ('gy', 'att', 'sx', 'sy', 'kick', 'rst', 'yaw')), key=len, reverse=True)
    ENG_CSS = re.sub(r'--(' + '|'.join(map(re.escape, names)) + r')\b', lambda m: f'--{PFX}{m.group(1)}', ENG_CSS)
    ENG_CSS = re.sub(r'--t(\d+)\b', lambda m: f'--{PFX}t{m.group(1)}', ENG_CSS)
    ENG_CSS = re.sub(r'\b(q\d+|v\d+|clk|wob)\b(?=[{,;])', lambda m: f'{PFX}{m.group(1)}', ENG_CSS)
    ENG_ID, INI_ID = PFX + 'ENG', PFX + 'INI'
else:
    ENG_ID, INI_ID = 'ENG', 'INI'
NDECL = len(LC) + sum(len(v) for v in BLK.values())
frag = dict(N=N, K=K, eng_id=ENG_ID, ini_id=INI_ID, css=ENG_CSS, html=ENG_HTML, scenes=SCENE_NAMES, grav=f(GRAV),
            ndecl=NDECL, nreg=len(REGS),
            consts=dict(VW=VIEW_W, VH=VIEW_H, HS=HS, PERSP=f(PERSP), TILT=f(TILT), TY=f(CAM_TY), DIST=f(CAM_DIST),
                        WX=WX, WZ=WZ, CEIL=CEIL, RMIN=RMIN, RMAX=RMAX, NTYPE=NTYPE, RATE=RATE))
dst = sys.argv[1] if len(sys.argv) > 1 else 'engine.json'
open(dst, 'w').write(json.dumps(frag))
print(f'{dst}: N={N} K={K} {NDECL} step declarations ({NDECL / N:.1f} per slot, gated by activity), {len(PAIRS)} window pairs, '
      f'{len(REGS)} registers in {NLS} readback groups, css {len(ENG_CSS) // 1024} KB', file=sys.stderr)
