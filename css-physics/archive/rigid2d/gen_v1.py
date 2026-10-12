#!/usr/bin/env python3
"""Generator for a pure-CSS rigid body physics engine (no JavaScript in the output).

Loop per style pass:
  readback  : state (x, y, angle, vx, vy, omega per body) comes from view-timeline
              progress of hidden "register" elements (layout -> animation -> custom prop)
  solve     : S substeps of XPBD-style contact resolution as a DAG of registered
              custom properties on #world
  writeback : next state sets each register's `top`; Chrome re-samples the view
              timelines after layout, which closes the loop without a cycle.
"""
import math, sys

W, H = 800, 500          # arena, sim units (1 unit = 1 px at scale 1)
S = int(sys.argv[1]) if len(sys.argv) > 1 else 4   # substeps per pass
HS = 16_000_000          # register scroller height in px (LayoutUnit max ~33.5M)
GRAV = 1400.0
MU = 0.5                 # friction
E = 0.35                 # restitution
BOUNCE_THR = 60.0        # min approach speed for restitution
LIN_DAMP = 0.05          # per second
ANG_DAMP = 0.4
DENS = 0.001

# ---- bodies ---------------------------------------------------------------
# kind, size, color; positions come from scenes
BODIES = [
    dict(k='box', hw=30, hh=30, col='#f2b134'),
    dict(k='box', hw=30, hh=30, col='#ed6a5a'),
    dict(k='box', hw=30, hh=30, col='#4ecdc4'),
    dict(k='box', hw=110, hh=11, col='#c9c9c9'),
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
        b['m'] = DENS * 4 * b['hw'] * b['hh']
        b['I'] = b['m'] * ((2*b['hw'])**2 + (2*b['hh'])**2) / 12
        b['rad'] = math.hypot(b['hw'], b['hh'])
    else:
        b['m'] = DENS * math.pi * b['r']**2
        b['I'] = 0.5 * b['m'] * b['r']**2
        b['rad'] = b['r']
    b['im'] = 1 / b['m']
    b['ii'] = 1 / b['I']

# scenes: list of (x, y, a, vx, vy, w) per body
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
    'seesaw': [
        (170, 440, 0, 0, 0, 0), (170, 380, 0, 0, 0, 0), (620, 470, 0, 0, 0, 0),
        (400, 450, 0.0, 0, 0, 0), (400, 408, 0, 0, 0, 0),
        (230, 380, 0, 0, 0, 0), (560, 60, 0, 0, 0, 0), (610, 200, 0, 0, 0, 0),
        (330, 300, 0, 0, 0, 0), (470, 300, 0, 0, 0, 0),
    ],
}
SCENE_NAMES = list(SCENES)

# register value ranges
RANGES = dict(x=(-150, W + 150), y=(-150, H + 150), a=(0, 2 * math.pi),
              vx=(-6000, 6000), vy=(-6000, 6000), w=(-250, 250))
FIELDS = ['x', 'y', 'a', 'vx', 'vy', 'w']

def f(v):
    if isinstance(v, str):
        return v
    s = repr(float(v))
    if s.endswith('.0'):
        s = s[:-2]
    return s

class Gen:
    def __init__(self):
        self.props = []      # (name, syntax, inherits, initial)
        self.decl = []       # (name, expr) on #world
        self.seen = set()

    def reg(self, name, inherits=False, init='0', syntax='<number>'):
        if name in self.seen:
            raise ValueError(name)
        self.seen.add(name)
        self.props.append((name, syntax, inherits, init))
        return f'var(--{name})'

    def P(self, name, expr, inherits=False):
        v = self.reg(name, inherits)
        self.decl.append((name, expr))
        return v

g = Gen()
V = lambda n: f'var(--{n})'

# ---- time / substep size ---------------------------------------------------
g.reg('now')                       # clock animation, seconds mod 100
TP = g.reg('TP')                   # readback: previous pass time
DB = g.reg('DB')                   # readback: unconsumed time debt
raw = g.P('raw', f'mod(var(--now) - {TP} + 100, 100)')
avail = g.P('avail', f'min({DB} + {raw}, 0.05)')
cons = g.P('cons', f'{avail} * (1 - 0.5 * sign({raw}))')
live = g.P('live', f'sign(max(0, {cons} - 0.0002))')
consE = g.P('consE', f'{live} * {cons}')
h = g.P('h', f'max({consE} / {S}, 0.000001)')

# controls (set by :has() rules, defaults here)
CTRL = ['gx', 'gy', 'att', 'mx', 'my', 'kick', 'rst']
for c in CTRL:
    g.reg(c, inherits=True)
# scene init values
for i in range(N):
    for fl in FIELDS:
        g.reg(f'i{fl}{i}')

# current state readback names
def cur(i, fl):
    return V(f'{fl.upper()}{i}')
for i in range(N):
    for fl in FIELDS:
        g.reg(f'{fl.upper()}{i}')

# ---- contact list (static) ------------------------------------------------
boxes = [i for i, b in enumerate(BODIES) if b['k'] == 'box']
cirs = [i for i, b in enumerate(BODIES) if b['k'] == 'cir']
CORN = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
WALLS = ['F', 'L', 'R', 'C']   # floor, left, right, ceiling
contacts = []
for i in boxes:
    for j in range(4):
        for wl in WALLS:
            contacts.append(('cw', i, j, wl))
for i in cirs:
    for wl in WALLS:
        contacts.append(('rw', i, wl))
for ai, a in enumerate(boxes):
    for b in boxes[ai + 1:]:
        for j in range(4):
            contacts.append(('bb', a, j, b))   # corner j of a inside b
            contacts.append(('bb', b, j, a))
for i in cirs:
    for b in boxes:
        contacts.append(('bc', i, b))
for ai, a in enumerate(cirs):
    for b in cirs[ai + 1:]:
        contacts.append(('cc', a, b))

def wall_n(wl):
    return {'F': (0, -1), 'L': (1, 0), 'R': (-1, 0), 'C': (0, 1)}[wl]

# ---- substeps -------------------------------------------------------------
def state_names(k):
    """names of the state entering substep k"""
    if k == 0:
        return {(i, fl): cur(i, fl) for i in range(N) for fl in FIELDS}
    return {(i, fl): V(f's{k}{fl}{i}') for i in range(N) for fl in FIELDS}

st = state_names(0)
for k in range(S):
    p = f'k{k}_'
    B = {}
    for i, b in enumerate(BODIES):
        X, Y, A = st[(i, 'x')], st[(i, 'y')], st[(i, 'a')]
        VX, VY, WW = st[(i, 'vx')], st[(i, 'vy')], st[(i, 'w')]
        # external accel: gravity + pointer attractor + kick
        ddx = g.P(f'{p}dd{i}', f'max(hypot(var(--mx) - {X}, var(--my) - {Y}), 40)')
        axe = (f'var(--gx) + var(--att) * 5200 * (var(--mx) - {X}) / {ddx}'
               f' + var(--kick) * 2600 * sin(var(--now) * 23 + {i * 2.1:.2f})')
        aye = (f'var(--gy) + var(--att) * 5200 * (var(--my) - {Y}) / {ddx}'
               f' - var(--kick) * 3400')
        damp = f'(1 - {LIN_DAMP} * {h} - var(--att) * 2.2 * {h})'
        u = g.P(f'{p}u{i}', f'({VX} + ({axe}) * {h}) * {damp}')
        v = g.P(f'{p}v{i}', f'({VY} + ({aye}) * {h}) * {damp}')
        om = g.P(f'{p}o{i}', f'{WW} * (1 - {ANG_DAMP} * {h})')
        px = g.P(f'{p}px{i}', f'{X} + {u} * {h}')
        py = g.P(f'{p}py{i}', f'{Y} + {v} * {h}')
        pa = g.P(f'{p}pa{i}', f'{A} + {om} * {h}')
        d = dict(u=u, v=v, o=om, px=px, py=py, pa=pa, X=X, Y=Y, A=A)
        if b['k'] == 'box':
            c = g.P(f'{p}c{i}', f'cos({pa})')
            s_ = g.P(f'{p}s{i}', f'sin({pa})')
            d['c'], d['s'] = c, s_
            q = []
            for j, (sx, sy) in enumerate(CORN):
                lx, ly = sx * b['hw'], sy * b['hh']
                qx = g.P(f'{p}qx{i}_{j}', f'{px} + {c} * {f(lx)} - {s_} * {f(ly)}')
                qy = g.P(f'{p}qy{i}_{j}', f'{py} + {s_} * {f(lx)} + {c} * {f(ly)}')
                q.append((qx, qy))
            d['q'] = q
        B[i] = d

    acc = {i: dict(px=[], py=[], tq=[], cnt=[], rest=[]) for i in range(N)}
    cdata = []
    for ci, ct in enumerate(contacts):
        cp = f'{p}c{ci}_'
        kind = ct[0]
        if kind == 'cw':
            _, a, j, wl = ct
            bb = None
            qx, qy = B[a]['q'][j]
            nx, ny = wall_n(wl)
            dep = {'F': f'{qy} - {H}', 'L': f'-1 * {qx}', 'R': f'{qx} - {W}', 'C': f'-1 * {qy}'}[wl]
            dd = g.P(cp + 'd', dep)
            cx_, cy_ = qx, qy
            nx, ny = f(nx), f(ny)
        elif kind == 'rw':
            _, a, wl = ct
            bb = None
            r = BODIES[a]['r']
            px, py = B[a]['px'], B[a]['py']
            nxv, nyv = wall_n(wl)
            dep = {'F': f'{py} + {r} - {H}', 'L': f'{r} - {px}', 'R': f'{px} + {r} - {W}', 'C': f'{r} - {py}'}[wl]
            dd = g.P(cp + 'd', dep)
            cx_ = f'({px} - {f(nxv * r)})'
            cy_ = f'({py} - {f(nyv * r)})'
            nx, ny = f(nxv), f(nyv)
        elif kind == 'bb':
            _, a, j, bb = ct
            qx, qy = B[a]['q'][j]
            ob = BODIES[bb]
            cB, sB, pxB, pyB = B[bb]['c'], B[bb]['s'], B[bb]['px'], B[bb]['py']
            ex = g.P(cp + 'ex', f'{qx} - {pxB}')
            ey = g.P(cp + 'ey', f'{qy} - {pyB}')
            lx = g.P(cp + 'lx', f'{cB} * {ex} + {sB} * {ey}')
            ly = g.P(cp + 'ly', f'{cB} * {ey} - {sB} * {ex}')
            pnx = g.P(cp + 'pnx', f'{ob["hw"]} - abs({lx})')
            pny = g.P(cp + 'pny', f'{ob["hh"]} - abs({ly})')
            dd = g.P(cp + 'd', f'min({pnx}, {pny})')
            fx = g.P(cp + 'fx', f'sign(max(0, {pny} - {pnx}))')
            nlx = g.P(cp + 'nlx', f'{fx} * sign({lx})')
            nly = g.P(cp + 'nly', f'(1 - {fx}) * sign({ly})')
            nx = g.P(cp + 'nx', f'{cB} * {nlx} - {sB} * {nly}')
            ny = g.P(cp + 'ny', f'{sB} * {nlx} + {cB} * {nly}')
            cx_, cy_ = qx, qy
        elif kind == 'bc':
            _, a, bb = ct
            r = BODIES[a]['r']
            ob = BODIES[bb]
            cB, sB, pxB, pyB = B[bb]['c'], B[bb]['s'], B[bb]['px'], B[bb]['py']
            pxA, pyA = B[a]['px'], B[a]['py']
            ex = g.P(cp + 'ex', f'{pxA} - {pxB}')
            ey = g.P(cp + 'ey', f'{pyA} - {pyB}')
            lx = g.P(cp + 'lx', f'{cB} * {ex} + {sB} * {ey}')
            ly = g.P(cp + 'ly', f'{cB} * {ey} - {sB} * {ex}')
            gx_ = g.P(cp + 'gx', f'{lx} - clamp({-ob["hw"]}, {lx}, {ob["hw"]})')
            gy_ = g.P(cp + 'gy', f'{ly} - clamp({-ob["hh"]}, {ly}, {ob["hh"]})')
            dist = g.P(cp + 'dist', f'hypot({gx_}, {gy_})')
            o = g.P(cp + 'o', f'sign({dist})')
            pnx = g.P(cp + 'pnx', f'{ob["hw"]} - abs({lx})')
            pny = g.P(cp + 'pny', f'{ob["hh"]} - abs({ly})')
            fx = g.P(cp + 'fx', f'sign(max(0, {pny} - {pnx}))')
            nlx = g.P(cp + 'nlx', f'{o} * {gx_} / max({dist}, 0.000000001) + (1 - {o}) * {fx} * sign({lx})')
            nly = g.P(cp + 'nly', f'{o} * {gy_} / max({dist}, 0.000000001) + (1 - {o}) * (1 - {fx}) * sign({ly})')
            dd = g.P(cp + 'd', f'{o} * ({r} - {dist}) + (1 - {o}) * ({r} + min({pnx}, {pny}))')
            nx = g.P(cp + 'nx', f'{cB} * {nlx} - {sB} * {nly}')
            ny = g.P(cp + 'ny', f'{sB} * {nlx} + {cB} * {nly}')
            cx_ = f'({pxA} - {nx} * {r})'
            cy_ = f'({pyA} - {ny} * {r})'
        elif kind == 'cc':
            _, a, bb = ct
            ra, rb = BODIES[a]['r'], BODIES[bb]['r']
            ex = g.P(cp + 'ex', f'{B[a]["px"]} - {B[bb]["px"]}')
            ey = g.P(cp + 'ey', f'{B[a]["py"]} - {B[bb]["py"]}')
            dist = g.P(cp + 'dist', f'max(hypot({ex}, {ey}), 0.000000001)')
            nx = g.P(cp + 'nx', f'{ex} / {dist}')
            ny = g.P(cp + 'ny', f'{ey} / {dist}')
            dd = g.P(cp + 'd', f'{ra + rb} - {dist}')
            cx_ = f'({B[a]["px"]} - {nx} * {ra})'
            cy_ = f'({B[a]["py"]} - {ny} * {ra})'

        A_, b_ = BODIES[a], (BODIES[bb] if bb is not None else None)
        act = g.P(cp + 'act', f'sign(max(0, {dd}))')
        rax = g.P(cp + 'rax', f'{cx_} - {B[a]["px"]}')
        ray = g.P(cp + 'ray', f'{cy_} - {B[a]["py"]}')
        cna = g.P(cp + 'cna', f'{rax} * {ny} - {ray} * {nx}')     # r x n
        cta = g.P(cp + 'cta', f'{rax} * {nx} + {ray} * {ny}')     # r x t, t = (-ny, nx)
        wn = f'{f(A_["im"])} + {cna} * {cna} * {f(A_["ii"])}'
        wt = f'{f(A_["im"])} + {cta} * {cta} * {f(A_["ii"])}'
        # contact point velocity of A
        vax = f'({B[a]["u"]} - {B[a]["o"]} * {ray})'
        vay = f'({B[a]["v"]} + {B[a]["o"]} * {rax})'
        if bb is not None:
            rbx = g.P(cp + 'rbx', f'{cx_} - {B[bb]["px"]}')
            rby = g.P(cp + 'rby', f'{cy_} - {B[bb]["py"]}')
            cnb = g.P(cp + 'cnb', f'{rbx} * {ny} - {rby} * {nx}')
            ctb = g.P(cp + 'ctb', f'{rbx} * {nx} + {rby} * {ny}')
            wn += f' + {f(b_["im"])} + {cnb} * {cnb} * {f(b_["ii"])}'
            wt += f' + {f(b_["im"])} + {ctb} * {ctb} * {f(b_["ii"])}'
            dvx = f'({vax} - ({B[bb]["u"]} - {B[bb]["o"]} * {rby}))'
            dvy = f'({vay} - ({B[bb]["v"]} + {B[bb]["o"]} * {rbx}))'
        else:
            dvx, dvy = vax, vay
        wnv = g.P(cp + 'wn', wn)
        wtv = g.P(cp + 'wt', wt)
        lam = g.P(cp + 'lam', f'{act} * {dd} / {wnv}')
        vt = g.P(cp + 'vt', f'{dvy} * {nx} - {dvx} * {ny}')
        vn = g.P(cp + 'vn', f'{dvx} * {nx} + {dvy} * {ny}')
        lt = g.P(cp + 'lt', f'clamp(-{MU} * {lam}, -1 * {vt} * {h} / {wtv}, {MU} * {lam})')
        Px = g.P(cp + 'Px', f'{lam} * {nx} - {lt} * {ny}')
        Py = g.P(cp + 'Py', f'{lam} * {ny} + {lt} * {nx}')
        acc[a]['px'].append(Px); acc[a]['py'].append(Py)
        acc[a]['tq'].append(f'({rax} * {Py} - {ray} * {Px})')
        acc[a]['cnt'].append(act)
        if bb is not None:
            acc[bb]['px'].append(f'(-1 * {Px})'); acc[bb]['py'].append(f'(-1 * {Py})')
            acc[bb]['tq'].append(f'({rby} * {Px} - {rbx} * {Py})')
            acc[bb]['cnt'].append(act)
        cdata.append(dict(a=a, bb=bb, act=act, nx=nx, ny=ny, rax=rax, ray=ray,
                          rbx=rbx if bb is not None else None,
                          rby=rby if bb is not None else None,
                          cna=cna, cnb=cnb if bb is not None else None,
                          wn=wnv, vn=vn, cp=cp))

    # position update + velocity rederivation
    post = {}
    for i, b in enumerate(BODIES):
        d = B[i]
        sm = lambda L: ' + '.join(L) if L else '0'
        cnt = g.P(f'{p}n{i}', f'max(1, {sm(acc[i]["cnt"])})')
        nx_ = g.P(f'{p}nx{i}', f'{d["px"]} + ({sm(acc[i]["px"])}) * {f(b["im"])} / {cnt}')
        ny_ = g.P(f'{p}ny{i}', f'{d["py"]} + ({sm(acc[i]["py"])}) * {f(b["im"])} / {cnt}')
        na_ = g.P(f'{p}na{i}', f'{d["pa"]} + ({sm(acc[i]["tq"])}) * {f(b["ii"])} / {cnt}')
        vx_ = g.P(f'{p}vx{i}', f'({nx_} - {d["X"]}) / {h}')
        vy_ = g.P(f'{p}vy{i}', f'({ny_} - {d["Y"]}) / {h}')
        w_ = g.P(f'{p}w{i}', f'({na_} - {d["A"]}) / {h}')
        post[i] = dict(x=nx_, y=ny_, a=na_, vx=vx_, vy=vy_, w=w_, cnt=cnt)

    # restitution velocity pass
    racc = {i: dict(vx=[], vy=[], w=[]) for i in range(N)}
    for cd in cdata:
        a, bb, cp = cd['a'], cd['bb'], cd['cp']
        nx, ny = cd['nx'], cd['ny']
        pa_, pb_ = post[a], (post[bb] if bb is not None else None)
        dvx = f'({pa_["vx"]} - {pa_["w"]} * {cd["ray"]})'
        dvy = f'({pa_["vy"]} + {pa_["w"]} * {cd["rax"]})'
        if bb is not None:
            dvx = f'({dvx} - ({pb_["vx"]} - {pb_["w"]} * {cd["rby"]}))'
            dvy = f'({dvy} - ({pb_["vy"]} + {pb_["w"]} * {cd["rbx"]}))'
        vn2 = g.P(cp + 'vn2', f'{dvx} * {nx} + {dvy} * {ny}')
        bf = f'{cd["act"]} * sign(max(0, -1 * {cd["vn"]} - {BOUNCE_THR}))'
        J = g.P(cp + 'J', f'{bf} * max(0, -{E} * {cd["vn"]} - {vn2}) / {cd["wn"]}')
        racc[a]['vx'].append(f'{J} * {nx}'); racc[a]['vy'].append(f'{J} * {ny}')
        racc[a]['w'].append(f'{J} * {cd["cna"]}')
        if bb is not None:
            racc[bb]['vx'].append(f'(-1 * {J} * {nx})'); racc[bb]['vy'].append(f'(-1 * {J} * {ny})')
            racc[bb]['w'].append(f'(-1 * {J} * {cd["cnb"]})')

    new = {}
    for i, b in enumerate(BODIES):
        q = post[i]
        sm = lambda L: ' + '.join(L) if L else '0'
        new[(i, 'x')] = g.P(f's{k+1}x{i}', q['x'])
        new[(i, 'y')] = g.P(f's{k+1}y{i}', q['y'])
        new[(i, 'a')] = g.P(f's{k+1}a{i}', q['a'])
        new[(i, 'vx')] = g.P(f's{k+1}vx{i}', f'{q["vx"]} + ({sm(racc[i]["vx"])}) * {f(b["im"])} / {q["cnt"]}')
        new[(i, 'vy')] = g.P(f's{k+1}vy{i}', f'{q["vy"]} + ({sm(racc[i]["vy"])}) * {f(b["im"])} / {q["cnt"]}')
        new[(i, 'w')] = g.P(f's{k+1}w{i}', f'{q["w"]} + ({sm(racc[i]["w"])}) * {f(b["ii"])} / {q["cnt"]}')
    st = new

# ---- final: gate by live/reset, clamp, wrap angle ---------------------------
for i in range(N):
    for fl in FIELDS:
        lo, hi = RANGES[fl]
        c0 = cur(i, fl)
        out = st[(i, fl)]
        expr = f'{live} * {out} + (1 - {live}) * {c0}'
        if fl == 'a':
            expr = f'mod({expr}, {f(2 * math.pi)})'
        expr = f'var(--rst) * var(--i{fl}{i}) + (1 - var(--rst)) * clamp({lo}, {expr}, {hi})'
        g.P(f'N{fl}{i}', expr, inherits=True)
g.P('NTP', 'var(--now)', inherits=True)
g.P('NDB', f'clamp(0, {avail} - {consE}, 0.1)', inherits=True)

# registers: (readback name, next name, lo, hi)
REGS = [('TP', 'NTP', 0, 100), ('DB', 'NDB', 0, 0.1)]
for i in range(N):
    for fl in FIELDS:
        lo, hi = RANGES[fl]
        REGS.append((f'{fl.upper()}{i}', f'N{fl}{i}', lo, hi))

# ---- emit -------------------------------------------------------------------
out = []
w = out.append
for name, syn, inh, init in g.props:
    w(f"@property --{name}{{syntax:'{syn}';inherits:{'true' if inh else 'false'};initial-value:{init}}}")
w('@keyframes clk{from{--now:0}to{--now:100}}')
for ri, (rn, nn, lo, hi) in enumerate(REGS):
    w(f'@keyframes q{ri}{{from{{--{rn}:{f(lo)}}}to{{--{rn}:{f(hi)}}}}}')

names = ['clk'] + [f'q{ri}' for ri in range(len(REGS))]
tl = ['auto'] + [f'--t{ri}' for ri in range(len(REGS))]
dur = ['100s'] + ['auto'] * len(REGS)
itc = ['infinite'] + ['1'] * len(REGS)
w('#world{')
w(f'timeline-scope:{",".join(tl[1:])};')
w(f'animation-name:{",".join(names)};')
w(f'animation-duration:{",".join(dur)};')
w(f'animation-iteration-count:{",".join(itc)};')
w('animation-timing-function:linear;animation-fill-mode:both;')
w(f'animation-timeline:{",".join(tl)};')
# first-frame base values for readback props (before timelines resolve)
w('--TP:var(--now);--DB:0;')
for i in range(N):
    for fl in FIELDS:
        w(f'--{fl.upper()}{i}:var(--i{fl}{i});')
w(f'--gx:0;--gy:{GRAV};--att:0;--mx:{W/2};--my:{H/2};--kick:0;--rst:0;')
for name, expr in g.decl:
    w(f'--{name}:calc({expr});')
w('}')

# scene init values
def scene_decls(sn):
    return ';'.join(f'--i{fl}{i}:{f(val)}' for i in range(N)
                    for fl, val in zip(FIELDS, SCENES[sn][i]))
for si, sn in enumerate(SCENE_NAMES):
    sel = '#world' if si == 0 else f'#world:has(#sc-{sn}:checked)'
    w(f'{sel}{{{scene_decls(sn)}}}')
# pressing a scene label loads that scene immediately (before the radio flips on mouseup)
for sn in SCENE_NAMES:
    w(f'#world:has(#lb-{sn}:active){{{scene_decls(sn)}}}')

for ri, (rn, nn, lo, hi) in enumerate(REGS):
    w(f'#r{ri}{{view-timeline:--t{ri};top:calc(({HS} - clamp(0, (var(--{nn}) - {f(lo)}) / {f(hi - lo)}, 1) * {HS + 1}) * 1px)}}')

PHYS_CSS = '\n'.join(out)

body_css = []
body_html = []
for i, b in enumerate(BODIES):
    if b['k'] == 'box':
        wv, hv = 2 * b['hw'], 2 * b['hh']
        cls = 'bx'
    else:
        wv = hv = 2 * b['r']
        cls = 'ci'
    body_css.append(
        f'#b{i}{{width:calc({wv} * var(--u));height:calc({hv} * var(--u));--c:{b["col"]};'
        f'transform:translate(calc(var(--Nx{i}) * var(--u) - 50%),calc(var(--Ny{i}) * var(--u) - 50%)) rotate(calc(var(--Na{i}) * 1rad))}}')
    body_html.append(f'<i class="b {cls}" id="b{i}"></i>')

reg_html = ''.join(f'<i id="r{ri}"></i>' for ri in range(len(REGS)))

# pointer grid: GC x GR hover cells
GC, GR = 40, 25
grid_css = []
for cx in range(GC):
    grid_css.append(f'#world:has(.gr>i:nth-child({GC}n+{cx + 1}):hover){{--mx:{f((cx + 0.5) * W / GC)}}}')
for ry in range(GR):
    grid_css.append(f'#world:has(.gr>i:nth-child(n+{ry * GC + 1}):nth-child(-n+{(ry + 1) * GC}):hover){{--my:{f((ry + 0.5) * H / GR)}}}')
grid_html = '<i></i>' * (GC * GR)

UI_CSS = open(__file__.replace('gen.py', 'ui.css')).read()
UI_CSS = UI_CSS.replace('/*GRID*/', '\n'.join(grid_css)).replace('/*BODIES*/', '\n'.join(body_css))
UI_CSS = UI_CSS.replace('__GC__', str(GC)).replace('__GR__', str(GR)).replace('__W__', str(W)).replace('__H__', str(H))

scene_html = ''.join(
    f'<input type="radio" name="sc" id="sc-{sn}"{" checked" if si == 0 else ""}><label id="lb-{sn}" for="sc-{sn}">{sn}</label>'
    for si, sn in enumerate(SCENE_NAMES))

html = open(__file__.replace('gen.py', 'page.html')).read()
html = (html.replace('/*PHYS*/', PHYS_CSS).replace('/*UI*/', UI_CSS)
        .replace('<!--BODIES-->', ''.join(body_html)).replace('<!--REGS-->', reg_html)
        .replace('<!--GRID-->', grid_html).replace('<!--SCENES-->', scene_html)
        .replace('__NPROPS__', f'{len(g.decl):,}').replace('__S__', str(S))
        .replace('__NC__', str(len(contacts))).replace('__HS__', str(HS)))
dst = sys.argv[2] if len(sys.argv) > 2 else 'rigid.html'
open(dst, 'w').write(html)
print(f'{dst}: {len(g.decl)} computed props, {len(contacts)} contacts x {S} substeps, {len(REGS)} registers, {len(html)//1024} KB', file=sys.stderr)
