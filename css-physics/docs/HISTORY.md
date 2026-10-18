# History: dead ends and open ideas

**How the design evolved (Oct 2026).** A 2D engine (rigid.css, Oct 9; in git at `91d73bc:css-physics/archive/rigid2d/`) established state in
layout read back through view timelines, solver levels as nested elements and `@container style()` gating. The 3D
port followed (Oct 9–10; the pre-optimization generator is at `83d4fde:css-physics/archive/rigid3d-v3/gen3d_v3.py`, which
`GEN=<path> python3 src/build3d.py` still builds). One optimization session (Oct 10) produced today's architecture:
planes-first rounds, `K/J/JP` accumulators, the soft box patch, owner-named gating, the #LS/#LT split, two registers
per element, `.ts` scope nests, digests, `SHARE`. Oct 13 tried spatial partitioning; Oct 17 added Firefox. Bugs that
shipped are CLAUDE.md gotchas, guarded by `tools/smoke.sh`.

Numbers are from BENCHMARKS.md (mini PC, Chromium 153) unless marked "141" (an older 2-core VM, Chromium 141).

## Paths that didn't work (or didn't pay)

### Solver and physics

- **Planes solved last:** a stack's floor push never reached the bodies above within the step; phantom downward
  velocities, stacks never slept.
- **`PATCHB=soft`** (soft box/box patch): leaning piles jitter and never sleep. **`PATCHW=depth`:** over-levels tilted
  boxes, which rock every other step.
- **Velocity-based sleep test:** phantom split-impulse velocity kept resting boxes awake.
- **RATE 60 or 45:** at 32 bodies RATE 90 is all asleep at 3.5 s; at 60 five bodies never sleep, at 45 only 12–20 of
  32 sleep (BENCHMARKS §1). At 60 stacks also sink.
- **Starting every zero-velocity body asleep:** upper layers floated in mid-air. Only bodies on the floor now.

### Style engine mechanics

- **Unnamed `@container style()` gates:** each rule evaluates its style() every pass, matching or not (2.5–3.5 µs in
  141, 0.8 µs now), which dominated sparse scenes. Replaced by owner-named containers.
- **Container names on L0/L1 only:** named rules deeper down didn't re-match (Chrome re-matches style-container rules
  only for direct children). Names are on every level.
- **`@function`:** about 2–3× slower than the same math inline (141).
- **`if()` selection inside hot properties:** about 4.2 µs per property against 2 µs for calc (141). The 153
  microbenchmark (BENCHMARKS §2) shows 2.70 against 2.61 µs, so this may no longer hold: re-check before relying on it.
- **Anchor-positioned registers** (state read through anchor positioning instead of view timelines): about 5 ms of
  layout per frame (141).
- **`:has(:nth-child(k):hover)` pointer:** about 30 ms per mouse move; replaced by `anchor-name` on the hovered cell.
- **`.ts` timeline-scope wrappers inside `.rz`:** rendering vanished.
- **Explicit inheritance of #LS's children** plus a live toggle on #LS: idle cost 15 ms (141). Fixed by the #LT split,
  the plain wrapper and `.rz`.
- **Compositor interpolation of body poses** (`transition: transform`, a removed `SMOOTH=<ms>` option, so the
  compositor glides at 60 fps while physics runs at 4–9 fps):
  - Doesn't fire on `.bw` (changes from an element's own animations don't start transitions); only `.bd` transitions.
  - **Bodies jump back and forth:** each restart begins at the pose's *base* value (the spawn point), not the animated
    pose. `tools/transcheck.js`: 677 of 935 restarts more than 2 px off (up to 216 px); `tools/filmstrip.js`: 122
    snap-back cells per 1000 against 1.5. An unregistered copy failed the same way; a minimal page didn't reproduce it.
  - Halves the physics rate: restarts cost ∝ registered properties, which are page-global (BENCHMARKS §4).
  - Screenshots and 60/s draw counts looked perfect; only frame-by-frame checks showed it.
- **Hypothesis rejected: inherited custom properties are copied per level.** Inherited and non-inherited cost the same
  over 50 levels; 6,000 declared at level 1 cost 7.0–7.4 ms at 8, 66 and 130 levels deep.

### Spatial partitioning (Oct 13)

- **Spatial cells (`CELLS=1`, removed from `gen3d.py` on 2026-10-18; `83d4fde` has it):** awake bodies mark the 120-unit floor columns and rows in reach as
  digits of decimal words; a sleeper is present (named, touchable, wakeable) only when its column and row are marked;
  a pair's near test becomes a name-only nested rule. Correct but **slower**: one-body drag through 64 sleepers
  22.3–22.5 ms per pass against 16.1–16.3 for the all-pairs digest; 96 bodies with 4 awake about 60 against 35 ms. The
  sleepers' bookkeeping (cell properties and a digit extraction each) is about 6.6 ms at 64, more than the near tests
  it saves; the digest charges only awake bodies. All awake (frozen tower 48), all variants within about 5%.
- **`OWNLEV=1`** (unnamed rules at the round levels, to dodge the absent-name walk): 27 against 22 ms per pass in the
  64-body one-body drag.
- **World-AABB broadphase:** keeps 108 of 118 sphere-near pairs at 64 bodies (37 touch); piles are full of close pairs.
- **Range style queries as the broadphase:** 1.7–2.3 µs per rule, about a property; per axis more than the `hypot` flag.
- **Per-body readback elements:** no gain (3.1 against 2.5–2.6 ms at 420 registers); unchanged timelines aren't
  re-sampled.
- **Considered, not built:** dynamically bound contact slots (no dynamic indexing: O(N) terms per input per slot,
  ranking O(N²)); Jacobi rounds (per-body sums cost more than the aliases saved; stacks need Gauss–Seidel); per-pair
  container names (N²/2 idents per level); K rules per pair under per-cell names; content-visibility or display:none
  per pair (rules must inherit into the chain).

### Firefox (Oct 17)

- **Container names from rules on a wrapper `#LN`** (portable instead of `if()`): every gate on #L0 had to become
  inherited, N² near flags included. Chrome, frozen 48: +6% (+11% with `BOOLQ=0`). Replaced by a Firefox-only block.
- **Moving the #LM clock into padding** to keep its box still: stopped the re-match.
- **Shrinking boxes 2–4%** so resting faces don't intersect: Firefox still draws whole bodies in document order.
- **A second step per frame:** not found; Firefox samples view timelines once per tick.

### Alternative compute substrates

- **Variable-font metrics** (`1ch`/`1ic` read HVAR, `1ex`/`1cap` MVAR, exactly, at style time):
  each new set of axis values is a new font instance (47 µs at 8 axes, 106 µs at 64 axes with 200 regions, BENCHMARKS
  §3), 4 outputs, 14-bit inputs. Rigid-body math is branchy and changes every step: a rotation matrix cost about 105 µs
  in a font against 36 µs in CSS (141).
- **GSUB shaping as arithmetic:** about 25 ns per glyph per lookup, but dozens of lookups per multiply, and outputs
  still need registers. Break-even at best.
- **avar2** (Chrome 148+): a hidden layer, but neither the per-instance cost nor the input precision improves.
- **Paused animations as evaluators:** about 128 µs per element against 9–13 µs for calc.
- **`var(ident(…))` dynamic indexing:** unsupported in Chromium 141 and 153.
- **Iframes for parallelism:** only cross-site iframes get their own process, and the only script-free channel
  between frames is the iframe's size, parent to child. A single-origin artifact can't use it.
- **Newer Chrome:** 153 is only about 10–15% cheaper per property than 141.

## Open ideas, not yet tried

- **Spheres only:** 1.5–2.5× faster per step, about a third more bodies (48 → 64) at equal fps; per-body overhead,
  registers and the N² pair table remain.
- **Contact slots read by anchor name** (from js-minus-js; `../../COMPARISON.md`): pick a partner's anchor name with a
  two-level `if()` and read it with one `anchor-size()`, so K slots per body make pair rules O(N·K). Caveats: the value
  arrives in layout (the solver must sit under a size-container reader); anchor-positioned registers once cost about
  5 ms of layout per frame; choosing partners still needs the broadphase. First: a microbenchmark against the per-pair
  rules at 64 bodies.
- **AVBD** (Giles, Diaz and Yuksel, SIGGRAPH 2025): body-centric gather, stable stacks at few iterations; but a
  per-body 6×6 Hessian with LDLᵀ is costly in calc, and warm starting needs per-contact registers. Prototype in JS
  first.
