# How rigid3d.css works

Every physics step is evaluated by Chrome's style engine; state survives between frames by being written into layout
and read back through scroll-driven animations. `src/gen3d.py` emits one *engine* (CSS + markup) per body count;
`src/build3d.py` wraps engines into pages with `src/page3d.html` and `src/ui3d.css`. `gen3d.py`'s docstring and
`# ---- …` section comments follow this document's structure.

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

- **Two steps per frame.** Chrome recalculates style and lays out; when view timelines are stale after layout (the
  registers moved) it does both once more in the same frame. Each recalculation that sees changed state runs a step.
- **Timestep** `1/RATE`, RATE 90. #LT banks time (`TP` last step, `DB` bank; `live` = 1 when enough is banked): steps
  faster than real time are skipped, slow frames run in slow motion.
- **No dependency cycle:** the next state goes through layout and timelines, never a custom-property reference.

### Registers

- A value `v ∈ [lo, hi]` (`RANGES` in `gen3d.py`) is an element offset in a 1,000,000 px scroller (`.regs .sc`):
  `top = (HS − clamp(0, (v − lo)/(hi − lo), 1)·(HS + 1)) px`; its `view-timeline` progress drives
  `@keyframes qK { from {--X: lo} to {--X: hi} }`. Precision: LayoutUnit (1/64 px) over 1e6 px, about 26 bits.
- Two registers per element: `view-timeline: --tA block, --tB inline` (`top` and `left`).
- Per body: x, y, z, qx, qy, qz, vx, vy, vz, wx, wy, wz and the sleep counter `SC`; `qw = sqrt(1 − |q_v|²)` (canonical,
  qw ≥ 0). Globals: `TP`, `DB`, `GI` (held body), `GOX/GOY/GOZ` (grab offset, body frame), `GT` (ray parameter), `GYP`
  (previous gravity).
- Timeline names are hoisted with `timeline-scope` on nested `.ts` wrappers of 24 names each (about 3× cheaper per
  lookup than one long list), **above** `#RB` (inside `.rz`, rendering vanished).
- `TP`/`DB` are written from `#LT` (`.regs.rt`), every other register from the last level.

### Why the wrapper stack looks the way it does

`.ptr > #TS > #TI > (#FO) + .ts… > #RB > .rz > #LS > #LT > (rt regs) + #LM > #LW > L0 > L1 > … > LF > .regs`

- `.ptr`: pointer (`--sx/--sy`) and camera yaw. `#TS`, `#TI`, `#FO`: the touch input ("Touch" below), above the
  `.ts` wrappers so a register's timeline lookup never scans `#TS`'s list; `.view` zeroes the drag. `#RB` gates the
  pointer and the drag by `--att` (nonzero only while grabbing); `.rz` zeroes `--sx/--sy/--yaw` and the drag so
  hovering or dragging doesn't restyle `#LS`.
- `#LS` reads the registers; asleep, nothing in it changes. `#LT` changes every pass (the clock), but passes down only
  non-inherited or state-derived values, so the solver isn't restyled while the scene sleeps (idle at 32 bodies went
  from 13.6 to about 1 ms per frame).
- `#LM`, `#LW`: plain wrappers that keep L0 out of #LT's every-pass child restyle; #LM is also Firefox's re-match
  clock (§6).
- The grab overlay (ring, pin, tether) hangs off L0, the only level using the pointer; L1 zeroes it below.

## 2. The solver levels

Every quantity is a registered `<number>` declared at a level (`#L<k>`), inherited downward and read with `var()`.
Each declaration sits in a **gate**, an `@container … style(--flag: v)` rule, so unneeded work is never declared.

| Level | Contents |
|---|---|
| **L0** | Prediction (gravity, grab spring, kick), quaternion integration, box rotation matrices, broadphase flags per body/plane group and body pair, neighbourhood digests, the mouse ray cast. |
| **L1** | Narrowphase for near pairs: box/box face-axis SAT with reference-face selection, sphere/box closest point (sphere/sphere and body/plane need none). |
| **LB = 2** | Every body against the tray planes, **first**: solved last, a stack's floor push never reached the bodies above within the step. |
| **LB+1 … LB+NBT−1** | Round-robin rounds (circle method, `SCHED`): each body meets at most one other per round, so each pair is solved once per step in a fixed Gauss–Seidel order. A pair's contact geometry sits at its round's level. |
| **LF** | Final state (velocities rederived from displacement), sleep counter, writeback values `N*`. |

NLEV ≈ N + 3 (51 at 48 bodies). **`SHARE=1`:** a property declared and read on one batch level only is non-inherited,
so different levels share names (`zn0, zn1, …`): a third fewer `@property` rules at 64 bodies.

### Contact model (position level, split impulse)

- **Box vs plane** (`PATCHW=soft`): one contact at a soft support patch. Per box axis k, `e_k = h_k (n·col_k)`, the
  deepest corner is at `dm = d0 + Σ|e_k|`, and the patch centre sits at `w_k = |e_k| / (PATCHC + dm − |e_k|)` along
  each axis: the centroid of the penetrating corners for a flat box, the corner for a box on its corner.
  `PATCHW=even|depth` uses all 8 corners. **Sphere vs plane:** the support point.
- **Box vs box:** one reference face per pair (ties to the lower index); the incident box's 8 corners, affine in the
  corner signs, are clipped laterally to it, then reduced to one depth-weighted contact (Q = Σq, D = Σq²/Q, point =
  q-weighted mean).
- **Solve:** `lvel` cancels this step's approach velocity; `lex` pushes out older overlap beyond `SLOP` (capped at
  `MAXCORR`), position-only and removed from the rederived velocity, so depenetration never launches bodies.
  Restitution above `BOUNCE_THR`; Coulomb friction with the effective inverse mass along the slide; torsional friction
  (μ·pn·patch radius); rolling resistance (`ROLL`, `ROLLB`); shock propagation (`SHOCK`: the lower body of a vertical
  contact is heavier); sleeping partners have inverse mass 0.

### Accumulators

Any round can touch a body, so each keeps running totals instead of sums over all partners: position change x,y,z,
rotation tx,ty,tz, and position-only "pseudo" shares ex,ey,ez, gx,gy,gz (none for sphere rotation). `K{i}{c}` (syntax
`'*'`, inherited) is the latest total; a round touching body i declares `J{par}{i}{c} = K + contribution` and the
next element aliases `K = J` (one `var()`, no fallback chain). `JP{i}{c}` holds the last batch's totals; LF reads
`var(--JP, var(--K, init))`. Velocities: `v = (pos − X − pseudo)/h`, `w = o + (θ − pseudo_θ)/h`.

### Gating: what makes a sleeping or sparse scene cheap

- **Flags** from L0/L1, tested as `style(--flag: 1)`: `ac{i}` (awake, and this pass advances time), `np{a}_{b}` (pair
  near), `tcp…` (touching), `p{a}_{b}uA/uB` (reference face), `nw{i}{F|C|X|Z}` (near a plane). `BOOLQ=1` tests
  `style(--flag)` instead (about 0.3 µs per rule cheaper, within noise in the engine; always true in Firefox).
- **Owner names.** Every rule owned by body i, or by a pair whose lower index is i, is
  `@container b{i} style(--gate){…}` at every level from L1 down (`OWNLEV`). L0 computes
  `--A{i}: if(style(--ac{i}: 1): b{i}; style(--nb{i}: 1): b{i}; else: )` (without `if()`, every body always named:
  §6, §7) and `--AN: q var(--A0) var(--A1) …`, and
  **every** level has `container-name: var(--AN)`, so each level finds the name at its parent (Chrome 141 also didn't
  re-match deeper named rules; not reproduced in 153, `../../bugs/README.md`).
- **Costs** (BENCHMARKS.md §2): a present name is found at the parent (0.2 µs, 0.8 µs with a false `style(--flag: 1)`).
  An absent name skips the style() but walks every ancestor's name list: about 0.2 µs + 0.6–0.9 ns × depth × names in
  a microbenchmark, about 0.2 + 0.01 × depth µs in the engine. With few names present that still beats an unnamed
  `style()` (`OWNLEV=1` made a 64-body one-body drag about 20% slower, HISTORY.md); with all awake the form doesn't
  matter. Rules nobody matches are the N² floor: about 3 per pair (narrowphase, solve, alias), 4 ms per pass at 64 in
  a one-body drag, growing like N² × depth.
- Spatial cells were a dead end (HISTORY.md).

### Sleeping and waking

- A body moving less than `SLEEP_DX`/`SLEEP_DA` per step counts `SC` up to `SLEEP_K` (45), is "ready", and sleeps
  (SC = SLEEP_K + 1) unless it touches a body that isn't. `SC` is tested against half-integers (asleep: SC > 45.5):
  it comes back from its register a hair off (§7). Stillness is displacement, not velocity (resting boxes carry
  phantom split-impulse velocity), and a step undoing the previous one counts as still (resting boxes rock by a hair).
- Wakes on shake, reset, gravity change, grab, or a moving body coming near.
- **Digests:** each awake body sums its near flags into decimal words, body i as digit `i % 6` of word `i // 6` (6
  significant digits survive `var()`); the sum over all bodies tells every body whether an awake, moving or not-ready
  body is near. Gates: `mix`, `anyrd`, `pk`, `bk`, `nb` (asleep, near an awake body).
- Scenes start a body asleep only if it rests **on the floor** (`scene_decls`); each scene's `#INI` rule declares every
  body's `--isc`.

### Grabbing

- On a press's first pass a camera ray (`PERSP`, `TILT`, `CAM_TY`, `CAM_DIST`, matching `.cam` in `ui3d.css`) is cast
  against every sphere and box slab; the hit is latched into `GI` (index + 1, N+1 for a miss), `GT`, `GO*`. Holding
  reads only the held body, through blocks gated on `GIr = i+1`; a spring-damper pulls the grab point to the ray.
- Mouse: hover cells get `anchor-name` on `:hover`; a zero-size marker anchored there has a view timeline giving
  `--sx/--sy`. Touch (`@media (pointer: coarse)`, `--tm: 1`): touch a body and drag; let go to drop.

### Touch

Chrome gives a finger drag almost nothing: `:hover`/`:active` arrive only with show-press (a finger resting
100–150 ms), `:active` clears when the finger passes the touch slop (tap-cancel), `:hover` never follows. A quick drag
gets neither. A scroll does follow the finger, and the scroller that scrolls says where it came down.

- Handles: each body's wrapper holds `.hd` (`#h<i>`), a camera-facing disc of radius R + 14, a scroller with
  6000-unit content resting at (3000, 3000). The gesture latches to the handle under the finger; Chrome unprojects the
  movement onto the handle's plane, so its offset is the drag in world units on the camera-facing plane through the
  body (`touch-3d-scroll` in `engine/`). `scroll-axis-lock: none` stops axis locking; `overscroll-behavior: contain`
  keeps the page still; everything else is `pointer-events: none`, so drags beside the bodies scroll the page.
- `#TI`: one additive animation per handle and axis gives `--tdx/--tdy` (only the dragged handle is off rest) and,
  through step keyframes (0 within 0.6 units of rest), `--tgi` = dragged index + 1.
- Finger down: the follower `#FO` is a small snap container whose snap area sits at the sums, so it re-snaps after
  every layout, except that Chrome defers layout re-snaps while a scroll gesture is active (`ShouldDeferLayoutSnap`,
  `touch-snap-defer`) and does them in the frame it ends. `--held` = "#FO lags the sums"; `--att = held × sign(tgi)`.
- Back to rest: while held a handle's snap area is an oversized one (`u`) following its offset (valid within ±40),
  so lifting snaps nothing and a fling stops within 40 units; when `--held` drops the rest area (`i`) returns and the
  handle re-snaps at once (a layout re-snap). Chrome's own end-of-gesture snap is animated and part of the gesture: it
  kept the body held and pulled it back for 200–500 ms. A frame with the handle at rest and `#FO` lagging has
  `tgi = 0`, so `att` stays 0.
- Engine: the press's first pass (`--tpk`, not `--pick`) latches `GI = tgi` and the body's centre into `GO`; no ray.
  Holding (`--tho`) pulls the centre (`grr = 0`) to `GO + tdx·ex + tdy·ey` (screen x, y on the camera-facing plane,
  the ray's derivatives at the current yaw); the overlay shows that target projected.
- Measured (`tools/touchcheck.js`): held from the first scroll update, dropped 16–50 ms after the lift (2–3 frames:
  250 ms at 48 bodies), trailing the finger by the touch slop (15 px desktop, ~8 dp Android). On the Android emulator
  (`../../shared/android/`, `experiments/touch/handles.html`) every drag that became a scroll grabbed and dropped;
  flings ran past the 40-unit cap (~190 units). Checked on a real phone by the user, 2026-10-18.

## 3. Rendering

- Laid out in fixed px (1 world unit = 1 px) inside `.view`, scaled once with `transform: scale(100cqw / VW)`
  (per-element `cqw` cost about 70 µs per element per pass).
- `#w{i}` animates its pose from the registers' timelines (`v{K}`) into **non-inherited**
  `--Rx --Ry --Rz --Ri --Rj --Rk --Rg`; `.bd` pulls them with explicit `inherit` into a `matrix3d`, and faces get
  lighting by `color-mix` from the rotation columns (3× cheaper than inherited registered props in every face).
- Shadows are blurred floor discs sized and faded by height.

## 4. Pages and builds

| Command | Output |
|---|---|
| `COUNTS=16 PLAIN=1 python3 src/build3d.py out/x.html` | One engine, readable names, a `<!--BODYINFO …-->` comment. **What the test tools expect.** |
| `python3 src/build3d.py out/x.html` | `out/x-N.html` per count (8, 16, 24, 32, 48, 64), linked; `out/x.html` copies the `DEFAULT` (16). The deploy builds this as `index.html` (`../deploy/assemble.sh`). |
| `MULTI=0 python3 src/build3d.py out/x.html` | One page with every engine, selected by radios. |

Engines are generated in parallel; non-PLAIN ones get a name prefix (`PFX`) and minified names. Stylesheets over
`CSS_SPLIT` (14 MB; Workers allows 25 MiB per file) split into linked `x-N.k.css` files.

### gen3d.py knobs (environment)

| Knob | Default | Meaning |
|---|---|---|
| `NBOX`, `NSPH` | 8, 8 | body counts (min 4 each); set from `COUNTS`; `NBOX_FIX` overrides the box count |
| `RATE` | 90 | steps per second; at 60 or 45 piles never settle, 120 is stiffer but slower |
| `SLEEP_K` | 45 | still passes before sleeping |
| `ROLL` / `ROLLB` | 0.06 / 0 | rolling-resistance arm for spheres / boxes |
| `PATCHW` | soft | box/plane: soft (one patch) \| even \| depth (8 corners) |
| `PATCHB` | corners | box/box: corners (clipped) \| soft (experimental, jitters) |
| `PATCHC` | 1.0 | patch weighting constant |
| `SCENE`, `SCENE_LIST` | tower | first scene and the list (tower, rain, stack; also calm, pair, field) |
| `BOOLQ` | 0 | gate 0/1 flags with `style(--flag)` (Chrome only) |
| `HYPOT1`, `FFQ` | 1, 1 | Firefox: `1 * hypot(…)`; Firefox-only names and #LM re-match clock (§6) |
| `OWNLEV` | 999 | owner-named rules only at levels ≤ this |
| `TRAY`, `FIELD_GAP` | 1, 6 | tray scale (benchmarks only: the camera doesn't follow); field spacing |
| `SIMPLIFY` | 1 | `simp.py` calc() simplifier |
| `INLINE2`, `INL_DEPTH`, `INL_ONLY1` | 1, 2, 1 | inline single-use props into their consumers |
| `SHARE` | 1 | shared names for level-local props |
| `PSEUDOROT` | 1 | track the position-only share of box rotation |
| `OWNSET` | 01234 | gate families with container-name ownership (ablation knob) |
| `PFX`, `MINIFY` | — | set by build3d for multi-engine pages |

### Scenes

`SCENES` has hand-placed 8-body tower, rain and stack; `_extend()` adds an 8×5 floor grid, then upper layers offset by
half a cell and dropped (rain: its 24 drop columns, then a higher set). **Field** shelf-packs every body at rest on the
floor, `FIELD_GAP` apart, so it loads asleep: the sparse-regime scene (`tools/sparse.js`).

## 5. Where the time goes

[BENCHMARKS.md](BENCHMARKS.md) §1 (ablation, N² costs) and §2 (cost per construct). Property count, not arithmetic,
is the bottleneck.

## 6. Firefox

Runs in Firefox 159+ (158 needs `layout.css.scroll-driven-animations.enabled`; the page says so). Checked in 157 (with
the pref), 158, 159 DevEdition and 160 Nightly, 2026-10-17: on a static state every property on every level matches
Chrome to float noise, after these changes (Chrome cost: BENCHMARKS.md §1 Firefox, within noise):

| Firefox behaviour | Workaround |
|---|---|
| `style(--x)` (no value) is always true on a registered property | `BOOLQ=0`: 0/1 gates are `style(--x: 1)` |
| Negating `hypot()` negates its arguments, leaving it unchanged: `100 - hypot(3, 4)` is 105 (also in a subtracted `min`/`max`/`sign`/sum, through `var()`) | every `hypot(` becomes `1 * hypot(` after `simp.py` (`HYPOT1=0` off) |
| No `if()` (the names `--A{i}`) | `@supports not (width: if(…))`: every body always named on #L0 (also Safari, §7) |
| Style-container rules aren't re-matched when the container's value changes through an animation (all state does): gates kept their first result | Firefox re-matches the subtree of a size container whose size changed: Firefox-only, #LM's box is sized from `--ffk = any × now` (two incommensurate periods), so it changes every frame while anything is awake (padding alone doesn't trigger it). #LW restores the arena's size (`VW × --u`); `--u` is registered so its `100cqw` resolves on `.arena`, not #LM (`tools/overlaycheck.js`). `FFQ=0` off. |
| No typed division before 158 | the view's scale is declared twice, `scale(tan(atan2(100cqw, 900px)))` then `scale(calc(100cqw / 900px))`: without typed division the second is dropped |
| Intersecting 3D planes drawn in document order (a shadow over its body) | the shadow comes first in each body |

Three are unreported Firefox bugs, with reproductions in `../../bugs/` (hypot, style-query re-match, boolean query).

**Left as they are:** one step per frame (Firefox samples view timelines once per tick), so 60 steps/s against
`RATE` 90, about half speed under load; whole bodies composited in document order (a box resting on another can draw
behind it; sphere rings draw over the disc); touch untested, and probably grabs nothing (it needs Chrome's deferred
layout re-snap).

## 7. Safari (WebKit)

Runs in Safari 26+ (scroll-driven animations, `timeline-scope` and anchor positioning arrived in 26; style queries on
custom properties in 18). Checked in Playwright's WebKit 27.2 (WPE, Linux, headless), 2026-10-21, with and without
`if()`: Safari 27.0 has none (Technology Preview 249 added it), `NOIF=1` makes the checks see the page as it does.
`smoke.sh` passes in both; `tools/xcheck.js` finds every value on every level within 1e-2 of Chrome's, mostly within
2e-3, on 16- and 48-body piles (BENCHMARKS.md §1 WebKit).

| WebKit behaviour | Workaround |
|---|---|
| No `if()` before Safari 27.x | Firefox's fallback (§6), on a feature query: every body always named on #L0 |
| `atan2()` of a relative length (`100cqw`) comes out wrong in Safari (probably [248513](https://bugs.webkit.org/show_bug.cgi?id=248513)); the view was scaled by `tan(atan2(100cqw, 900px))` | typed division (Safari 26) is declared after it and wins; `experiments/safari/probe.html` B2 prints the values |
| `var()` of a registered number keeps 6 decimal places, as CSSOM serializes a number (Chrome and Firefox keep 6 significant digits): `1e-8` is 0, `45.999999` stays | registers read back a hair off (46 as 45.999999, −1600 as −1599.999924) and Chrome's rounding hid it; WebKit's exact tests on them woke every sleeping body on every pass (a 16-body tower never slept; one box rocked in a two-step cycle). `SC` and `GYP` are compared with a margin of 0.5 |
| An animated registered `<integer>` isn't rounded ([327925](https://bugs.webkit.org/show_bug.cgi?id=327925)) | why the margin and not `<integer>` registers |
| One step per frame (timelines are sampled once per frame, as in Firefox): 60 steps/s at 60 Hz against `RATE` 90 | left as is: two-thirds speed |
| Headless WPE screenshots flatten `preserve-3d` (Playwright paints a software snapshot) | harness only: frames of a `recordVideo` recording are composited and show the scene as Chrome draws it |

Everything small loses relative precision through `var()` (a rotation increment of 1.5e-3 keeps 3 digits), which moves
contact normals by about 1e-3 against Chrome, and where it flips a gate (a box corner just touching) a handful of
values by up to 0.17: chaos, not a fault (smoke, sleep and grabbing behave as in Chrome). **Untested:** touch on iOS (the touch
input rests on Chrome's deferred layout re-snap, "Touch" above) and drawing through Core Animation on macOS (only WPE's
compositor on Linux was checked).

