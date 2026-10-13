# How we got here

This is a chronological account of the engine, reconstructed from the generator versions kept in `archive/`, the code comments, the end-of-session summaries and the last session's notes (Oct 9–11, 2026, about three working days in one long Claude session).

Numbers marked † come from summaries of earlier sessions; their raw logs no longer exist. Everything else was measured in the last session (Chromium 141, a 2-core VM) with the scripts listed in BENCHMARKS.md. BENCHMARKS.md now holds the 2026-10-13 re-measurements on a different machine and Chromium 153, so its numbers differ from the ones quoted here.

Standing goals, set by the project owner throughout:
- pure CSS pages, with no JavaScript unless asked;
- Chrome-only is fine;
- speed matters, payload size does not;
- Claude tests in headless Chromium itself;
- "as many objects on screen as possible with smooth animation and interaction".

---

## Phase 0: rigid.css (2D), Oct 9

`archive/rigid2d/gen_v1.py` was the first engine, followed by `archive/rigid2d/gen.py`. It established the machine that everything later reuses:

- **State in layout, read back through view timelines.** Each body's x, y, angle, vx, vy and ω sits in a hidden register element's `top`; the element's `view-timeline` progress, hoisted with `timeline-scope`, drives an animation that turns it back into a custom property. The next state is written into `top`, and Chrome re-samples view timelines after layout, which closes the loop with no dependency cycle.
- **Two style passes per frame**, so about 120 steps/s at 60 Hz.
- **The solver** is an XPBD-style contact solver written as registered custom properties on a chain of nested elements:
  - L0: predict and broadphase (bounding circles);
  - L1: narrowphase (SAT reference-face manifolds for box/box, closest point for circle/box);
  - L2: Gauss–Seidel over batches (walls, then round-robin matchings of all pairs), with friction, restitution and shock propagation, and velocities rederived from positions.
- **Gating.** Declarations sit inside `@container style(--flag: 1)` blocks keyed on flags from the level above, so far-apart pairs are never declared at all.

## Phase 1: 3D port (rigid3d.css), Oct 9–10

The same machine, one dimension up, built as a series of generator versions:

| Version | What changed |
|---|---|
| `gen3d_presleep` | 13 registers per body (position, quaternion, linear and angular velocity). L0 prediction, quaternion integration, rotation matrices, broadphase against bounding spheres and the 6 tray planes, mouse ray cast. L1 box/plane corners, sphere closest point, box/box SAT with incident corners clipped to the reference face. L2 one depth-weighted contact per group, Gauss–Seidel with world-space inverse inertia. A first inliner substituted cheap or single-use properties. |
| `gen3d_new` | **Sleeping** (`SLEEP_K`): bodies still for K passes stop being simulated, and a sleeping scene should cost nothing. |
| `gen3d_prerender` | `simp.py`, a calc() expression simplifier (`SIMPLIFY`). |
| `gen3d_touch` | Touch flags (LC): the solve runs only for groups with an active contact, since most near pairs aren't touching. Render pose moved into non-inherited props (below). |
| `gen3d_c` | `INLINE2`: single-use properties inlined into consumers with a depth limit. Cost model in the comments: registered prop about 2.3–3.5 µs, var() reference about 0.7 µs. |
| `gen3d_pre_eng` | Box rocking fixes (`PATCHW`, `PATCHC`, `ROLL`, `ROLLB`). Touch-screen input (a scrollable 3× layer) came in around here. |
| `gen3d_pre_grab` | Several engines per page (per-engine name prefix `PFX`, `MINIFY`), selected by radios; unselected engines are `display:none`. |
| `gen3d_v3` (`archive/rigid3d-v3/`) | Grab rework (latch the pick once, then read only the held body). The baseline before the big optimization session. |

Lessons from Phase 1 that are still in the code:

- **Rendering.** Per-element `cqw` units cost about 70 µs per element per pass when everything moves, so the scene is laid out in fixed px and scaled once.
- **Body pose props.** Body wrappers animate pose into **non-inherited** props, and faces pull them with an explicit `inherit`. That was about 3× cheaper than inherited registered props flowing into every face.
- **Pointer input.** The first pointer used `:has(:nth-child(k):hover)` rules, which cost about 30 ms per mouse move. It was replaced by an `anchor-name` on the hovered cell plus a view-timeline marker.
- **Box contact patches.** Depth-weighted box/plane patches put the push next to the deepest corner, which over-levelled a slightly tilted box and left it rocking every other step. Even weighting and, later, the soft single patch fixed this.
- **Sleep test.** Testing velocity for stillness doesn't work: resting boxes carry a bounded phantom velocity from the split impulse. The test uses displacement, and counts a step that undoes the previous one as still.
- **Timestep.** At `RATE` 60 stacks sink; 120 is stiffer but slower. 90 is the compromise.

## Phase 2: the big optimization session, Oct 10

Goal: as many objects as possible with smooth animation and interaction. The session followed a profile → change → short benchmark → occasional large validation loop.

**Kept** (the current architecture):

1. **Early schedule (`LB=2`).** Planes come first, then round-robin rounds, one element per batch. Each pair's geometry lives at its own round's level, next to its solve.
2. **Running-total accumulators `K/J/JP`**, replacing sums over every possible partner (see ARCHITECTURE §2).
3. **Soft box/plane patch (`PATCHW=soft`).** One contact instead of 8 corners.
4. **Named container gating.** Rules are owned by body `b{i}`, and names are carried only while the body is awake or near an awake body. A sleeping neighbourhood's rules cost nothing. The names are on **every** level, because Chrome only re-matches style-container-dependent rules for that container's direct children.
5. **#LS / #LT split.** The clock and time budget moved into #LT, plus a plain wrapper before L0 and `.rz` zeroing the pointer. Idle style cost fell from 13.6 to 1.0 ms per frame at 32 bodies.†
6. **Two registers per element** (top and left), which halves the register elements.
7. **Timeline scope split** into a nest of `.ts` wrappers with 24 names each. The scope-list lookup became about 3× cheaper.
8. **Neighbourhood digests** (decimal words, 6 bodies per word) for the wake and sleep logic.
9. **Shared names for level-local props (`SHARE`).** The stylesheet shrank by about a third at 64 bodies.
10. **Larger scenes.** `_extend()` fills a floor grid and then upper layers, so there are 8–64 body pages.
11. **Multi-page site.** One page per count; the CSS is split above 14 MB for the artifact host's file limit.

Results at 32 bodies (old → new):†

| Metric | Old | New |
|---|---|---|
| Load | 2.9 s | 0.8 s |
| Idle style per frame | 13.6 ms | 1.0 ms |
| Hover style per frame | 28.8 ms | 2.0 ms |
| Rain chaos | 6–9 fps | 8–13 fps |
| Drag | 11 fps | 14 fps |

At 24 bodies drag ran at 18 fps; at 48 bodies drag was 4–5 fps and hold 8 fps; the 64-body page loads in 3.6 s.†

## Phase 3: bug fix and architecture exploration, Oct 11

- **Fixed:** floor-grid upper layers started asleep and floated in mid-air. The cause was that any body placed with zero velocity started asleep. Now a body starts asleep only if its lowest point touches the floor.
- **Measured the cost model precisely**, then evaluated alternative substrates and strategies. Most were rejected; see below and ROADMAP.md.

---

## Paths that didn't work (or didn't pay)

Each entry gives what was tried, what happened, and why.

### Solver and physics

- **Planes solved last** in the Gauss–Seidel order. A stack's floor push never reached the bodies above it within the step, so stacks settled into a state with phantom downward velocities and never slept. Reverted to planes first.
- **Soft box/box patch (`PATCHB=soft`).** One contact at the incident box's soft support patch. Leaning piles jitter and never sleep. Kept only as an experimental option.
- **Depth-weighted box/plane patch (`PATCHW=depth`).** Over-levels tilted boxes, and they rock every other step.
- **Velocity-based sleep test.** Phantom split-impulse velocity on resting boxes kept them awake.
- **Larger timestep** (RATE 60 or 45) to get more simulated time per step. 32-body piles never fully slept within 25 s, while RATE 90 settled in about 16 s. (At RATE 60, stacks also sink.)
- **Starting every zero-velocity body asleep.** Caused the floating-sleeper bug, now fixed.

### Style engine mechanics

- **Unnamed `@container style()` gates.** Each rule costs about 2.5–3.5 µs per pass whether it matches or not, and that dominated the cost of sparse scenes. Replaced by owner-named containers.
- **Container names on L0/L1 only.** Named rules at deeper levels didn't re-match. Fixed by putting the names on every level.
- **`@function`** is about 2–3× slower than the same math written inline.†
- **`if()`-based selection inside hot properties** costs about 4.2 µs per property, against about 2 µs for plain calc.
- **Anchor-positioned registers** (reading state through anchor positioning instead of view timelines) cost about 5 ms of layout per frame.† Reverted.
- **Moving the `.ts` timeline-scope wrappers inside `.rz`** made rendering vanish. They stay above `#RB`.
- **Explicit inheritance of #LS's children** and the live toggle on #LS made idle cost 15 ms.† Fixed by the #LT split, the plain wrapper and `.rz`.
- **Compositor interpolation of body poses (2026-10-13).** The idea: `transition: transform` on the bodies, so the compositor glides between poses at 60 fps while the physics runs at 4–9 fps. A `SMOOTH=<ms>` build option tried it and was removed. Three problems:
  - **It doesn't fire on `.bw`.** `.bw` gets its pose from its own (view-timeline) animations, and changes caused by an element's own animations don't start transitions. Only `.bd`, which inherits the quaternion, transitioned, so the first test smoothed rotation only. Moving the translation onto `.bd` (and the sphere `.disc`) made both transition.
  - **It's broken: bodies jump back and forth.** Every transition starts from the pose's *base* value (`--Rx: var(--ix…)`, the scene's spawn point), not the animated pose or the running transition. Each physics frame, every moving body snaps back toward its spawn point and glides forward again. `tools/transcheck.js` found 677 of 935 transitions restarting more than 2 px off (up to 216 px); `tools/filmstrip.js` scored 122 snap-back cells per 1000 against 1.5 without it. Passing the pose through an unregistered copy failed the same way; a minimal view-timeline page didn't reproduce it.
  - **It halves the physics rate.** Each transition restart costs time in proportion to the page's registered properties (24,896 at 48 bodies, about 1.25 ms per body per pass). At 48 bodies the main thread fell from 8.7 to about 4 fps, and settling took 21.5 s instead of 9 s. Registrations are page-global, so CSS can't avoid it.
  - Settled screenshots and draw counts (60/s) looked perfect throughout; only frame-by-frame checks showed the glitch.
- **Hypothesis rejected: quadratic copying of inherited custom properties down a deep chain.** A microbenchmark showed no difference between inherited and non-inherited across 50 levels (4.8 ms either way for 2,000 props). Blink doesn't copy per level in a way that matters here.

### Alternative compute substrates (Phase 3)

- **Variable-font metrics as style-time compute** (`ch`, `ic`, `ex`, `cap`, driven by `font-variation-settings`).
  - **It works:** in Chromium 141, `1ch`/`1ic` return exact HVAR glyph-advance polynomials and `1ex`/`1cap` exact MVAR values in the same style pass, with no layout. Bilinear (x·y) regions are exact. See `experiments/fonts/`.
  - **It doesn't pay:** every new set of axis values creates a font instance, costing about 15–20 µs for a 2-axis font, 35 µs at 8 axes and 80 µs at 64 axes, plus about 0.1 µs per region term. That gives 4 outputs, with 14-bit (F2DOT14) inputs. A wide multiply-add is about 4× cheaper than calc() (0.1 vs about 0.4–0.5 µs per term), but the setup cost equals 10–30 CSS properties.
  - **Why not for rigid bodies:** the math is narrow and branchy (SAT, clipping, clamps), with coefficients that change every step. Computing a rotation matrix in a font is about 105 µs, against about 36 µs in CSS.
- **Glyph shaping (GSUB) as an arithmetic engine.** About 25 ns per glyph per lookup (measured in a related HarfBuzz project), but byte-level arithmetic needs dozens of lookups per multiply, and fonts carry no state between frames: every output still has to go through registers. At best this breaks even with calc().
- **avar2** adds a hidden layer (axes → axes), but doesn't fix the per-instance cost or the input precision. It shipped in Chrome 148; the sandbox Chromium is 141, and Chromium 153 was used for avar2 tests.
- **Paused animations as evaluators** (`animation-delay: calc(var(--x) * -1s)` with paused keyframes, adding several animations with `animation-composition: add`). About 400 µs per element, likely because a changing delay re-creates the animation. Dead.
- **`ident()` / `var(ident(…))` for dynamic indexing** would have allowed a few contact slots per body instead of fixed all-pairs slots. Not supported in Chromium 141 or 153.
- **Process parallelism with iframes.** Cross-site iframes (e.g. 127.0.0.1 and 127.0.0.2) do run in separate renderer processes, giving 2× throughput on the 2-core sandbox. Sandboxed same-origin frames share **one** process (also with `--enable-features=IsolateSandboxedIframes`). And the only script-free channel between frames is the iframe's size, which flows parent to child only. So one world can't be split across processes, and a single-origin artifact can't use this at all.
- **Newer Chrome.** Chromium 153 is only about 10–15% cheaper per property than 141.

### Algorithmic ideas evaluated, not yet tried (see ROADMAP.md)

- **Spheres only** with the current engine: 1.5–2.5× faster per step at the same body count, which buys about a third more bodies (48 → 64) at equal fps. Not dramatic on its own: per-body overhead, registers and the N² pair table remain.
- **AVBD** (Giles, Diaz and Yuksel, SIGGRAPH 2025). Body-centric gather (good for CSS) and stable stacks at few iterations. But the per-body 6×6 Hessian plus LDLᵀ is costly in calc, and warm starting needs per-contact persistent state, i.e. registers. Recommended prototype: plain JS outside the browser first.
