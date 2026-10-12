# Roadmap and open ideas

The goal: **as many objects on screen as possible, with smooth animation and interaction**, in pure CSS. Chrome only.

## What the measurements say (see BENCHMARKS.md)

- **Fixed per-property cost dominates.** A registered property costs about 1.5–2 µs, plus about 0.35 µs per operation and about 0.5 µs per `var()`. The engine is within roughly 2–3× of what this substrate can do for the same math, so big wins must come from **doing less work**, not from cheaper arithmetic.
- **Registers cost about 10 µs per stored value per pass** (about 20 µs per element of 2 values). That sets a floor on world state: 1,500 changing values per pass is already 15 ms, whatever the solver.
- **N² work is about 28% of a 48-body step and grows quadratically:** the broadphase near tests plus the owner-named pair rules that are evaluated while their body is awake.
- **Pair slots must be fixed in the stylesheet.** CSS can't write to a computed index, and `ident()` isn't available, so nothing scatters.
- **Free filter:** a `@container` rule naming an absent container costs ≈0, even 50,000 of them, even nested.
- **Fonts carry no state between frames.** At style time an instance gives 4 outputs, inputs are 14-bit, a new instance costs 15–80 µs, and a cached instance is free.

## Ranked candidates

| # | Idea | Fit | Expected gain | Status |
|---|---|---|---|---|
| 1 | **Spatial partitioning by container names** | excellent | removes most of the N² work: ~20–25% at 48 bodies, ~30% at 64, essential beyond ~100 | designed, not built |
| 2 | **Compositor interpolation of the render** | excellent | 60 fps visuals regardless of physics cost (it doesn't make physics faster) | measured feasible |
| 3 | **Lean sphere engine** (no box machinery, rotation for rendering only, packed registers) + #1 | excellent | estimate ~150–250 spheres at today's 48-body frame rates | proposed |
| 4 | **Two tiers:** a few full-solver boxes + many cheap spheres pushed one way | excellent | keeps box stacking, adds hundreds of debris objects | proposed |
| 5 | **Packing two values into one register coordinate** (about 13 bits each) | good | ~1.5–2× less register cost | proposed |
| 6 | **AVBD** (Giles et al. 2025): body-centric primal solver | medium | stable stacks at 60 Hz (1.5× fewer steps), robust to mass ratios | prototype in JS first |
| 7 | **Particle–grid hybrid with the font doing the splatting** (PIC/FLIP/MPM, SPH) | interesting, a separate demo | the one place fonts do something CSS can't | speculative |
| 8 | Lattice Boltzmann or a grid fluid | good for CSS (fixed neighbours), wrong goal | a fluid demo | idea |
| 9 | Linear modal soft-body wobble via HVAR (fixed matrix × state) | fonts' best mathematical fit | visual polish only | idea |
| 10 | GSUB sort-and-sweep broadphase | speculative | cheap sorting, but neighbour lists still need dynamic indexing; one frame of lag | idea |
| — | Font lookup tables, box shape-matching, DEM penalty contacts, event-driven motion, learned surrogates | poor | — | rejected (HISTORY.md) |

### 1. Spatial partitioning (design)

1. **Advertise cells.** Before L0 (on a wrapper between #LT and L0), each awake body advertises cell names for the grid cells its padded bounding sphere overlaps. Use x bands and z bands, at most 2 names per axis, e.g. `X5_3` and `Z5_1`, computed from the stored positions with small `if()` chains. With cell size ≥ the largest interaction distance, near pairs always share a cell.
2. **Wrap each pair's near test** in nested rules, one set per (u, v) cell:
   `@container X{a}_{u} { @container X{b}_{u} { @container Z{a}_{v} { @container Z{b}_{v} { #L0{ --np{a}_{b}: … } } } } }`
   Chrome only evaluates rules whose names are all present, so the cost scales with the pairs that actually share a cell.
3. **Gate pair blocks by a per-pair name** emitted only when `np = 1`. Each awake pair contributes `var(--Np{a}_{b}, )` to the `container-name` list (about 0.3 µs per lookup; declared only inside the cell rules). This replaces the owner-name gates for pair blocks, so an awake body's far-away pairs cost nothing.
4. **Mind the stylesheet size.** Flag rules repeat once per cell: 24–40 per pair, adding about 5–10 MB at 48 bodies and about 60 MB at 128. Option: x bands only (8 repeats per pair), which still skips about 75% of the tests.
5. **Verify** with `tools/ablate.py` and frozen piles at 48 and 64, then `tools/smoke.sh`.

### 2. Compositor interpolation

- **The change:** `.bw, .bd { transition: transform Xms linear }`. Match X to the measured frame interval (the engine knows the frame dt from `TP`/`DB`), e.g. `transition-duration: calc(var(--fdt) * 1s)`. Also smooth the grab ring, pin and tether, or they will visibly lead the bodies.
- **Trade-offs:** drawn positions lag by about one physics frame, and heavy scenes still run in slow motion, but smoothly.
- **Measured:** 59 compositor fps with the main thread at 8 fps (synthetic), and 29–36 at 48 bodies on the 2-core sandbox.

### 3 and 4. Leaner bodies

- **Sphere-only estimate:**
  - about 20 props per sphere (integration, floor and walls) and about 15 per contact, so 200 spheres with about 400 contacts is about 30 ms per step;
  - registers about 12 ms per pass (200 × 6 values), or about 6 ms with #5;
  - #1 is required: 200 bodies is 19,900 pair tests (≈250 ms) without it.
- **Two-tier debris:**
  - sphere/sphere contacts;
  - sphere vs hero box (one clamp in the box frame, about 12 props);
  - the planes;
  - no forces fed back into the boxes.

### 6. AVBD

- **For it:** gather-only (a body reads its neighbours, no scatter), which suits the level chain and could remove the K/J/JP accumulator machinery. Contacts are linearised once per step, and hard contacts stay stable at low iteration counts.
- **Against it:**
  - the per-body 6×6 Hessian plus LDLᵀ is costly in calc;
  - warm starting needs persistent per-contact λ and stiffness, i.e. registers per contact, and that's N² DOM with fixed pair slots;
  - GPU-style colouring is irrelevant in single-threaded CSS.
- **First step:** a plain-JS simulator outside the browser, run on the tower, stack and rain scenes. Measure the iterations and step rate needed with and without warm starting, and the operations per body-step, against the current solver.

### 7. Font splatting

- **The idea:** an HVAR region is a product of tent functions over its axes. With particle coordinates as axes, the region for (particle p, node k) **is** the bilinear splatting kernel. A grid node's glyph advance then equals Σ_p tent(x_p − X_k)·tent(z_p − Z_k), i.e. particle-to-grid scatter from a fixed font. Momentum needs a third, linear factor on the velocity axis; interpolating back to particles works the same way.
- **The catch:** the cost scales with regions × axes (region records span every axis) and axes ≈ 2–3 × particles. My estimate is that it beats calc() only up to ~100 particles on an 8×8 grid.

## Open questions worth a quick test

- What exactly makes a new font instance cost 15–80 µs, and does a minimal font (no glyf, tiny tables) cut it?
- How does Chrome's FontCache behave with ~10k new instances per second (memory, the 100–150 ms spikes)?
- Do compositor transitions hold 60 fps on a GPU machine at 64 bodies?
- Register packing: what precision does each field really need? Positions about 0.01 px; velocities?
