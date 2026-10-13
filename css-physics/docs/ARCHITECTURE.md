# How rigid3d.css works

A 3D rigid-body physics engine (boxes and spheres in a walled tray, with gravity, friction, restitution, sleeping, mouse and touch grabbing) whose page contains **no JavaScript**. Every physics step is evaluated by Chrome's style engine, and the state survives from frame to frame by being written into layout and read back through scroll-driven animations.

The page is generated: `src/gen3d.py` emits one *engine* (CSS + markup) for a given body count, and `src/build3d.py` wraps one or more engines into pages using `src/page3d.html` and `src/ui3d.css`.

Read alongside `src/gen3d.py`. Its module docstring and section comments (`# ---- …`) carry the same structure.

---

## 1. The frame loop

```
          ┌────────────────────────── layout ───────────────────────────┐
          │ register elements <i id=rK> positioned with top/left = f(N*) │
          └───────────────┬──────────────────────────────────────────────┘
                          │ view-timeline progress (one timeline per axis)
                          ▼
#LS  animations q2..qM sample the register timelines → state props X0 Y0 … SC0 …
 └ #LT  clock (animation clk → --now) + time budget (TP, DB via registers q0/q1)
     └ L0 … L(NLEV-1)  the solver: one nested element per level, custom props inherited downward
         └ .regs  register elements whose top/left = var(--N…) (the next state)
```

- **Two style passes per frame.** Chrome samples animations and recalculates style, then lays out. When view timelines are stale after layout (the registers moved), it recalculates style and layout once more in the same frame. Each recalculation that sees changed state runs one physics step, so a frame normally advances **two steps**.
- **Timestep.** A fixed `STEP = 1/RATE`, with RATE 90 by default.
- **Time budget.** #LT keeps a time budget: `TP` is the time of the last step and `DB` the banked time; `live` = 1 when enough time is banked. Steps that would run faster than real time are skipped. Slow frames do not catch up: the simulation runs in slow motion instead.
- **No dependency cycle.** The next state is written into layout (`top`/`left` of the register elements) and read back on the next pass through timelines, never through a custom-property reference.

### Registers

- **Mapping.** A state value `v ∈ [lo, hi]` is stored as an element offset in a scroller `HS = 1,000,000 px` tall (`.regs .sc`):
  `top = (HS − clamp(0, (v − lo)/(hi − lo), 1)·(HS + 1)) px`.
  The element's `view-timeline` gives progress p ∈ [0, 1], and an `@keyframes qK { from {--X: lo} to {--X: hi} }` animation with `animation-timeline: --tK` turns p back into v.
- **Two registers per element.** `view-timeline: --tA block, --tB inline` uses `top` for one register and `left` for another, which halves the register elements.
- **Ranges.** `RANGES` in `gen3d.py` sets each field's range. Precision is LayoutUnit (1/64 px) over 1e6 px, about 26 bits.
- **Per body:** 12 registers (x, y, z, qx, qy, qz, vx, vy, vz, wx, wy, wz) plus the sleep counter `SC`. `qw` is rederived as `sqrt(1 − |q_v|²)`, with the quaternion kept in canonical form (qw ≥ 0).
- **Globals:** `TP`, `DB` (time), `GI` (held body), `GOX/GOY/GOZ` (grab offset in the body frame), `GT` (ray parameter) and `GYP` (gravity on the previous pass).
- **Timeline names.** Names are hoisted with `timeline-scope` on a nest of small `.ts` wrappers holding 24 names each. Short scope lists made the per-element lookup about 3× cheaper than one long list on a single ancestor. The wrappers sit **above** `#RB`; when they were moved inside `.rz`, rendering vanished.
- **Writeback.** The clock registers `TP`/`DB` are written from `#LT` (in `.regs.rt`); every other register is written from the last level.

### Why the wrapper stack looks the way it does

`.ptr > .ts… > #RB > .rz > #LS > #LT > (rt regs) + plain wrapper > L0 > L1 > … > LF > .regs`

- **`.ptr`** holds the pointer (`--sx/--sy` from a view timeline on a hover-anchored marker) and the camera yaw.
- **`#RB`** gates the pointer by `--att`: it is only nonzero while grabbing.
- **`.rz`** zeroes `--sx/--sy/--yaw`, so hovering doesn't restyle `#LS`.
- **`#LS`** reads the state registers. In a fully sleeping scene nothing in it changes, so it isn't restyled.
- **`#LT`** sits inside `#LS` and changes every pass because of the clock. Everything it passes down is either non-inherited or derived only from state, so the solver levels are not restyled while the scene sleeps. This took idle style cost from 13.6 to about 1.0 ms per frame at 32 bodies.
- **The plain wrapper** between #LT and L0 keeps L0 out of #LT's every-pass child restyle unless L0's inputs really changed.
- **The grab overlay** (ring, pin, tether) hangs off L0, the only level that uses the pointer. L1 zeroes the pointer for everything below it.

---

## 2. The solver levels

Every physics quantity is a registered custom property (`@property --name{syntax:'<number>';…}`) declared at a **level** (the element `#L<k>`) and inherited downward. Later levels read earlier quantities with `var()`. Each declaration sits inside a **gate**, an `@container … style(--flag: v)` rule, so work that isn't needed is never declared.

| Level | Contents |
|---|---|
| **L0** | Prediction (gravity, grab spring, kick), quaternion integration, rotation matrices for boxes, broadphase flags for every body/plane group and every body pair, neighbourhood digests, and the mouse ray cast (first pass of a press). |
| **L1** | Narrowphase for nearby pairs: box/box face-axis SAT with reference-face selection, sphere/box closest point. Sphere/sphere and body/plane need no separate narrowphase; the broadphase test is exact for them. |
| **LB = 2** | Batch 0: every body against the tray planes (floor, ceiling, x walls, z walls). Planes go **first**: when they were solved last, a stack's floor push never reached the bodies above within the same step, and stacks kept phantom velocities that never slept. |
| **LB+1 … LB+NBT−1** | Round-robin rounds (a circle-method schedule, `SCHED`): in each round every body meets at most one other, so each pair is solved exactly once per step in a fixed Gauss–Seidel order. One element per round. A pair's contact geometry is declared at its own round's level, next to its solve. |
| **LF** | Final state per body (position, rotation, velocities rederived from displacement), sleep counter, and writeback values `N*` for the registers. |

NLEV is about N + 3: 51 levels at 48 bodies, 67 at 64.

### Contact model (position level, split impulse)

- **Body vs plane, box.** By default (`PATCHW=soft`) a box gets one contact at a soft support patch: per box axis k, `e_k = h_k (n·col_k)`, the deepest corner is at `dm = d0 + Σ|e_k|`, and the patch centre is placed along each axis by `w_k = |e_k| / (PATCHC + dm − |e_k|)`. That gives the even centroid of the penetrating corners for a nearly flat box, and the corner itself when the box stands on it. `PATCHW=even|depth` uses all 8 corners instead.
- **Body vs plane, sphere.** One contact at the support point.
- **Box vs box.** Only one reference face per pair is used (ties go to the lower index). The incident box's 8 corners are written as affine functions of the corner signs and **clipped laterally** to the reference face, which gives the real overlap patch for crossed or overhanging boxes. The contacts are then reduced to one depth-weighted contact (Q = Σq, D = Σq²/Q, patch point = q-weighted mean). `PATCHB=soft` (a single soft patch) is experimental: piles jitter and never sleep.
- **Solve per group.** For a single reduced contact:
  - **Split impulse.** `lvel` cancels this step's approach velocity and carries velocity. The rest (`lex`) pushes out older overlap beyond `SLOP`, capped at `MAXCORR`. `lex` is position-only and is removed again from the rederived velocity, so depenetration never launches bodies.
  - **Restitution** applies above a bounce threshold (`BOUNCE_THR`).
  - **Coulomb friction** uses the effective inverse mass along the sliding direction.
  - **Torsional friction** cancels relative spin about n, limited by μ·pn·patch radius.
  - **Rolling resistance** applies to spheres (`ROLL`) and optionally boxes (`ROLLB`).
  - **Shock propagation:** the lower body of a vertical contact is made heavier (`SHOCK`).
  - **Sleeping partners** are treated as immovable (inverse mass 0).

### Accumulators: running totals without sums over all partners

A body can be touched by any round. Instead of summing over every possible partner, each body keeps **running totals**:

- **The totals:** position change x,y,z; rotation change tx,ty,tz; and the position-only "pseudo" shares ex,ey,ez and gx,gy,gz. Spheres skip the pseudo rotation share.
- **`K{i}{c}`** (syntax `'*'`, inherited) is the latest total. A round that touches body i declares `J{par}{i}{c} = K + this round's contribution`, and the **next** element aliases `K = J`. Reading the latest total is then one `var()` with no fallback chain.
- **`JP{i}{c}`** holds the last batch's totals. The final level reads `var(--JP, var(--K, init))`.
- **Final velocities:** `v = (pos − X − pseudo)/h` and `w = o + (θ − pseudo_θ)/h`.

### Gating: what makes a sleeping or sparse scene cheap

- **Gates.** Each declaration's gate is a style() condition on a flag computed at L0/L1. Examples: `ac{i}` (body awake and this pass advances time), `np{a}_{b}` (pair near), `tcp…` (touching), `p{a}_{b}uA/uB` (which reference face), `nw{i}{F|C|X|Z}` (near a plane).
- **Named containers.** A rule whose container name is absent from every ancestor is skipped cheaply: 50,000 such rules measured at 0 ms in Chromium 141 and about 7 ms per pass in Chromium 153. A present-name style() rule costs about 0.9 µs per pass even when false (2.5–3.5 µs in 141), about 6× an absent one.
  - So every rule owned by body i, or by a pair whose lower index is i, is written `@container b{i} style(--gate: v){…}`.
  - L0 computes `--A{i}: if(style(--ac{i}:1) or style(--nbs{i}:1): b{i}; else: )` and `--AN: q var(--A0) var(--A1) …`.
  - **Every** level has `container-name: var(--AN)`. Chrome only re-matches rules that depend on a style container for that container's direct children, so the names must be on every level.
  - The rules of a sleeping neighbourhood are rejected without evaluating their style() query.
- **Shared names (`SHARE=1`).** A property declared and read on only one batch level is invisible to every other level (it is non-inherited), so properties of different levels share names (`zn0, zn1, …`). This shrinks the `@property` list by about a third at 64 bodies.

### Sleeping and waking

- **Going to sleep.** A body that moves less than `SLEEP_DX`/`SLEEP_DA` in a step counts up `SC` to `SLEEP_K` (45 passes). At `SLEEP_K` it is "ready", and it sleeps (SC = SLEEP_K + 1) unless it is blocked by touching a body that isn't ready.
- **The stillness test uses displacement, not velocity.** Resting boxes carry a bounded phantom velocity from the split impulse. The test also counts a step that undoes the previous one as still, because resting boxes can rock by a hair every other step.
- **Waking.** A sleeping body wakes on shake, reset, a gravity change, being grabbed, or a moving body coming near.
- **Neighbourhood digests.** "A moving body is near me" is computed with decimal words:
  - Each awake body j sums its near flags into words where body i is digit `i % 6` of word `i // 6`. A registered number survives `var()` with only 6 significant digits.
  - Summing the words over all bodies tells every body at once whether an awake, moving or not-ready body is near it.
  - The gates are `mix`, `anyrd`, `pk`, `bk` and `nbs`.
- **Starting asleep.** Scenes start with bodies asleep only if they are at rest **and touching the floor** (`scene_decls`). Anything placed in the air starts awake.

### Grabbing (mouse and touch)

- **Picking.** On the first pass of a press, a ray from the camera is unprojected through the CSS camera transform (constants `PERSP`, `TILT`, `CAM_TY`, `CAM_DIST` must match `.cam` in `ui3d.css`) and cast against every sphere and box slab. The hit is latched into registers: `GI` (body index + 1, or N+1 for a miss), `GT` and `GO*`.
- **Holding** reads only the held body's state, through blocks gated on `GIr = i+1`. A spring-damper pulls the grab point toward the ray point at the latched depth.
- **Mouse pointer.** A hover grid of cells gets `anchor-name` on `:hover`. A zero-size marker is anchored to the hovered cell and has a view timeline, which turns its position into `--sx/--sy`.
- **Touch.** Tap a body to pick it up; the point comes from the hovered cell of a grid 3× the arena's size. Dragging scrolls that layer, and the marker inside it moves with the finger. Tap again to drop.

---

## 3. Rendering

- **Units.** The scene is laid out in fixed px (1 world unit = 1 px) inside `.view` and scaled once with `transform: scale(100cqw / VW)`. Per-element `cqw` units cost about 70 µs per element per pass when everything moves.
- **Body wrapper.** Each body wrapper `#w{i}` animates its own pose from the registers' view timelines (keyframes `v{K}`) into **non-inherited** props `--Rx --Ry --Rz --Ri --Rj --Rk --Rg`.
- **Rotation and lighting.** `.bd` pulls the quaternion with an explicit `inherit` and builds a `matrix3d`. Faces get per-face lighting colours by `color-mix` from the rotation columns. This is about 3× cheaper than letting inherited registered props flow into every face.
- **Shadows** are blurred discs on the floor, sized and faded by height.

---

## 4. Pages and builds

| Command | Output |
|---|---|
| `COUNTS=16 PLAIN=1 python3 src/build3d.py out/x.html` | One engine with readable names and a `<!--BODYINFO …-->` comment. **This is what the test tools expect.** |
| `python3 src/build3d.py out/x.html` | One page with several engines (default 8, 12, 16, 24), selected by radios; unselected engines are `display:none`. |
| `MULTI=1 COUNTS=… DEFAULT=24 python3 src/build3d.py site/rigid3d.html` (`tools/make_site.sh`) | One page per count, linked to each other. |

- **Prefixes.** Engines are generated in parallel, one `gen3d.py` process per count. Each non-PLAIN engine gets a name prefix (`PFX`) and minified property names.
- **CSS splitting.** A stylesheet over `CSS_SPLIT` (14 MB, the artifact host's per-file limit) is split into linked `rigid3d-N.k.css` files, cut between top-level rules.
- **Artifact index.** `tools/artifact_index.py` strips doctype/html/head/body for the claude.ai artifact host.

### gen3d.py knobs (environment)

| Knob | Default | Meaning |
|---|---|---|
| `NBOX`, `NSPH` | 8, 8 | body counts (min 4 each; the hand-built scenes use 4+4). `build3d.py` sets them from `COUNTS`; `NBOX_FIX` overrides the box count. |
| `RATE` | 90 | steps per second. At 60 or 45 piles never settle (measured); 120 is stiffer but slower. |
| `SLEEP_K` | 45 | still passes before sleeping |
| `ROLL` / `ROLLB` | 0.06 / 0 | rolling-resistance arm for spheres / boxes |
| `PATCHW` | soft | box/plane contact: soft (one patch) \| even \| depth (8 corners) |
| `PATCHB` | corners | box/box: corners (clipped incident corners) \| soft (experimental, jitters) |
| `PATCHC` | 1.0 | patch weighting constant |
| `SCENE`, `SCENE_LIST` | tower | first scene and the scene list (tower, rain, stack; also calm, pair) |
| `SIMPLIFY` | 1 | `simp.py` calc() simplifier |
| `INLINE2`, `INL_DEPTH`, `INL_ONLY1` | 1, 2, 1 | inline single-use props into their consumers |
| `SHARE` | 1 | shared names for level-local props |
| `PSEUDOROT` | 1 | track the position-only share of rotation for boxes |
| `OWNSET` | 01234 | which gate families get container-name ownership (ablation knob) |
| `PFX`, `MINIFY` | — | set by build3d for multi-engine pages |

### Scenes

`SCENES` holds hand-placed 8-body layouts for tower, rain and stack. `_extend()` adds bodies past 8:
- **Layer 0:** an 8×5 grid on the floor, clear of the hand-placed bodies.
- **Upper layers:** offset by half a cell and dropped from above.
- **Rain:** the original 24 drop columns, then a higher offset set.

---

## 5. Where the time goes (summary; details in BENCHMARKS.md, measured 2026-10-13 in Chromium 153)

- **Per-property cost.** A registered property costs about 1.5–2 µs plus about 0.1–0.15 µs per arithmetic operation and about 0.17 µs per `var()` reference. Arithmetic is not the bottleneck; property count is.
- **A 48-body pile.** One step costs about 37 ms (frozen at 4 s), almost all of it style recalculation:
  - contact pairs about 15 ms;
  - per-body awake blocks about 27 ms (82 + 24 props per body; overlaps with the pairs);
  - base about 6 ms.
- **N² costs (all bodies awake, 48 bodies).**
  - The all-pairs broadphase is 1,128 near tests at about 2.9 µs each, about 3.3 ms.
  - Owner-named pair rules whose name is present (body awake) but whose style() is false add about 0.9 µs × 3,360 ≈ 3 ms.
  - Together that is about 17% of a step, and it grows with N².
- **Registers.** About 20 µs per register element restyle (2 values).
- **An idle scene** (32 bodies, all asleep) costs about 2 ms per style pass, 2 passes per frame.
