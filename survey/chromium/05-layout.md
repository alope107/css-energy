# 05. LayoutNG: caches, invalidation, anchors, and layout as a compute substrate

Scope: the layout engine (`core/layout`), its caches and dirty bits, out-of-flow and anchor positioning, size
containers seen from layout, the layout algorithms that compute something (flex, grid, grid-lanes, tables, multicol,
`text-wrap`, intrinsic sizes), inline layout of one long line, `content-visibility`, and the precision of layout
geometry. Neighbours: [01](01-lifecycle.md) (how many passes a frame runs), 02 (style recalc itself), 03 (counters,
values), [04](04-animations-and-scroll.md) (timelines, snap, scroll anchoring, register precision on the timeline
side), 06 (shaping inside inline layout).

Sources: Chromium main `22b3b159` (M158) and the M153 branch tree (`refs/branch-heads/8010`). `core/layout` is
identical between them in everything this chapter relies on unless §3 says otherwise *(code: `diff -ru`)*. Path
abbreviations: `L/` = `third_party/blink/renderer/core/layout/`, `C/` = `third_party/blink/renderer/core/`,
`P/` = `third_party/blink/renderer/platform/`. Line numbers are main's.

Probes *(measured)*: headless Chromium 153.0.8010.12 on the mini PC with other agents running, so read ratios, not
absolutes. Each probe builds a page from a test harness (JS only in the harness), changes one tiny "driver" box per
iteration and times the forced style+layout (`offsetWidth`) with `performance.now()` (0.1 ms resolution), median of
150–300 iterations, 2–3 rounds. Scripts: `exp/05/exp/*.js` (scratch, not in the repo); each probe is described
where it's used, enough to rebuild it.

## Findings in brief

1. **Every anchored out-of-flow element is restyled and force-relaid-out every time its containing block runs its
   out-of-flow pass**, changed or not: `ElementStyleDependsOnAnchor` → `UpdateStyleAndLayoutTreeForOutOfFlow` →
   `SetNeedsLayout(kAnchorPositioning)` (`L/out_of_flow_layout_part.cc:252-346`). +2.25 µs per element at shallow
   DOM depth, ~65 µs at depth 2,000; 0 if the element sits under its own containing block that isn't dirty
   *(code, measured)*. This, not only size containers, is why js-minus-js's console readers restyle every pass.
2. **ENGINE_NOTES 40, root cause:** every rebuilt fragment on the path from an anchor to the root re-allocates a
   `PhysicalAnchorReference` (with a float `TransformState`) for **every** anchor below it
   (`L/anchor_map.cc:154-199`): ~66–200 ns per anchor per rebuilt level. 16,384 anchors in 64 group boxes under
   `<body>`: 9–10 ms per pass; nothing scopes it (`anchor-scope` and containment don't; only a locked
   `content-visibility` stops it) *(code, measured)*.
3. **Interleaved recalcs cost O(DOM depth) each:** the selector filter pushes every ancestor
   (`C/css/resolver/selector_filter_parent_scope.cc:10`), `StyleRecalcContext::FromInclusiveAncestors` walks to the
   root, and each named anchor walks its ancestors for `anchor-scope` (`L/naming_scope.cc:42`). In js-minus-js's
   compile chain (depth ~2,000) each displayed code-word overlay, which reads a label with `anchor-size()`, costs
   ~65 µs every time `#tcr` is laid out *(measured synthetic)*.
4. **A `display: contents` chain restyles in O(D²):** each resolve walks all `display: contents` ancestors to find the
   layout parent (`C/dom/layout_tree_builder_traversal.cc:68-78`). 1,561 levels: 4.5–8.1 ms per full-chain restyle
   against 1.1–1.8 ms with a zero-height block every 64 levels *(code, measured)*.
5. The layout cache compares the **would-be size**, not the constraint space (`L/layout_utils.cc:176`): an unchanged
   box under a re-laid-out parent is O(1). 4,000 unchanged siblings cost < 0.1 ms per pass *(code, measured)*.
6. **Relayout boundaries never form around anchors or escaping out-of-flow boxes** (`L/layout_object.cc:1439-1586`,
   "Anchors should be propagated across the layout boundaries, even when `contain: strict`"), so on both pages every
   pass lays out from `LayoutView`. What `contain: strict` buys (ENGINE_NOTES 20) is a fixed-position containing block
   that stays a cache hit *(code)*.
7. A size container restyles only when its **content-box size** differs from the last evaluated one
   (`C/css/container_query_evaluator.cc:354`); `cq*` units make any change recalc every dependent element below
   (`kDescendantContainers`), traversing the whole subtree down to nested containers *(code)*. ENGINE_NOTES 34 holds.
8. **Geometry passes through float in three places**: CSS lengths (`Length` stores `float`, `P/geometry/length.h:433`),
   anchor rects (`TransformState` quads, `L/anchor_map.h:52-55`), remembered sizes (`gfx::SizeF`). `LayoutUnit` is
   1/64 px in int32 (±33,554,431 px, saturating). Bigger scrollers don't buy register bits (04 §1.5) *(code)*.
9. Layout reductions (sum, max, prefix sums) are **not cheaper than style**: a readback reader costs ~2.4 µs per pass
   and arrives a pass later; a chained registered property is ~2.5 µs. Layout wins only where style has no primitive:
   addressing by value (grid placement, anchor names), sort (`order`: `std::stable_sort`, 2.4–3.4 µs per item per
   pass), argmin (snap, grid-lanes), optimal partition (`flex-wrap: balance`) *(code, measured)*.
10. **Bug:** grid track sizing multiplies raw extra space by a track count in 32-bit unsigned
    (`L/grid/grid_track_sizing_algorithm.cc:686-687`); 70,000 px over 1,000 + 999 auto tracks gives the first set
    1,446 px instead of 35,017 px, in 153 and main *(code, measured)*.
11. **Possible bug:** a `content-visibility: hidden` element with its own `anchor-name` is not an anchor
    (`L/fragment_builder.cc:363-367` returns before registering the child's own name); the spec only excludes
    elements *in* skipped contents *(code, measured)*.
12. 153 → main: anchor and cache code unchanged; 155 fixed an O(N² log N) tree-order sort of out-of-flow candidates
    when anchors are involved (`L/fragment_builder.cc:787-830`); gap decorations shipped; grid-lanes still
    experimental; `flex-wrap: balance` + `flex-line-count` are already stable in 153 *(code)*.

---

## 1. How it works

### 1.1 Two trees and the inputs to a layout

```
DOM + ComputedStyle ──attach──▶ LayoutObject tree (mutable, one per box; display:contents/none make none)
                                   │  dirty bits live here; the last LayoutResult is cached on each LayoutBox
                                   ▼
               BlockNode::Layout(ConstraintSpace) ──▶ LayoutAlgorithm (block, flex, grid, table, column, …)
                                   │
                                   ▼
               LayoutResult { PhysicalBoxFragment (immutable, children + offsets),
                              BFC offset, end margin strut, exclusion space, OOF descendants,
                              AnchorMap, snap areas, intrinsic block size, flags }
```

- `LayoutInputNode` / `BlockNode` / `InlineNode` are thin handles over a `LayoutBox` that algorithms traverse
  (`L/layout_input_node.h`, `L/block_node.h`). The inputs to an algorithm are only the node, its style, its children
  and the `ConstraintSpace` (`L/layout_ng.md`): available size, percentage resolution size, fixed-size flags, BFC
  offset, margin strut, exclusion space (floats), fragmentation state, and a **cache slot**
  (`enum class LayoutResultCacheSlot { kLayout, kMeasure }`, `L/constraint_space.h:89`).
- Output is a fragment tree. Positions in fragments are physical and relative to the parent fragment. Paint and
  hit-testing walk fragments, not LayoutObjects.
- A box may be laid out several times per pass with different spaces: flex and grid run "measure" layouts
  (kMeasure slot, `L/measure_cache.h:33`: 8-entry LRU) before the final one; min/max (intrinsic) sizes have their own
  8-entry cache keyed on the initial block size (`L/min_max_sizes_cache.h:32`) *(code)*.

### 1.2 Dirty bits and how they climb

Three layout bits per LayoutObject (`L/layout_object.h:1477-1500`): `self_needs_full_layout_`,
`child_needs_full_layout_`, `needs_simplified_layout_`; plus intrinsic-widths-dirty and `NeedsCollectInlines` for
inline formatting contexts. Marking (`MarkContainerChainForLayout`, `L/layout_object.cc:1656-1730`):

- Walks `Container()` upward setting `child_needs_full_layout_` until it meets an ancestor already marked.
- **An out-of-flow box jumps to its containing block and switches to simplified marking**: from there up, ancestors
  get `needs_simplified_layout_` instead (`:1699-1703`).
- Stops at a relayout boundary (§1.4) and schedules a subtree layout there; otherwise reaches `LayoutView`.
- A display-locked box (`content-visibility`) stops propagation of its children's bits (`:1686-1692`).

Style changes enter through `LayoutObject::SetStyle` (`:3356-3368`, `:3596-3605`): `NeedsFullLayout` diffs mark the
box itself; **inset-only diffs (`NeedsPositionedLayout`) on an out-of-flow box mark only its containing block for
simplified layout**; and any style change on a box with anchor functions does the same
(`HasAnchorFunctionsWithoutEvaluator`, `:3361`) *(code)*.

**Simplified layout** (`L/simplified_layout_algorithm.cc:219-304`) reuses the previous fragment's in-flow children
as they are (calling `SimplifiedLayout` on each, which is a cache hit unless that child is dirty), **re-adds every
direct out-of-flow child as a candidate** and runs the out-of-flow pass again. It gives up (full layout) on fragments
with inline items. This is the path every css-physics register write takes (§2.3) *(code)*.

### 1.3 The layout cache

`BlockNode::Layout` (`L/block_node.cc:407-650`):

```
needed_layout = box.NeedsLayout()
result = box.CachedLayoutResult(space, …, &status)          // L/layout_box_hot.cc:72
if status == kHit and !NeedsLayout: return result           // O(1): no children visited
if size container: UpdateStyleAndLayoutTreeForSizeContainer  // §1.7, then try the cache again (:486-516)
if status == kNeedsSimplifiedLayout: RunSimplifiedLayout     // :540
elif status == kCanReuseLines: params.previous_result = …    // inline line-box reuse (:547)
else: LayoutWithAlgorithm
scrollbar change → freeze scrollbars and relayout, in a loop (:590-640)
```

`CachedLayoutResult` (`L/layout_box_hot.cc:72-330`) returns null (miss) for `SelfNeedsFullLayout`, a child needing
full layout (except inline children, where lines may be reused), fragmentation changes, floats, and size changes. The
size test (`CalculateSizeBasedLayoutCacheStatusWithGeometry`, `L/layout_utils.cc:176-379`) **computes the box's size
under the new space and compares it with the cached fragment**: different inline size or padding → miss; for an
auto block size it recomputes the block size from the cached *intrinsic* block size, so a parent whose available
height changed still hits if the child's final size doesn't. Flex, grid and grid-lanes miss whenever the old space
had a fixed block size or %-block-size inputs changed (`:255-284`) because their children can stretch to it. Outside
the formatting context, a BFC-offset change can still hit through `MaySkipLayoutWithinBlockFormattingContext`
(`:450`) *(code)*.

Measured: 4,000 unchanged boxes as children of a box re-laid out every pass add < 0.1 ms per pass (probe b0)
*(measured)*. The cache makes "layout from the root every pass" cheap; what costs is what the cache can't skip (§1.5,
§1.6, §1.7).

### 1.4 Relayout boundaries

`ObjectIsRelayoutBoundary` (`L/layout_object.cc:1439-1586`) decides whether dirty bits may stop at a box and the
frame lay out only that subtree (`LocalFrameView::ScheduleRelayoutOfSubtree`). Requirements, in order:

- a cached result whose fragment has no break token, **no propagated out-of-flow descendants, no child anchors**
  (`:1475-1478`: "Anchors should be propagated across the layout boundaries, even when `contain: strict` is
  explicitly set"), and is a formatting-context root;
- a self-painting PaintLayer (positioned, stacked, or `contain: paint`) or an SVG root; not a table part, flex item,
  grid item or non-root MathML; an out-of-flow box only with non-auto insets;
- then either **`contain: layout` + size containment** (`:1535-1538`, i.e. `contain: strict`/`size layout`), or
  fixed `width` and `height` + overflow clipped on both axes (or a text control); never inside fragmentation.

Consequence *(inference)*: a subtree holding any anchor, or any fixed/absolute box whose containing block is outside
it, never becomes a boundary, so its changes lay out from `LayoutView`, including `LayoutView`'s out-of-flow pass over
every fixed box it contains. Both projects' pages qualify on every pass.

### 1.5 Out-of-flow layout and the anchored-element restyle

Out-of-flow (OOF) boxes are skipped by their parent's algorithm and bubble up in the `LayoutResult` (with a static
position) until the builder of their containing block runs `OutOfFlowLayoutPart::Run`
(`L/out_of_flow_layout_part.cc:614`). Per candidate (`LayoutCandidates`, `:1107-1230`):

1. If any candidate may contain an anchor, the candidate list is first sorted into tree order
   (`SwapOutOfFlowPositionedCandidates`, `L/fragment_builder.cc:787-830`) with `IsBeforeInPreOrder`, which walks to
   the common ancestor and then *siblings* (O(depth + siblings)). 153 has no index cache: O(K log K × siblings) at a
   containing block with K candidates. 155+ builds a child-index map when K > 32 (`kIndexCacheMinSize`) *(code)*.
2. `SetupNodeInfo` + `CalculateOffset` (`:2074-2286`): builds an `AnchorEvaluatorImpl` over the containing block's
   `AnchorMap`, then an `OOFCandidateStyleIterator`. Its `Initialize` (`:252-276`):
   ```cpp
   if (position_try_fallbacks_ || ElementStyleDependsOnAnchor(*element_, *style_)) {
     UpdateStyle(std::nullopt, /*initial_update=*/true);
   ```
   `ElementStyleDependsOnAnchor` is true for any `anchor()`/`anchor-size()` in the style or a named (or implicit)
   `position-anchor` (`:279-300`). `UpdateStyle` (`:305-346`) calls
   `StyleEngine::UpdateStyleAndLayoutTreeForOutOfFlow` (`C/css/style_engine.cc:4084-4152`): an interleaved style
   recalc rooted at the element, `StyleRecalcChange().ForceRecalcChildren()` (the element itself always; children only
   if its inherited style changed), with the evaluator installed so anchor functions resolve. Then
   `layout_object->SetNeedsLayout(kAnchorPositioning, kMarkOnlyThis)`: **the element misses the layout cache**.
3. `position-try-fallbacks`: up to `kMaxTryAttempts = 5 + 1` styles (`:1991`), each another interleaved recalc and
   `TryCalculateOffset`; the last successful option is tried first; `position-try-order: most-width/height` is a
   `std::stable_sort` of the fitting options by inset-modified containing block size (`:2033-2070`, sort at
   `:2051`), an argmax over ≤ 6 candidates. `position-area` shrinks the containing block rect
   (`AdjustedContainingBlockRect`); `position-visibility: no-overflow` and `anchor-valid` (157+) set PaintLayer flags; `anchors-visible` uses a
   post-layout IntersectionObserver (`:439-480`). Anchored container queries (`container-type: anchored`) are applied
   inside the same interleaved recalc (`ApplyAnchoredChanges`, `C/css/style_engine.cc:4122`).
4. `LayoutOOFNode` → `GenerateFragment` → `BlockNode::Layout` with a fixed inline size (`:2748-2855`): a cache hit for
   unchanged non-anchored boxes, a miss for anchored ones (step 2).

So the anchor positioning model is "resolve style late": the main recalc resolves anchor functions to their
fallbacks, and the real values come from a second, per-element recalc inside layout, repeated **every time the
containing block's OOF pass runs** *(code)*.

Probe E1 *(measured)*: 2,000 `position: fixed` boxes, a driver box in `<body>` changed every pass:

| Fixed boxes | ms per pass | Per box |
|---|---|---|
| `width: 50px` | 0.9 | 0.45 µs (offset + cache hit) |
| `width: anchor-size(--a width)` (one static anchor) | 5.4 | +2.25 µs (restyle + relayout) |
| same, but boxes and anchor inside a `contain: layout; position: relative` wrapper the driver isn't in | < 0.1 | 0 |

### 1.6 Anchor maps: collection, propagation, lookup, evaluation

**Collection and propagation.** There is one physical map per fragment (`AnchorMap`, `L/anchor_map.h:94-235`: a
named map keyed by `AnchorScopedName` and an implicit-anchor map keyed by element; the old logical/physical query
pair is gone; logical values are converted at evaluation). When a builder adds a child fragment,
`PropagateChildAnchors` (`L/fragment_builder.cc:322-415`, two overloads):

- returns if the child element's display lock is locked (`:363-367`), so nothing at or under a locked
  `content-visibility` element propagates;
- if the child is an anchor, maps its border box to the container through `UpdateTransformState`
  (`L/transform_utils.cc:86-108`) and inserts one reference per name, after `ToAnchorScopedName` (`:393`), which
  allocates a `NamingScope` and walks **every flat-tree ancestor** looking for a matching `anchor-scope`
  (`L/naming_scope.cc:42-63`);
- then `AnchorMap::SetFromChild` (`L/anchor_map.cc:154-199`) **creates a new GC'd `PhysicalAnchorReference` for every
  reference in the child's map**, all of them, not just the winner per name ("the presence of anchor-scope can make it
  necessary to skip past any number of references … Therefore, all references must be propagated"), each with a
  `TransformState` re-mapped by the child's offset and transform.

A fragment that hits the cache keeps its map; its parent, if rebuilt, copies it again. Propagation continues to the
root: `HasChildAnchors()` disqualifies relayout boundaries (§1.4) and nothing else stops it. Cost model
*(code + measured)*: per pass, Σ over rebuilt fragments of the anchors below them.

| Probe (E2/E3, driver changed every pass) | Extra per pass | Per anchor |
|---|---|---|
| 4,000 named boxes in a clean wrapper, rebuilt levels above: body, html, view | 0.9 ms | 0.23 µs (≈75 ns per level) |
| same, wrapper under 40 rebuilt `flow-root` levels | 11.4 ms | 2.85 µs (≈66 ns per level) |
| same 40 levels, driver at `<body>` (levels are cache hits) | 1.1 ms | as the first row |
| 16,384 named boxes in 64 group boxes under body (memtree-like) | 9.1–10.3 ms | 0.55–0.63 µs (≈200 ns per level) |
| 1,000 anchors whose parent box is rebuilt, DOM depth ~3 | 0.3 ms | 0.3 µs |
| same at the bottom of a 400-level `display: contents` chain | 1.5 ms | 1.5 µs (≈3 ns per ancestor) |
| same, `anchor-scope: all` on the anchors' parent | 0.4 ms | walk cut to one step |

The per-level cost grows with map size (cache misses on a 16K-entry hash map); the garbage (one reference per anchor
per level per pass) is also Oilpan GC work not separated here.

**Lookup** (`AnchorMap::AnchorReference`, `L/anchor_map.cc:61-90`): each key holds a singly linked list in **reverse
tree order** (`InsertInReverseTreeOrderInto`, `:44-59`; O(k) per insert with `IsBeforeInPreOrder`); the first entry
that isn't the query box itself and, if out-of-flow, is laid out before it, wins. **That is ENGINE_NOTES 21**: with a
shared name the last element in tree order wins, unless it's an OOF box after the reader. Only anchors inside the
reader's containing block are in the map the reader sees (`CreateAnchorEvaluator` uses the containing block's
builder map, `L/out_of_flow_layout_part.cc:1726-1824`).

**Evaluation** (`L/anchor_evaluator_impl.cc:224-495`). Anchor functions are evaluated while the OOF element's style is
resolved (`CSSMathExpressionAnchorQuery::EvaluateQuery`, `C/css/css_math_expression_node.cc:4070-4084`), and only in
the properties `AnchorScope::PropertyMode` allows (`C/css/anchor_evaluator.h`): insets take `anchor()` and
`anchor-size()`, sizes and margins take `anchor-size()`, **anything else (custom properties included) gets the
fallback**. Each named evaluation calls `ToAnchorScopedName` on the *query box* (another ancestor walk),
`AnchorReference`, then `CalculateAnchorRectWithScrollOffset`, whose `ComputeAdjustmentContainersData`
(`L/anchor_position_scroll_data.cc:101-200`) walks containers from the anchor up to the reader's container looking for
scrollers. The anchor rect is `PhysicalRect::EnclosingRect` of the float quad (`L/anchor_map.h:52-55`).

**What scopes anchors, and what it saves** *(code; measured where marked)*:

| Mechanism | Who can read the anchor | Propagation cost |
|---|---|---|
| `anchor-scope` on an ancestor | only boxes inside that subtree | unchanged (all references still copied to the root); the `ToAnchorScopedName` walk stops at the scoping element (measured: 1.5 → 0.4 µs per anchor at depth 400) |
| `contain: layout`/`strict`, any containment | everyone | unchanged; also prevents the box from being a relayout boundary |
| the reader's containing block | only anchors inside the reader's containing block are in its map | unchanged; but a clean containing block skips the reader's restyle entirely (E1) |
| locked `content-visibility` (hidden, or auto off-screen) | nobody outside (the locked element itself included, §5) | none past the locked element |
| `display: none` | nobody | none (no fragment) |

### 1.7 Size containers inside layout

`BlockNode::Layout` calls `StyleEngine::UpdateStyleAndLayoutTreeForSizeContainer(element, available_size,
ContainedAxes())` on every cache miss of a size container's first fragment (`L/block_node.cc:486-516`), with the
content-box size (auto scrollbars ignored). In `C/css/style_engine.cc:3955-4040`:

```
change = evaluator.SizeContainerChanged(physical_size, axes)     // container_query_evaluator.cc:351
  if size_ == size && axes unchanged → kNone → return (unless a recalc was deferred)
  UpdateContainerSize; ComputeSizeChange re-evaluates every cached query result for this container (:761)
  return referenced_by_unit_ ? kDescendantContainers : change
kNearestContainer   → ForceRecalcSizeContainer
kDescendantContainers → ForceRecalcDescendantSizeContainers
RecalcStyle(change) rooted at the container; RebuildLayoutTree if needed; then layout continues
```

- **When it counts as dirty** (ENGINE_NOTES 34): when the box is laid out (cache miss) *and* its content-box size
  differs from the size last evaluated, in either axis. An auto block size is indefinite there and clamps to 0, so a
  content-sized height never dirties an `inline-size` container; a definite height that changes does, even for
  `inline-size` *(code)*.
- **What is restyled**: the traversal visits every descendant (`TraverseChild` is true while the flag is set,
  `C/css/style_recalc_change.cc:24-29`), but restyles only elements whose old style `DependsOnSizeContainerQueries()`
  (a size query was evaluated for it, or it used `cq*` units) (`:31-54`), plus normal inheritance fallout below them.
  With `kRecalcSizeContainer` the walk stops at nested size containers (`FlagsForChildren`, `:153-183`); their subtrees
  are resumed when *they* are laid out, so N nested containers give N interleaved recalcs per pass.
- **`cq*` units make it worse**: `referenced_by_unit_` turns any size change into `kDescendantContainers` even if no
  query result changed.
- **Cost per container** *(code; inference for magnitudes)*: a size compare when clean; when dirty, re-evaluation of
  its cached queries, O(subtree) traversal, one resolve per dependent element (2–3 µs plus declarations), and the
  O(DOM depth) setup of §1.8. `inline-size` vs `size` doesn't change the restyle logic; it changes which axes can
  dirty it and whether the container's own height may come from content.

### 1.8 Interleaved recalcs are O(DOM depth); `display: contents` chains are O(D²)

Each interleaved recalc root (an anchored OOF element in §1.5, a size container in §1.7) pays:

- `StyleRecalcContext::FromInclusiveAncestors` (`C/css/style_recalc_context.cc:44-95`): a walk to the document root
  with a `GetComputedStyle()` and a display-lock check per ancestor;
- `SelectorFilterParentScope` at the root (`C/css/style_engine.cc:4173`), whose `PushAncestors` recursively pushes
  **every ancestor** into the selector Bloom filter and pops them after
  (`C/css/resolver/selector_filter_parent_scope.cc:10-22`);
- for anchors, the `anchor-scope` walks of §1.6.

Probe *(measured)*: 500 `position: fixed` boxes inside a `contain: strict` box, at the bottom of a 2,000-level
`display: contents` chain vs directly in it; the driver is inside, so the box re-runs its OOF pass every pass:

| Fixed boxes (500) | depth 0 | depth 2,000 |
|---|---|---|
| plain | 0.2–0.3 ms | 0.3 ms |
| with `anchor-name` (distinct) | 0.6–1.1 ms | 3.7 ms (≈7 µs per anchor) |
| `width: calc(5px + anchor-size(--lab width, 0px))` | 1.5–1.8 ms | 33 ms (≈65 µs each, ≈31 ns per level) |
| both | 2.1–2.2 ms | 36.5 ms |

Separately, every style resolve builds an `ElementResolveContext` that calls
`LayoutTreeBuilderTraversal::LayoutParentElement` (`C/css/resolver/element_resolve_context.cc:107`), which loops up
through all `display: contents` ancestors (`C/dom/layout_tree_builder_traversal.cc:68-78`). Restyling a whole chain of
D `display: contents` levels is therefore O(D²). Attach, rebuild and recalc are recursive with no depth guard; the
HTML parser alone caps nesting at 512 (`C/html/parser/html_construction_site.h:78`, ENGINE_NOTES 19) *(code)*.

Probe *(measured)*: a chain where every level declares `--w: calc(var(--v) + 1)` and `--v` (registered, inherited)
changes at the top each pass:

| Chain | ms per full-chain restyle |
|---|---|
| 400 levels, all `display: contents` | 0.5 |
| 1,561 levels, all `display: contents` | 4.5, 8.1 |
| 1,561 levels, every 64th level `display: block; height: 0` | 1.8, 1.1 |
| 1,561 levels, every 8th level a block | 1.3, 1.7 |

The layout tree of an all-`contents` chain is flat (ENGINE_NOTES 20): every box generated anywhere in it is a direct
child of the nearest real box, so a change anywhere re-lays out that one parent, which iterates all its children
(cache hits) and re-propagates every anchor among them.

### 1.9 LayoutUnit, and where geometry passes through float

- `using LayoutUnit = FixedPoint<6, int32_t>` (`P/geometry/layout_unit.h:473`): 1/64 px, `kIntMax` = 33,554,431 px.
  `+`/`-` saturate (`base::ClampAdd`, `:646-651`); `LayoutUnit(float)` multiplies by 64 and **truncates** toward zero
  (`:125-130`); `x *= int` binds to a float overload. `TextRunLayoutUnit` (16.16) and `InlineLayoutUnit` (16.48) exist
  for text (`:474-475`) *(code)*.
- Every CSS length goes through `float` first: `Length` stores `float value_` (`P/geometry/length.h:433`),
  `PixelsAndPercent` floats (`:88-89`), `calc()` evaluates in float (`P/geometry/calculation_value.cc:41`). So a
  `top: calc(v * 1px)` write is exact to 1/64 only below 2^18 px; at 10^6 px it has 1/16 px steps *(code)*.
- Reads: view-timeline subject positions are `gfx::PointF` (`C/animation/view_timeline.cc:574`; chapter 04 §1.5 has
  the register arithmetic: ≈24 bits at 10^6 px, and a larger scroller gains nothing); anchor rects are float quads
  (`L/anchor_map.h:52-55`), so `anchor()`/`anchor-size()` of a box beyond 2^18 px can be off by up to 1/16 px;
  remembered sizes go `LayoutUnit` → `gfx::SizeF` → `double` → `LayoutUnit`
  (`C/resize_observer/resize_observer_utilities.cc:34-45`, `C/dom/element.cc:2581-2588`), exact for integers below
  2^24 px; scroll offsets are `gfx::Vector2dF` (`C/scroll/scroll_types.h:42`) and integer-snapped in 153
  (`FractionalScrollOffsets` is experimental from 155) *(code)*.
- Maximum scrollable extent: the LayoutUnit limit, ~3.36·10^7 px; overflow rects saturate rather than wrap. Integer
  words survive every path above up to 2^24 px *(code)*.

### 1.10 Inline layout of one long line

From the source *(code, via a sub-agent's line-by-line read, spot-checked)*:

- `InlineNode::PrepareLayoutIfNeeded` (`L/inline/inline_node.cc:622-646`) re-collects the **whole** inline formatting
  context only if `NeedsCollectInlines` is set: `CollectInlines` (iterative, `:340-468`) → `SegmentText` →
  `ShapeTextIncludingFirstLine` → associate items. A changed counter text (`LayoutCounter::UpdateCounter` →
  `SetTextIfNeeded`, no-op when equal) sets it (`L/layout_text.cc:1047-1049`); so does any `font`, `direction`,
  `text-transform`, `white-space-collapse` or `text-wrap-mode` change. `padding`, `margin`, `line-height` and
  `vertical-align` relayout without re-collecting.
- Shaping runs span inline boundaries: consecutive text items with the same font, direction and segment, and no
  inline padding/margin/border or non-baseline `vertical-align` between them, are one `HarfBuzzShaper::Shape` call
  over the context's whole text (`:1620-1706`, ENGINE_NOTES 30); results are split per item with `CopyRanges`. Any
  change in a run reshapes the whole run. Details: chapter 06.
- Line breaking: `white-space: pre`/`nowrap` skips `ShapingLineBreaker` entirely (`L/inline/line_breaker.cc:1407`,
  `:1496-1518`): per item an `InlineItemResult`, a `ShapeResultView` (O(runs)) and a snapped width. Line-box reuse
  never applies to the last line (`L/inline/fragment_items.cc:350-352`), so a one-line context is fully re-broken
  whenever its block misses the cache.
- `::before`/`::after` inlines always get box fragments (`CanBeHitTestTargetPseudoNodeStyle`,
  `L/layout_inline.cc:62-75`): one `PhysicalBoxFragment` + `LayoutResult` per pseudo per layout. Inline boxes with
  inline margin/border/padding make `ComputeInlinePositions` O(boxes × items) (`L/inline/inline_box_state.cc:892-902`).
- `width: max-content` on the line's container adds `InlineNode::ComputeMinMaxSizes` (1–2 more line-breaker passes,
  `:2308-2343`) when intrinsic widths are dirty.

Probe *(measured)*: a `position: fixed; white-space: pre` line of N spans, each `::before { content: counter(c) }`,
16 px monospace (cheap shaping), one counter changed per pass: N = 150: 0.4–0.6 ms; N = 1,274: 3.8–4.3 ms; no
change: < 0.1 ms (the line is a cache hit). `max-content` vs a fixed width: no measurable difference. So ~3 µs per
span per changed pass including the (cheap) reshape.

### 1.11 Flex, grid, grid-lanes, tables, multicol, `text-wrap`, intrinsic sizes

The arithmetic, as a compute engine sees it *(code; citations from a sub-agent's read, constants spot-checked)*:

- **Flex.** `order` is `std::stable_sort` over the children (`L/flex/flex_child_iterator.cc:28-33`), only when some
  order differs, rebuilt on every flex layout (no cache). A row's max-content width is the **sum** of item
  contributions plus gaps, max over lines (`L/flex/flex_layout_algorithm.cc:2889-3025`); a column's is the max. Item
  offsets are a running `LayoutUnit` sum (`:2035-2043`). Distribution (`L/flex/line_flexer.cc`) uses double factor
  sums and `FromDoubleRound`, the remainder absorbed by the first item, freeze loop ≤ n iterations. Typically one
  measure + one final layout per item. Sort probe *(measured)*: N items with
  `order: calc(mod(var(--i) * 7919 + var(--seed), N))`, `--seed` changed on the row every pass: N = 1,000: 4.0 ms
  against 1.6 ms for the same restyle without `order`; N = 10,000: 48.8 against 15.2 ms. So a re-sort costs
  2.4–3.4 µs per item per pass, slightly superlinear.
- **`flex-wrap: balance`** (stable since 150, flag `FlexWrapBalance`) with `flex-line-count: N` (uint16,
  interpolable, `C/css/css_properties.json5:3686-3697`): a prefix-sum array, Knuth–Plass-style DP minimising Σ
  slack² with memoised scores, and a **bisection of the line width** with `std::upper_bound` greedy counts to reach at
  least N lines (`L/flex/flex_line_breaker.cc:73-210`). An optimal-partition solver in layout.
- **Grid.** `kGridMaxTracks = 10000000` (`C/style/grid_area.h:45`). Placement re-runs for **all** items when any
  item's `grid-row/column-*` or `order` changes (`SetGridPlacementDirty`, `L/layout_box.cc:836-880`), except that
  out-of-flow items don't dirty placement (but force a full grid layout). The sizing tree is rebuilt every layout.
  Tracks are compressed into sets; set offsets are a prefix sum (`L/grid/grid_track_collection.cc:1085-1091`);
  intrinsic sizing sorts items by span and takes a **max-reduction** per set
  (`planned_increase = max(item_incurred_increase, planned_increase)`,
  `L/grid/grid_track_sizing_algorithm.cc:912-917`). Per item: min/max (cached) for columns, one measure layout for
  rows, one final layout. Subgrids recurse into the parent's sizing tree.
- **Grid-lanes (masonry)**: `display: grid-lanes`, flag `CSSGridLanesLayout` experimental in 153/155/157/main. Each
  item goes to the **argmin of running lane positions** within `fit-tolerance` (default `normal` = 1em; `0` for an
  exact argmin), ties to the first lane at/after the cursor (`L/grid_lanes/grid_lanes_running_positions.cc:166-207`);
  O(tracks × span) per item, no placement cache.
- **Tables**: column min/max = **max over cells** (`L/table/table_layout_algorithm_types.cc:236-296`), table min/max =
  sum over columns, width distributed with int64 `MulDiv`; row height = max over cells. `kMaxColSpan = 1000`,
  `kMaxRowSpan = 65534`, `kTableMaxInlineSize` = 1,000,000 px.
- **Multicol**: one layout as a single strip for the initial height (`FromFloatCeil(content / (breaks + 1))`, float),
  then a stretch loop: each pass lays out all columns and grows by the **minimal space shortage** (min over columns)
  until it fits (`L/column_layout_algorithm.cc:956-1241`); no pass-count constant.
- **`text-wrap: balance`**: ≤ `kMaxLinesForBalance = 6` lines (`L/inline/score_line_break_context.h:17`), score
  breaker first, else `ParagraphLineBreaker` **binary-searches the available width** between 0.8 × average and full
  width to `ceil(zoom)` px, each probe a full line-break run. **`pretty`**: `ScoreLineBreaker` DP over the last
  ≤ `kMaxLinesForOptimal = 4` lines of a paragraph, only when the last line is short.
- **Intrinsic sizes**: block max-content = max over children, inline max-content = sum along a line, min-content =
  max of unbreakable pieces; `fit-content` = `min(max, max(min, available))` (`L/min_max_sizes.h:45-48`).
- **`field-sizing: content`** (no flag): `ComputedStyle::ApplyControlFixedSize` (`C/style/computed_style.cc:2997-3008`)
  turns off the `size`/`cols`/`rows` defaults, so an `<input>`, `<textarea>` or `<select>` takes its intrinsic size
  from its value (`L/layout_box.cc:1266-1350`). It's the only script-free way for a form control's *typed text* to set
  a box size (an autofilled control stays fixed-size).

### 1.12 `content-visibility`, remembered sizes, `display: none`, containment

- A locked display lock (`content-visibility: hidden`, or `auto` off-screen) blocks child layout
  (`ChildLayoutBlockedByDisplayLock`), stops dirty-bit propagation, and **stops anchor propagation at the locked
  element, its own `anchor-name` included** (`L/fragment_builder.cc:363-367`; §5).
- Remembered sizes: `Element::ProcessContainIntrinsicSizeChanges` observes elements with `contain-intrinsic-size: auto`
  through the document's internal ResizeObserver unless locked (`C/dom/element.cc:6262-6297`), delivered
  `kBeforeOthers` (`C/dom/document.cc:750-762`) at the post-layout RO step; layout reads them only while locked
  (`L/layout_box.cc:1190-1225`). Setting one invalidates nothing. Per-pass delivery inside a depth nest and the pass
  pump are PRIMITIVES findings 1–2; the loop mechanics are chapter 01.
- `display: none`: no LayoutObject, so no fragment, no anchor, no layout; descendants aren't styled
  (ENGINE_NOTES 42) *(code)*.
- `contain: strict` (ENGINE_NOTES 20): layout containment makes the box the containing block for fixed and absolute
  descendants (`IsFixedContainer`), and size containment makes its size content-independent. If nothing inside is
  dirty it's a cache hit, so its fixed descendants (anchored or not) cost nothing that pass. It is **not** a relayout
  boundary while it holds anchors (§1.4) *(code)*.

### 1.13 Per-pass cost model

Unit costs on 153 from the probes above *(measured; noisy machine, ±30%)*:

| Unit | Cost per pass |
|---|---|
| unchanged box under a re-laid-out parent | ~0 (cache hit; 4,000 boxes < 0.1 ms) |
| fixed/absolute box at a containing block that re-runs its OOF pass | 0.45 µs |
| + anchor functions or `position-anchor` | +2.25 µs, +~31 ns × DOM depth |
| anchor, per rebuilt fragment above it | 66–200 ns |
| anchor whose parent box is rebuilt | +0.3 µs, +~3.5 ns × DOM depth |
| restyle of an element under D `display: contents` ancestors | +~3 ns × D |
| flex item re-sorted by `order` (1,000 / 10,000 items) | 2.4 / 3.4 µs |
| span with a `::before` counter on a changed one-line context | ~3 µs |
| size container, clean / dirty | ~0 / its dependents' restyles (ENGINE_NOTES 34) |

---

## 2. What it means for the projects

### 2.1 What one pass costs on js-minus-js's page

The page never lays out a subtree on its own (§1.4): every pass starts at `LayoutView`, which is rebuilt along with
`html` and `body`. What that pass costs beyond shaping and the main recalc *(inference from §1.13 and the page
source)*:

- **Root OOF pass**: every fixed box contained by the viewport. About 210 of them are anchored readers (76 readback
  readers, 128 console `.oc` cells, 4 read ports `.rp`, status readers `.cst*`), each restyled and re-laid out every
  pass (§1.5): ~0.5 ms, more if a reader's own style is heavy. `#state` (fixed, `width: max-content`) re-collects,
  reshapes and re-breaks only on shaping passes.
- **Size-container recalcs inside layout**: the 1,300 restyles of ENGINE_NOTES 34; unchanged from that note. One
  qualification: a reader is restyled every pass because it is *anchored*; its *subtree* restyles only when its size
  changed. PRIMITIVES §2 P2's "128 console readers restyle every pass although the console changes on a few passes in
  a hundred" is the anchored restyle, not the size container.
- **Anchor merge**: every live RAM anchor is copied at body, html and view (memtree puts group boxes directly in
  `<body>`, `.tn` decode levels are `display: contents`), ~0.2–0.6 µs per anchor per pass (16K: 9–10 ms, probe
  above). Written groups add a copy at their group box and the `ToAnchorScopedName` walk for the leaves in it.
- **During compile only**: `#tcr` (`contain: strict`, the containing block of every code overlay) is rebuilt whenever
  a token level changes. Each displayed `.ov` overlay is anchored (`width: calc(… + anchor-size(var(--ln) width,
  0px))`, `compiler/ccpage5.py:316-325`) and sits ~1,600–2,000 levels deep: ~65 µs per overlay per rebuild in the
  synthetic probe, i.e. up to ~30 ms per pass at 511 code words. The `.lp` label anchors add ~7 µs each. And the
  1,962-level chain pays the O(D²) layout-parent walk on every level it restyles (§1.8).

### 2.2 js-minus-js: what to change

1. **Compile chain: stop making every code overlay an anchored element.** Only words that reference a label need
   `anchor-size(var(--ln) width, 0px)`. Declare it in a rule gated on "this slot has a label" (the generator knows
   `q-o_l{s}`), so label-free overlays have no anchor functions: per §1.5 they then hit the layout cache instead of
   being restyled (~65 µs at depth 2,000 → < 1 µs). Measure with L3 (`make l3`; BENCHMARKS §4a's per-word slope,
   7.6 ms per code word, is where it would show).
2. **Compile chain: put a zero-height block every 32–64 levels** of the character and token chains (`.lvA/.lvB`,
   `.tlA/.tlB` are `display: contents`). It caps the `LayoutParentElement` walk at the block (§1.8: 4.5–8.1 →
   1.1–1.8 ms per full restyle at 1,561 levels). Side effects to check: the boxes generated inside a segment become
   children of that segment's block (≈ 25–60 nested blocks, far from the recursion problem ENGINE_NOTES 20 avoids),
   and an anchor below a dirty segment is copied once per rebuilt segment block above it (66–200 ns each) — but
   anchors in clean segments are no longer re-propagated with their 2,000-step walks when `#tcr` relays out, since
   their parent block is a cache hit.
3. **RAM anchors (ENGINE_NOTES 40).** The note's mechanism text ("merges children's anchors into the containing
   block's anchor query") is right in spirit but the unit is per *rebuilt ancestor fragment*, not per containing
   block, and it's an allocation per anchor per level (§1.6). Levers, in order of certainty:
   - fewer live anchors: sparse groups already do this; smaller groups (BENCHMARKS §8: 16 or 64 cells halt ~6%
     sooner) fit the model, since fewer cells come alive per write;
   - two words per anchor: a leaf's remembered *block* size can hold a second word (`contain-intrinsic-size: auto
     W auto H`, read with `anchor-size(--c height)`), halving anchors for the same RAM *(inference)*;
   - one fewer rebuilt level: XHTML allows the RAM groups as children of `<html>` after `<body>`, dropping the body
     copy (~−⅓ of the merge) *(inference)*.
4. **Readers that rarely change** (the console's 128 `.oc` cells): a reader is only free when its containing block
   is a cache hit, and its containing block must contain the anchors it reads (§1.6). Moving the console's RAM group
   and its readers under one `contain: layout` wrapper would make them free on passes that don't print. Gain
   ~0.3–0.5 ms per pass; touches memtree's bank layout. Low priority.
5. **Keeping a size container's dependents tiny** (ENGINE_NOTES 34), from §1.7: the restyle set is "every element
   below whose style evaluated a size query or used `cq*` units, plus inheritance fallout". So: put the `cq*`
   consumer on a leaf; give it `inherits: false` outputs (ENGINE_NOTES 41); don't let rules with `@container` size
   queries match anything else under the reader, even rules that end up false (evaluating marks the element,
   `C/css/container_query_evaluator.cc:185-192`); and keep
   readers shallow (they are: ~13 levels), since every interleaved recalc pays O(depth) (§1.8). A nested size
   container is a firewall: the outer recalc skips its subtree.
6. **Grid ports, from the code** (PRIMITIVES P7: ~15 µs per port, ~3 ms per pass at 4,096 rows). A port's
   `grid-row` change dirties placement for the whole grid (`L/layout_box.cc:870-873`): every item is re-placed, the
   sizing tree is rebuilt, every row's contribution is re-read (cached min/max, measure cache) and every item gets its
   final layout (mostly cache hits): O(items) per pass, ~0.7 µs per row. Cheaper shapes *(inference)*: out-of-flow
   ports (`position: absolute` in the grid, `grid-row` still picks the area) skip re-placement but still force a full
   grid layout (`:875-880`); one grid per bank (or per 256 rows) bounds the relayout to the bank whose port moved;
   explicit `grid-row` on every RAM row avoids the auto-placement cursor. The port reads its row through
   `height: 100%` or stretch, as a size container contributing 0 (size containment).
7. **Upgrade note**: on 153 the root's anchor-aware OOF candidate sort is O(K log K × siblings); 155 fixed it (§3).
   Expect a small run-time gain on 155+ without changes.

### 2.3 css-physics

- **Layout is not a bottleneck** (BENCHMARKS §1: 0.37 ms per frame at 48 bodies) and the code explains why: a register
  write changes `top`/`left` of an absolutely positioned subject, which marks only its containing block for
  simplified layout (§1.2); simplified layout re-runs offsets for the scroller's OOF children (~0.45 µs each, ~316
  register elements at 48 bodies) and copies nothing else. No anchors, no size containers per pass.
- **Anchor-positioned registers** (HISTORY: ~5 ms of layout per frame in 141): each anchored reader restyled and
  relaid out per pass plus one anchor copy per rebuilt level, with float anchor geometry on top (§1.9: worse
  precision than the view-timeline path at 10^6 px). The dead end stands.
- **Register precision**: the write path is float (`Length`) and so is the read path (04 §1.5), so ARCHITECTURE.md's
  "LayoutUnit (1/64 px) over 1e6 px, about 26 bits" overstates by 1–2 bits; growing the scroller doesn't help. If a
  quantity ever needs more, split it into two registers (high and low parts); nesting two positioned boxes doesn't
  help because the read is a float point *(code)*.
- **Contact slots / dynamic partners** (HISTORY open idea): layout can sort (flex `order`) and rank in O(N log N), but
  a rank is only useful with dynamic indexing, which costs ~15 µs per port (PRIMITIVES P7) plus 2.4 µs per readback
  reader here. Still dead at ≤ 96 bodies.
- The hover marker is one anchored element: ~2 µs per pass. Fine.

### 2.4 paint

The probe-row reader is an anchored size container: restyled and relaid out every pass of its containing block,
microseconds. Each cell is an `<object>` document with its own `LayoutView` and fragment tree, so its anchors and
OOF passes stay inside it *(inference)*. Nothing to change.

### 2.5 Layout as a reduction engine: verdict

| Reduction | In layout | Cost and precision | Versus style |
|---|---|---|---|
| sum | inline/flex-row max-content width; any running offset | free inside a box's layout; readback ~2.4 µs (anchored reader) or a size container; LayoutUnit, exact integers < 2^24 through float paths | `calc(a + b + …)`: ~0.1 µs per extra `var()` term (css-physics BENCHMARKS §2). Style wins |
| max | block max-content, grid set sizing, table columns | as above | `max(…)`: same. Style wins |
| prefix sums | `anchor(--k left)` = Σ widths before k | N anchored readers: N × (2.4 µs + 31 ns × depth) per pass (measured: 1,000 `left: anchor(--b<i> left)` readers on a 1,000-item row, +2.4 ms), one pass of latency | a chained property is 2.53 µs. Tie at best, and later |
| sort | flex `order` (stable sort) | 2.4–3.4 µs per item per pass + readers | no style primitive (O(N²) comparisons). Layout wins |
| argmin | scroll snap (04), grid-lanes (flag), `position-try-order: most-*` (≤ 6) | snap O(N) per re-snap; grid-lanes experimental | `min()` gives the value, not the index |
| addressing by value | `grid-row: var(--a)`, anchor names | ~15 µs per grid port, O(items) grid relayout (PRIMITIVES) | O(√N) `if()` tests per port |
| optimal partition | `flex-wrap: balance` + `flex-line-count` | DP + bisection per layout | none |

Rule of thumb *(inference)*: move a computation into layout only if it is an indexing, ordering or optimisation
problem; arithmetic reductions belong in style.

---

## 3. What's changing (153 → 155 → 157 → main)

`diff -ru` of `core/layout` (153 tree vs main, tests excluded): 348 files, ~32k lines, mostly mechanical (`StyleRef()`
→ `Style()`, `ContainingBlock()` returning `LayoutBox`, inline containing-block utils). Branch status from
`$SP/src/versions/{153,155,157}` *(code)*:

| Change | 153 | 155 | 157 | main | Relevance |
|---|---|---|---|---|---|
| OOF candidate tree-order sort with `IndexCache` (`L/fragment_builder.cc:787-830`, `L/layout_object.cc:1138-1174`) | no | yes | yes | yes | js-minus-js root OOF pass (§2.2 item 7) |
| `OofLayoutRequiresSideEffects`: skip OOF layout in measure passes with side effects disabled | — | stable | stable | stable | fewer OOF layouts inside flex/grid measures |
| Anchor map, evaluator, `kMaxTryAttempts`, anchored-restyle logic | same | — | — | same | none of §1.5–1.6 changes |
| `position-visibility: anchor-valid` (`CSSPositionVisibilityAnchorValid`), `anchors-visible` → `anchor-visible` | — | — | stable | stable | |
| Gap decorations (`CSSGapDecoration`) | stable flag | flag removed | | | paint only (`L/gap/`), no size effect |
| Grid-lanes (`CSSGridLanesLayout`), incl. grid-lanes subgrids in main | experimental | experimental | experimental | experimental | argmin primitive, not shippable |
| `flex-wrap: balance`, `flex-line-count` (`FlexWrapBalance`) | stable | stable | stable | stable | chromestatus: shipped 150 |
| `scroll-snap-type: pair` (`CSSScrollSnapTypePair`) | test | experimental | stable | stable | 2D snap argmin (04) |
| `SingleAxisScrollContainers` | experimental | experimental | stable | stable | |
| `LayoutCloneForScrollableOverflowChange` | — | — | stable | stable | |
| `FractionalScrollOffsets` | no status | experimental | experimental | experimental | fractional scroll positions |
| `CssMaxContentSizing`, `CSSLineClamp` | test / experimental | same | same | same | |
| `LayoutResultList` replaces the results vector; `layout_result_list.h` new | | | | yes | memory |

Work in progress visible in main: `FragmentedOofInCb` (no status: off) with many `TODO(crbug.com/40267498)`;
`TODO(kschmi)` to dirty grid placement only when track sizing depends on item sizes (`L/layout_box.cc:870-871`);
`TODO(ikilpatrick)` on caching %-block-size and flex/grid stretch cases (`L/layout_utils.cc:248-251`). Nothing in
sight reduces the anchored-element restyle or the anchor-copy cost.

---

## 4. Ideas, ranked (expected value × confidence)

1. **Gate `anchor-size()` on js-minus-js code overlays to label-referencing words** *(code-backed, measured
   synthetic)*. ~65 µs per overlay per `#tcr` rebuild at depth 2,000 → < 1 µs. Cheapest test: generator patch, then
   `RERUN=1 make l3` and compare the per-word slope.
2. **Zero-height blocks every 32–64 chain levels** *(code-backed, measured synthetic)*: 3–6× cheaper full-chain
   restyles at 1,561 levels, and cache-hit segments for anchors. Test: class every 64th `.lv`/`.tl` level as
   `display: block; height: 0`, L3 + one L5 FizzBuzz; watch ENGINE_NOTES 20's recursion concern (25–60 nested blocks).
3. **Measure the RAM anchor merge on the real page** *(code-backed)*: trace one pass; the model predicts
   ~0.2–0.6 µs per live anchor per pass with groups under `<body>`; ENGINE_NOTES 40's 1.5 µs suggests more rebuilt
   levels or GC. Then try two words per anchor (width + height) and RAM under `<html>`. Test: the 32K-cell A/B from
   ENGINE_NOTES 40 with names on a block vs inline size.
4. **Containing-block islands for readers** *(code-backed, measured: 5.4 → < 0.1 ms for 2,000 readers)*: any
   reader/anchor group whose inputs are stable for many passes (console, status line, compile-done flags) under its
   own `contain: layout` box with the anchors it reads.
5. **Grid ports as out-of-flow items** *(inference)*: an absolutely positioned port with `grid-row: var(--a)` doesn't
   dirty grid placement (`L/layout_box.cc:870-873`), though the grid still lays out fully; and per-bank grids keep
   the O(rows) relayout to one bank. Test: PRIMITIVES' `mkidx.py grid` with `position: absolute` ports.
6. **`flex-wrap: balance` as a solver** *(speculation)*: `flex-line-count: N` bisects a line width so that greedy
   packing makes ≥ N lines and then minimises Σ slack²: a min-max partition of a sequence in one layout, readable
   through item positions. No current consumer in the projects; note it next to MathML `ceil()` (ENGINE_RESEARCH
   Q10) as an exotic layout operator.
7. **Sweep-and-prune by `order`** *(speculation)*: 64 bodies sorted per axis cost ~0.3 ms of layout; useless until
   pair rules can be indexed dynamically. Keep closed with the contact-slot idea.
8. **Prefix sums via `anchor()`** *(code-backed, measured)*: works, costs ≈ a style chain, a pass later. Don't.

## 5. Possible bugs

1. **Grid: wrapped extra-space shares** *(code, measured in 153; same code in main)*.
   `DistributeExtraSpaceToSets` (`L/grid/grid_track_sizing_algorithm.cc:686-687`):
   ```cpp
   extra_space_share = LayoutUnit::FromRawValue(
       (extra_space.RawValue() * set_share_ratio) / share_ratio_sum);
   ```
   `RawValue()` is `int32_t` and `set_share_ratio` is `wtf_size_t` (`uint32_t`) for equal distribution, so the
   product is computed modulo 2^32. Repro: `grid-template-columns: repeat(2000, auto)`, an item spanning all 2,000
   columns with `width: 70000px`, an empty item in column 1001 (splitting the tracks into sets of 1,000 and 999): the
   empty item's `offsetLeft` is 1,446 px; expected 35,017.5 (1,000/1,999 of 70,000). Correct up to 60,000 px
   (64 × 60,000 × 1,000 < 2^32), wrong from 70,000. Spec: css-grid-2 §12.5.1 "Distribute space up to limits: … by
   distributing the space equally among these tracks". Fix: widen to int64 as the `MulDiv` paths do. Not checked
   against the tracker; repro script `exp/05/exp/gridovf.js`.
2. **`content-visibility: hidden` element with its own `anchor-name` isn't an anchor** *(code, measured)*.
   `L/fragment_builder.cc:363-367` returns for a locked child before its own names are registered. Repro: `<div
   style="anchor-name: --x; width: 50px; content-visibility: hidden">` and an abspos `width: anchor-size(--x width,
   7px)` reads 7; the same with `content-visibility: auto` on-screen reads 60. Spec (css-anchor-position-1 §2.1,
   note): "While an element is in the skipped contents of another element (due to content-visibility: hidden, for
   instance), it's not an acceptable anchor element"; the hidden element is not in *another* element's skipped
   contents, and the normative list only adds "If possible anchor is in the skipped contents of another element, then
   positioned el is in the skipped contents of that same element". No WPT covers it
   (local `css-anchor-position` has only `anchored-c-v-hidden.html`, the anchored side). js-minus-js avoids it by
   naming a wrapper (`machine/memtree.py:74-75`).
3. Not bugs, worth knowing: anchored OOF elements are restyled and relaid out on every containing-block OOF pass
   (§1.5); `anchor()`/`anchor-size()` geometry is float-quantised (1/16 px at 10^6 px, §1.9).

## 6. Open questions

- How much of js-minus-js's compile time is the overlay restyle (§2.1)? An ablation that drops `anchor-size` from
  overlays would answer it in one L3 run; the synthetic says up to ~30 ms per pass at 511 words.
- Why does ENGINE_NOTES 40 measure ~1.5 µs per anchor per pass when a memtree-shaped synthetic gives 0.55–0.63 µs?
  Candidates: more rebuilt levels in the real page, GC of the per-pass reference garbage, or the older dense layout.
  A trace with `blink.debug` layout events on the real page would count rebuilt fragments.
- Does Oilpan GC from anchor-reference churn show up as main-thread time between frames? Not separated here.
- `flex-wrap: balance` uses `uint64` prefix sums of raw LayoutUnits: are its results exact for integer item sizes
  (useful if it's ever used as a solver)? Untested.
