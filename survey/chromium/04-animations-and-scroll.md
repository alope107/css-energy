# 04. Animations, timelines, triggers, scroll machinery and SMIL

Scope: CSS animations and transitions, how interpolations enter the cascade, scroll and view timelines (the
projects' registers and latches), animation triggers, the scroll machinery (offsets, snap, anchoring,
`scroll-state()`, scroll buttons and markers, smooth scroll), SMIL, view transitions. Neighbours: the frame loop and
pass count are [01-lifecycle.md](01-lifecycle.md); the cascade, `var()` serialization and the MPC are
[02-style-engine.md](02-style-engine.md); layout is [05-layout.md](05-layout.md); declarative HTML input (invokers,
popovers, forms) is [08-interactivity-and-loading.md](08-interactivity-and-loading.md).

Source: Chromium main `22b3b159` (M158) unless marked 153 (branch 8010). Paths are from the src root; `core/` means
`third_party/blink/renderer/core/`. Experiments ran in headless Chromium 153.0.8010.12 on a shared machine (load
average 4–6), so timings are rough; files are under `exp/04/` (relative to `survey/chromium/`). Labels:
*(code)*, *(measured)* (run for this chapter), *(docs)*, *(inference)*.

## Key findings

1. **The per-registered-property animation cost (js-minus-js ENGINE_NOTES 4, css-physics BENCHMARKS §4) is one loop.**
   Every new or rebuilt keyframe model snapshots "compositor keyframes" and iterates
   `ComputedStyle::GetVariableNames()`, which includes **every registered property that has an `initial-value`**
   (`core/animation/keyframe_effect_model.cc:342`, `core/style/computed_style.cc:2281`). Measured: 0.06–0.067 µs per
   such property per transition restart or animation rebuild (200 restarts per frame: 3.5 → 56.9 ms at 4,000 unused
   registered properties), and zero cost for registrations without an initial value or for animations that are not
   rebuilt. *(code + measured)*
2. **The transition latch is per pass, not per frame** (correcting PRIMITIVES §P4). A latch keyed on an inherited
   flag wrote in pass 1 and held in pass 2 of the same frame, every frame. The before-change style is the style at the
   start of the current style+layout pass (`PostStyleUpdateScope` per `UpdateStyleAndLayout`). *(code + measured)*
3. **Named-timeline lookup is an ancestor walk, repeated for every animation on every non-animation restyle.** This
   is ENGINE_NOTES 13: chains with an animation per level cost O(depth²). Measured: 8 animations per level, extra cost
   1.5 / 5.2 / 21 ms at 100 / 200 / 400 levels, ≈ 33 ns per ancestor visited. *(code + measured)*
4. **View-timeline registers hold 1/16 px, not 1/64 px.** The current time is `int64` microseconds at 16 µs per pixel,
   truncated (`core/animation/scroll_timeline.cc:173`), and the subject position goes through `gfx::PointF`
   (`core/animation/view_timeline.cc:574`). Over a 10⁶ px scroller that is ≈ 24 bits, not 26, and a bigger scroller
   adds nothing. `var()` then cuts it to 6 significant digits. *(code + measured)*
5. **Animation taint does not survive a registered property.** `var(--animated)` in an `animation-*`/`transition-*`
   property is invalid (it became `0s`), but a registered property computed from it is untainted
   (`core/css/properties/longhands/custom_property.cc:194`). The spec says taint is "infectious". This is what lets the
   latches work, and also a spec deviation that could be fixed. *(code + measured)*
6. **The 24-name `timeline-scope` nests no longer matter**: in 153 a scope lookup is a linear `Vector::Contains`, and
   one 840-name list measured the same as the nest. The 3× came from Chrome 141, which rebuilt a scope's map on every
   restyle of the scope element. *(code + measured)*
7. **`::scroll-button` is a JS-free step register**: each click or Enter/Space adds `int(0.875 × snapport)`. A 1 px
   snapport (`scroll-padding`) makes it +1 per activation; narrow snap areas make it "next snap position". It is
   stable in 153 and readable by a scroll timeline at the next frame. *(code + measured)*
8. **Scroll anchoring is a mirror, and a ratchet with suppression**: alone, the offset follows the *net* height change
   above the anchor; growing unsuppressed and shrinking suppressed gave +100 px per cycle. It runs once per lifecycle
   pass with integer deltas. *(code + measured)*
9. **SMIL is a JS-free event machine.** `begin` takes any DOM event of any element by id (`click`, `change`, `toggle`,
   `animationend`, `transitionend`, `scrollend`…). `<set>` can write `class` (read with `:has()`) or the `width` of a
   `<foreignObject>`/`<svg>` (read by `cqw`/`anchor-size()`). It lands at the next frame and costs nothing while idle.
   *(code + measured)*
10. **Custom-property animations never run on the compositor** without a CSS Paint worklet, which needs JS
    (`core/animation/compositor_animations.cc:433`). An element that animates a custom property also loses the
    base-style cache and applies its whole cascade twice per restyle. *(code)*
11. **Animation triggers are frame-granular edge detectors, not per-pass latches, and by default they don't fire in
    non-composited scrollers**, which is how both projects build registers (`overflow: hidden`). With the compositor
    path (stable) a trigger stage costs 3 frames. `--en pause play` on a register animation is a working
    sample-and-hold. `play-pause`/`play-alternate` crash the renderer. There is no CSS event trigger. *(code + measured)*

---

## 1. How it works

### 1.1 Where animation work sits in a frame

[01-lifecycle.md](01-lifecycle.md) has the loop; the animation-relevant order on main is *(code)*:

```
BeginMainFrame
 ├ ServiceScrollAnimations (core/frame/local_frame_view.cc:4041-4071)
 │   smooth-scroll animators tick (main-thread ones)
 │   UpdatePostLayoutSnapshotClientsForServiceAnimations: every scroll/view/deferred timeline re-snapshots
 │   SMIL: ServiceSmilOnAnimationFrame (:4067)
 │   DocumentAnimations::UpdateAnimationTimingForAnimationFrame (:4070): every timeline's animations_needing_update_
 ├ rAF callbacks
 └ UpdateLifecyclePhases loop
     style recalc → ApplyAnimatedStyle per animated element → layout
     → scroll anchoring, pending snaps, scroll-marker selection (local_frame_view.cc:2944-2955)
     → RunSnapshotPostLayoutStateSteps, ONCE per frame: timelines, triggers, scroll-state, scroll buttons;
       any change → repeat style+layout
     → … prepaint, paint → DocumentAnimations::UpdateAnimations → PendingAnimations::Update
       (start times of new animations and transitions, pending pause/play commits)
```

Two consequences recur below:
- Anything resolved in `PendingAnimations::Update` (`core/animation/pending_animations.cc:69`) is frame-granular. That
  covers pause commits, a new transition's start time and a scroll-driven animation's ready time.
- Anything that re-runs with style is per pass. That covers which value a transition starts from and every
  `if()`/`@container` gate.

### 1.2 From `@keyframes` to the cascade

`StyleResolver::ResolveStyle` computes the base style, then `ApplyAnimatedStyle`
(`core/css/resolver/style_resolver.cc:2760-2868`):

1. `CalculateTimelineUpdate` if the element declares `scroll-timeline`/`view-timeline`/`timeline-scope` (:2776).
   For each timeline it declares, this re-runs the attachment search described in §1.5.
2. `StyleBaseData` snapshot of the base style (:2794).
3. `CSSAnimations::CalculateAnimationUpdate` (:2800; `core/animation/css/css_animations.cc:1891-2149`):
   - **Fast path.** If this restyle was caused only by the element's own animations ticking
     (`IsAnimationStyleChange()`), it only re-collects the active interpolations (:1910).
   - **Otherwise, for each name in `animation-name`:**
     1. `FindKeyframesRule` by name.
     2. `ComputeTimeline`: a name lookup for `animation-timeline: --x` (:2062).
     3. Compare timing, play state, timeline, range and triggers with the running animation (:2079).
     4. Any difference → `UpdateAnimation` with a **new keyframe model** (:2091).
   - `IsAnimationStyleChange()` is cleared whenever the parent forces a recalc of children, e.g. because an
     inherited value changed (`core/dom/element.cc:5854`). An animated element inside a chain whose inherited state
     changes every pass therefore takes the full path every pass.
4. `CalculateTransitionUpdate` (:2803; css_animations.cc:3105-3213), §1.3.
5. If anything is active, `cascade.AddInterpolations` and **`cascade.Apply(filter)` again** (:2820-2836).
   `StyleCascade::Apply` clears the applied flags (`core/css/resolver/style_cascade.cc:299`) and re-applies every
   declaration plus the interpolations. A non-cached animated element therefore runs its cascade twice per restyle.
   The filter `Add(kNotAnimation)` (:2834) skips the `animation-*` and `transition-*` longhands in that second run.
6. `CalculateCompositorAnimationUpdate`, `SnapshotCompositorKeyframes` (:2858-2863), §1.4.

Base-style reuse (`CanReuseBaseComputedStyle`, :3106-3190) is the cache that makes animation-only restyles cheap. It
is **off for any element animating a custom property** (:3122): "animating a custom property can have side effects on
other properties via variable references". Each tick of such an element is a full rule match plus two cascade
applications *(code)*.

**Interpolation of registered custom properties** (`core/animation/interpolation_types_map.cc:510-602`): each
registration precomputes its type list. `<number>` gets `[CSSVarCycle, CSSNumber, CSSDefault]`; `<integer>` is
`CSSNumberInterpolationType(…, round_to_integer=true)` (:542); `*`, `<custom-ident>` and `<string>` flip at 50%.
Values are `double` throughout: `InterpolableNumber`, keyframe fraction, `CSSNumericLiteralValue`. Conversions are
cached per interpolation and revalidated by checkers (`core/animation/invalidatable_interpolation.cc:160-228`).

The interpolated value is applied with `ValueMode::kAnimated`. The registered property then stores a `CSSValue`
(double) and, for `var()`, `CSSVariableData::Create(value.CssText())` (`core/css/resolver/style_builder_converter.cc:3712-3719`,
"TODO(andruud): Produce tokens directly from CSSValue"). `CssText` is still `%.6g` on main
(`core/css/css_numeric_literal_value.cc:192-198`), which is ENGINE_NOTES 2's six digits. Paths that read the `double`
instead of the text: additive/accumulative animations (the underlying value), transitions, `@container style()`
range comparisons and explicit `inherit`. `var()` never does.

**Composite order** (`core/animation/effect_stack.cc:158-195`): per element, sampled effects are `std::sort`ed by
`Animation::HasLowerCompositeOrdering` on every resolve. For CSS animations that is tree order of the owning element,
then position in `animation-name`. A `replace` interpolation clears the per-property stack; `add`/`accumulate` push
onto it. Transitions are a separate origin above animations (`CascadeOrigin::kTransition`). css-physics' `#TI` sums
handle drags with `animation-composition: add`, which works this way.

**Animation taint** (`core/css/resolver/cascade_resolver.cc:20-29`): `var()` of tainted data inside an
animation-affecting property (`animation-*`, `transition-*`) is invalid at computed-value time. Data is tainted when
it is the animated value itself (`custom_property.cc:194-195`) or an *unregistered* custom property whose tokens
reference tainted data (the `TokenSequence` ORs the bit, `style_cascade.cc:1166`).
- A **registered** property computed from a declaration is stored untainted whatever it referenced
  (`custom_property.cc:194`). Spec, css-variables-2: "Animation-tainted is 'infectious': custom properties which
  reference animation-tainted properties also become animation-tainted."
- `if(style(--tainted…))` doesn't propagate taint (only attr-taint, `style_cascade.cc:2887-2952`), and neither does
  an `@container style()` gate. The selected branch is a literal.
- *(measured, `latch/latch.html`)*:
  - `animation-delay: calc(var(--t) * -1ms)` with `--t` inherited from an animated parent computed to `0s`;
  - `transition: --N 0s calc((1 - var(--w)) * 1000000s)` worked with `--w` a registered `<integer>` derived from an
    animated value.

### 1.3 Transitions and the latch

`CalculateTransitionUpdateForPropertyHandle` (css_animations.cc:2691-2955):
- **Before-change style** = the old style's *base* (animations excluded, TODO crbug.com/1082401) plus every running
  transition sampled at its current time (:3215-3305), resolved by a second `StyleResolver::BeforeChangeStyleForTransitionUpdate`
  cascade.
- **After-change style** = this resolve's base style. If an ancestor is animating, `EnsureAfterChangeStyle` re-resolves
  the ancestor chain (:3336-3458).
- Equal values → nothing. `delay + duration ≤ 0` → `UnstartTransition`: the property shows the new value at once
  (:2879). Otherwise a new `TransitionKeyframeEffectModel` and a `CSSTransition` that `play()`s on the document
  timeline (:2626).
- The new transition has no start time until `PendingAnimations::Update`. Until then its current time is 0 and its
  backwards fill shows the start keyframe, so a 10⁶ s delay holds the before-change value.

**Which style is "old".** `PostStyleUpdateScope` is created per `UpdateStyleAndLayout` (`core/frame/local_frame_view.cc:3697`),
and `StoreOldStyleIfNeeded` keeps the element's style from the start of *that* scope (`core/css/post_style_update_scope.cc:119-143`).
So pass 2 of a frame compares against pass 1's result, not against the previous frame.

*(measured, `latch/latch.html` + `run.js`)*: a view-timeline counter `k` advanced by 1 per pass (2 per frame).
- A child latch `--L: var(--k); transition: --L 0s; transition-delay: if(style(--w: 1): 0s; else: 1000000s)`, with
  `--w = k mod 2` inherited from the parent, read `L = k − 1` at every frame end: written in pass 1 (odd), held in
  pass 2.
- An `@container style(--w: 1)` gate, and the `calc((1 − var(--w)) × 10⁶ s)` form, behaved identically.
- **The latch is per pass.** What PRIMITIVES §P4 observed as frame granularity comes from the editor scan's own
  per-frame column counter (`--rbfresh`, `readback/ui_rb.py:61-82`), not from transitions.

Two conditions do make transitions skip a pass:
- **A restyle caused only by the element's own animations** (`animation_style_recalc`, :3127, :3157) evaluates no
  transitions. A latch whose input is its *own* animated property only latches when something else restyles it.
  Feed latches through inheritance, as `latch.html` does.
- **The control flag is read from the base style.** ENGINE_NOTES 9 applies to `transition-delay` just as to
  `animation-play-state`. The flag must come from an ancestor, or from a registered property one hop away.

**Per-frame cost of held latches** *(code)*:
- A transition in its 10⁶ s delay is "not inactive", so `Animation::Update` returns true
  (`core/animation/animation.cc:3372`) and it stays in the document timeline's `animations_needing_update_`.
- Every frame in which the document timeline is serviced, every held latch is `Update()`d, the list is `std::sort`ed
  (`core/animation/animation_timeline.cc:139`), and `getReplaceableAnimations` walks all animations
  (`core/animation/document_animations.cc:200`).
- Cost is O(latches) per frame even when nothing changes. Part of the ~5,600 `serviceAnimations` per frame that
  PRIMITIVES recommendation 6 saw is probably this *(inference)*.

### 1.4 The O(registered properties) loop

`CSSAnimations::SnapshotCompositorKeyframes` (css_animations.cc:2180-2210) runs on every animated resolve. It snapshots
every animation on the element, every new animation, every updated animation and every new transition, but only
models with `needs_compositor_keyframes_snapshot_` set: new models (`keyframe_effect_model.h:419`) or any
`ClearCachedData()` (`keyframe_effect_model.cc:680`). For those, `KeyframeEffectModelBase::SnapshotCompositableProperties`
(`core/animation/keyframe_effect_model.cc:320-356`) does:

```cpp
for (const AtomicString& name : computed_style.GetVariableNames()) {   // :342
  if (property_registry->WasReferenced(name)) continue;
  updated |= SnapshotCompositorKeyFrames(PropertyHandle(name), …);       // keyframe_groups_->find(name)
}
```

`ComputedStyle::GetVariableNames()` (`core/style/computed_style.cc:2272-2288`) builds a fresh `HashSet` of:
- the inherited and non-inherited variables,
- **plus `StyleInitialData::CollectVariableNames`**, i.e. every registration with an initial value
  (`core/style/style_initial_data.cc:12-30`).

It is cached per `ComputedStyle` object, and each resolve makes a new one. So each new model costs O(R) hash
insertions plus, per registered property, a `WasReferenced` lookup and, unless some `var()` references the name, a
`keyframe_groups_` lookup. All of that serves only custom properties, which can be
composited only with a CSS Paint worklet (`compositor_animations.cc:424-436`).

What creates a new model:

| Event | Path |
|---|---|
| any transition (re)start: every latch write→hold, every retarget | `update.NewTransitions()` (:2207) |
| any change in `animation-duration/-delay/-timing-function/-iteration-count/-direction/-fill-mode/-play-state/-timeline/-range/-composition` or the triggers, or a `@keyframes` rule version change | `UpdateAnimation` (:2079-2091) |
| element (re)shown, `animation-name` list changed | `StartAnimation` |

*(measured, `regcost/`, 200 children, R unused `@property <number>` with `initial-value`, median style time per
frame)*:

| Variant | R = 0 | R = 4,000 | R = 4,000, `syntax: '*'` (no initial value) |
|---|---|---|---|
| children only inherit an animated value | 0.38 ms | 0.40 ms | — |
| each child runs its own animation (created once) | 2.69 | 2.60 | — |
| each child's transition restarts every frame | 2.2–3.5 | 51.4–56.9 | 4.46 |
| each child's animation is rebuilt every frame (`animation-duration: if(…)`) | 2.93 | 51.3 | 2.67 |

That is (51 − 3) ms / 200 / 4,000 ≈ **0.06 µs per registered property per rebuild**. css-physics BENCHMARKS §4 derived
0.05 µs from a different page. The steady state doesn't depend on R.

With 16 animations per element, all rebuilt (`m_R*_K16.html`, 100 elements), style time went from 2.97 to 138.7 ms.
That is ≈ 85 µs per animation, 0.021 µs per registered property per animation. The `HashSet` is shared by the
element's animations (one `ComputedStyle`), but the two lookups per name aren't.

### 1.5 Scroll and view timelines

**Objects** *(code)*:
- `ScrollTimeline` and `ViewTimeline` (subclass) are `ScrollSnapshotTimeline`s, as is `DeferredTimeline`, which is
  what a `timeline-scope` name resolves to.
- Every `ScrollSnapshotTimeline` is a `PostLayoutSnapshotClient` registered with the frame at construction
  (`core/frame/post_layout_snapshot_client.cc:12-16`).
- A timeline's state is a snapshot `TimelineState` (`scroll_snapshot_timeline.h:143-190`): direction, `current_time`
  (`std::optional<base::TimeDelta>`), scroll limits, `scroll_offsets` (start/end, double), `view_offsets`, zoom,
  duration, source.

**Computing a view timeline** (`ScrollTimeline::ComputeTimelineState`, `scroll_timeline.cc:74-176`, and
`ViewTimeline::CalculateOffsets`, `view_timeline.cc:348-420`):

```
subject_pos  = LocalToAncestorPoint(subject → scroller)    gfx::PointF (float)       view_timeline.cc:574
start, end   = subject_pos − viewport + end_inset,  subject_pos + subject_size − start_inset  (double)
current      = |scroll offset| (gfx::Vector2dF float; integer px in 153, FractionalScrollOffsets off)
current_time = base::Microseconds((current − start) × 16)   → int64 µs, truncated           scroll_timeline.cc:173
duration     = (end − start) × 16 µs                         (AnimationTimeDelta, double)
progress     = current_time / duration   → keyframe fraction (double) → CSSNumericLiteralValue (double)
var()        → CssText "%.6g"
```

The constant is `cc::ScrollTimeline::kScrollTimelineMicrosecondsPerPixel = 16` (`cc/animation/scroll_timeline.h:85`).
The comment derives it from a 4 × (1/64 px) worst-case error. So **one µs of timeline time = 1/16 px**.

*(measured, `prec/`)*: a 100 px view timeline mapped to `--x = current_time` in µs, subject at 50 + k/64 px, read
800, 799, 799, 799, 799, 798… (truncation at 1/16 px). Near 600,000 px the float subject position adds its own
1/16 px rounding.
- At the repo's 10⁶ px a register has 1.6·10⁷ steps ≈ 24 bits (ARCHITECTURE.md says LayoutUnit/26 bits).
- A larger scroller gains nothing: above 2²⁰ px the float ULP grows past 1/16 px. LayoutUnit itself saturates at
  33,554,431 px.
- Scroll-timeline registers (the scroll offset itself) are integer px in 153.
- The binding limit is downstream: `var()` keeps 6 significant digits (≈ 20 bits).

**When timelines update and what they invalidate** *(code)*:
- `UpdateSnapshotInternal` (`scroll_snapshot_timeline.cc:221-291`) recomputes the state. It runs:
  - at frame start (`UpdateSnapshotForServiceAnimations`);
  - once post-layout per frame (`RunSnapshotPostLayoutStateSteps`);
  - and `ShouldScheduleNextService` (:164-177) computes the state once more, without storing it, for timelines with
    animations needing updates.
- In the post-layout step, any state difference makes `UpdateSnapshot` return true, which repeats style and layout,
  even for a timeline with no animations. If the geometry changed (`HasConsistentLayout`, :177-181), every attached animation gets
  `OnValidateSnapshot(true)` → `InvalidateEffectTargetStyle()` → `SetNeedsAnimationStyleRecalc()` on the **target
  element only** (`animation.cc:3083-3090`; `core/dom/element.cc:7575-7594`).
- A sampled fraction change marks only the target (`keyframe_effect.cc:741`, `keyframe_effect_model.cc:230`). The
  subtree is restyled only through the style diff: inherited properties change → children recalc; non-inherited →
  only children with explicit `inherit`.
- Keyframe easing (`steps()`) doesn't save invalidations: `changed` compares the raw fraction.
- **An inactive timeline costs nothing** beyond its `ComputeTimelineState` per snapshot. There is no current time,
  the effect is inactive, nothing is invalidated (ENGINE_NOTES 12).
- **`DeferredTimeline` doubles the geometry work.** Its `ComputeTimelineState` forwards to the attached timeline
  (`core/animation/deferred_timeline.cc:85-90`), and both are snapshot clients. Each hoisted register computes its
  subject geometry twice per snapshot, at 2–3 snapshots per frame.

**Name lookup** *(code)*:
- `animation-timeline: --x` → `FindAncestorTimeline` (css_animations.cc:1503-1526) walks the *flat-tree ancestors*
  one by one. At each ancestor it checks:
  - the element's scroll-timeline map;
  - its view-timeline map;
  - its `timeline-scope` filter: `filter_.Names().Contains(name)`, a **linear scan** of the names
    (`core/animation/css/css_timeline_map.cc:20`; `core/style/style_timeline_scope.h:29`).
- A view timeline finds its `timeline-scope` the same way, walking up from the subject (`FindAncestorDeferredTimeline`,
  :1531-1557), for each timeline it declares, on every resolve of the subject (`CalculateTimelineAttachmentUpdate`,
  :1338-1370).
- The animation lookup runs on every *non-animation* restyle of the animated element, for every animation (:2062).
- *(measured, `chain/`)*: chains with 8 named-timeline animations per level cost, above a document-timeline control,
  1.46 / 5.2 / 21 ms at depth 100 / 200 / 400: quadratic, ≈ 33 ns per ancestor visit.
- In M141 the scope map was a per-element hash map rebuilt whenever the scope element restyled
  (`CalculateChangedDeferredTimelines`, M141 `css_animations.cc:1164-1186`; lookups were O(1)). The 2026 rewrite
  (`CSSDeferredTimelineMap`, a filter plus a lazily filled map, already in 153) makes a restyle of the scope element an
  O(K) vector compare, and a lookup through it O(K).

**Compositor**: scroll-driven animations of transform/opacity/filter can run on the compositor. Custom-property
animations need a paint worklet (`compositor_animations.cc:424-436`), so **every register and every derived property
is main-thread, every pass** *(code)*. On main, `TrackAnimatedSources` (test, `core/animation/inherited_animations/`)
prepares compositor support for animations whose values are inherited, which is exactly this case, but it is far from
shipping.

### 1.6 Play state, paused animations, detached timelines (ENGINE_NOTES 9–11)

- **9, play state from the base style** *(code)*:
  - `is_paused` is read from `style_builder.Animations()->PlayStateList()` (css_animations.cc:1968) inside
    `CalculateAnimationUpdate`, which runs before the interpolations are applied (style_resolver.cc:2800 vs 2836).
  - The second cascade pass skips `animation-*` longhands (`kNotAnimation` filter, :2834).
  - So `animation-play-state: if(style(--own))` sees the element's *base* `--own`. An ancestor's animated value,
    inherited, is visible.
  - The same holds for every `animation-*` and `transition-*` longhand.
- **10, created paused** *(code)*:
  - `PauseInternal` on a scroll-driven animation with no current time sets no hold time and sets
    `auto_align_start_time_` (`animation.cc:1687-1714`).
  - The next `OnValidateSnapshot` sets a start time from the range start.
  - `CommitPendingPause` at `PendingAnimations::Update`, end of frame, sets `hold_time = ready_time − start_time`
    (:1190), where `ready_time` is the timeline time at that moment (`pending_animations.cc:132`).
  - A paused-at-creation animation therefore shows whatever the timeline snapshot was at the end of its first frame,
    and is deferred altogether while the timeline is inactive (:118-121). If the register settled later than that,
    the value is stale. Hence "doesn't reliably take its timeline's value".
- **11, keeps its value after detach** *(code)*:
  - A paused animation's `CurrentTimeInternal()` is its `hold_time_`, independent of the timeline.
  - `setTimeline(nullptr)` from a scroll timeline converts progress into a held current time (`animation.cc:1301-1306`).
  - A timeline that merely becomes inactive leaves `hold_time_` alone.
- **Pausing is a frame-granular latch at best.** *(measured, `latch.html` `#F`)*: `animation-play-state` toggled
  every pass never held. The pause stays pending until frame end while the animation keeps tracking, and each toggle
  rebuilds the keyframe model (§1.4).

### 1.7 Animation triggers

Status: `AnimationTrigger`, `TimelineTrigger` and `CompositorTimelineTrigger` are stable in 153, 155 and main (shipped
146, chromestatus 5181996801982464; `trigger-scope` 5152759609425920). `EventTrigger` is experimental everywhere and
**JS-only**. The `css_properties.json5` trigger blocks are identical in 153, 155 and main *(code)*.

**Grammar** (`core/css/css_properties.json5:1169-1366`):
- `animation-trigger: none | [<dashed-ident> <enter-action> <exit-action>?]#`, one entry per animation.
- `timeline-trigger: <name> <source> <activation-start> <activation-end> / <active-start> <active-end>`, with longhands
  `timeline-trigger-name`, `-source` (`auto | <dashed-ident> | scroll() | view()`), `-activation-range-*`,
  `-active-range-*`.
- `trigger-scope: none | all | <dashed-ident>#`.
- Actions: `play play-once play-forwards play-backwards pause reset replay none`. The parser also accepts
  `play-alternate` and `play-pause` (`core/css/properties/css_parsing_utils.cc:4752-4760`), which crash (§5).
- The spec has moved to animation-triggers-1 (ED 2026-10-16) *(docs)*. Its CSS event trigger (`event-trigger: --n click()`,
  `keypress()`, `focusin()`…) is implemented nowhere in Chromium.

**How it works** *(code)*:
- `TimelineTriggerRange::ComputeState` (`core/animation/timeline_trigger_range.cc:367-434`) is a **Schmitt trigger**:
  inside the activation range → `kPrimary`; outside the active range → `kInverse`; in between → unchanged; idle can't
  go straight to inverse.
- `TimelineTrigger::Update` runs the enter/exit action only on a state change (`timeline_trigger.cc:63-95`).
- Actions call `PlayInternal(AutoRewind::kDisabled)`, `ReverseInternal`, `PauseInternal`, `ResetPlayback`, or
  `PlayInternal(kForced)` for `replay` (`animation_trigger.cc:28-150`).
- Actions are skipped (the edge is lost) while the CSS `animation-play-state` is `paused` (:197-209).
- Triggers are evaluated inside `UpdateSnapshotInternal` (`scroll_snapshot_timeline.cc:252-280`): at most at frame start
  and once post-layout per frame.
- **But with `CompositorTimelineTrigger` (default) the main-thread evaluation stops once the cc trigger exists**
  (`timeline_trigger.cc:63-69`). From then on state arrives from the impl thread's `TickAnimations`
  (`NotifyActivated`, :231-253). The impl thread skips timelines whose scroller isn't composited
  (`cc/animation/scroll_timeline.cc:71-75`).

*(measured, `trig/`)*:
- Hysteresis works (`scroll() 40% 60% / 20% 80%`: on, still on at 30%, off at 10%, still off at 30%, on at 40%).
- `replay` restarts; `play` on a finished animation does nothing; `play pause` accumulates active time.
- **Latency**: with default flags, a chain of trigger stages took **3 frames per stage**; with
  `--disable-blink-features=CompositorTimelineTrigger`, 1 frame per stage, the action applied in the same frame's
  second pass.
- **In a non-composited scroller (`overflow: hidden`, `visibility: hidden`), which is the projects' register setup,
  the default trigger never fired** (§5).
- **Sample-and-hold**: `animation-trigger: --en pause play` on a view-timeline register animation held 545 while the
  free-running copy reached 1,000, and resumed tracking on re-entry. Until the first entry the triggered animation
  sits paused at the from-keyframe.

A trigger is an edge detector, a frame-granular latch and a sample-and-hold on a register's own animation. It is not
a per-pass flip-flop, and there's no JS-free event trigger.

### 1.8 The scroll machinery

**Offsets** *(code)*:
- `ScrollOffset` is `gfx::Vector2dF` (`core/scroll/scroll_types.h:42`); `PaintLayerScrollableArea::scroll_offset_` stores it
  (`core/paint/paint_layer_scrollable_area.h:888`).
- Min and max are integers: the scroll origin is a floored int point and the contents size is pixel-snapped
  (`paint_layer_scrollable_area.cc:664-734, 958-968`).
- Every write passes `ShouldUseIntegerScrollOffset() ? ToRoundedVector2d(offset) : offset`
  (`core/scroll/scrollable_area.cc:626-634`), with `ShouldUseIntegerScrollOffset() = !FractionalScrollOffsetsEnabled()`.
- `FractionalScrollOffsets`: no status in 153 (its content feature is disabled by default); experimental in 155 and
  main.
- *(measured, `scroll/big.html`)*:
  - writes round (1000000.4 → 1000000; from 0, `scrollBy(0, 0.4)` stays at 0 and a further `scrollBy(0, 0.6)` gives
    1: fractions aren't accumulated);
  - above 2²⁴ only even offsets are reachable;
  - `scrollHeight` saturates at 33,554,428.
- *(measured, `scroll/frac.html`)*: with `--enable-features=FractionalScrollOffsets` a scroll-timeline-driven value
  lands on a 1/16 px grid (500.4 → 500.375). That is the µs truncation of §1.5.

**Snap** *(code)*:
- After each layout, `RunStyleAndLayoutLifecyclePhases` runs, in order (`local_frame_view.cc:2944-2955`):
  1. `PerformScrollAnchoringAdjustments`
  2. `ExecutePendingSnapUpdates`
  3. `ExecutePendingScrollMarkerSelectionUpdates`
  4. `ProcessDeferredScrollEvents`
- All of it is skipped for script-forced layouts (`target_state == kLayoutClean`, :2943), and it runs again on every
  lifecycle repeat. Snap and anchoring therefore act **after every pass**, whereas timelines re-snapshot once
  post-layout per frame.
- `ExecutePendingSnapUpdates` (:5819-5850):
  - rebuilds the whole `SnapContainerData` of each enqueued scroller with one `LocalRectToAncestorQuad` per area
    (`core/page/scrolling/snap_coordinator.cc:81-221`);
  - skips scrollers with a running smooth scroll;
  - skips `SnapAfterLayout` while `ShouldDeferLayoutSnap()`, which is `widget->IsScrollGestureActive()` (:2912-2921).
    That is a **page-global** test: a gesture on any scroller defers every layout re-snap (`touch-snap-defer`).
- Re-snap uses `EndPositionStrategy` with `kRequire` and **sticks to the previously snapped element** if it still
  exists, even when another area is closer (`cc/input/scroll_snap_data.cc:649-679`). It is instant when the target is
  unchanged, else the author's `scroll-behavior` (`scrollable_area.cc:1297-1333`).
- Selection is a linear scan of `snap_area_list_` (`scroll_snap_data.cc:749-896`), plus a second scan for areas larger
  than the snapport (:966-988). There is no spatial index. Snap is an argmin over areas, O(N) per re-snap, float
  positions (:420-422). Proximity range is scrollport/3 (`snap_coordinator.cc:42`).
- `scroll-initial-target` is stable in 153 and cancels anchoring while it applies (`local_frame_view.cc:3256-3258`).

**Scroll anchoring** (`core/layout/scroll_anchor.cc`) *(code)*:
- `NotifyBeforeLayout` saves the anchor's offset when the scroller is laid out (`core/layout/block_node.cc:800-806`).
- `Adjust()` runs once per lifecycle pass (`local_frame_view.cc:3244-3263`).
- **No anchor at block offset 0** (`scroll_anchor.cc:620-628`).
- Selection: priority candidates (focused editable, find-in-page match), else the first fully visible in-flow box in
  DFS order, skipping `overflow-anchor: none`, fixed/sticky boxes and boxes whose containing block is outside the
  scroller (:202-212, 360-538). Out-of-flow boxes are tried in a second pass.
- The delta is `ToRoundedVector2d(now) − ToRoundedVector2d(saved)`: integer, block axis only (:655-680).
- After an anchoring scroll the anchor is kept and `saved_relative_offset_` isn't reset, so the offset tracks the
  anchor's **net** displacement. Results are clamped to [min, max].
- Suppression ("SANACLAP", `scroll_anchor.h:184-189`): any change on the anchor → scroller path to
  `top/right/bottom/left`, `margin-*`, `padding-*`, `width/height/min-*/max-*`, `position`,
  `contain-intrinsic-*`, or `transform` (`ComputedStyle` diff `disable_scroll_anchoring`, `computed_style.cc:865-867`)
  clears the anchor without scrolling. There is no adjustment counter or limit.
- *(measured, `scroll/anchor.html`)*:
  - **Mirror.** Content above the anchor animated 0 → 100 → 0 px: `scrollTop = 1000 + h`, the net change.
  - **Ratchet.** The content grows during the first half of a 1 s cycle; during the second half it shrinks while the
    anchor's ancestor animates `padding-right` (suppressed). `scrollTop` 1000 → 1100 → 1200 → 1300 → 1397, one step
    per cycle.

**`scroll-state()`** (`core/css/scroll_state_query_snapshot.cc:24-108`) *(code)*:
- It is a post-layout snapshot client: evaluated once per frame in `RunSnapshotPostLayoutStateSteps`, and a change
  repeats style and layout in that frame.
- `snapped` follows `snapped_query_target_ids_`, set on both the snapchanging and the snapchange paths, which is why
  css-physics HISTORY found it tracking the would-snap target mid-gesture.
- `scrolled` is set only for `cc::ScrollSourceType::kRelativeScroll` (`paint_layer_scrollable_area.cc:556-575`); see
  §5.

**CSS carousels** (`CSSPseudoScrollButtons`, `CSSPseudoScrollMarkers`, `CSSScrollTargetGroup`, `CSSPseudoColumn`, all
stable in 153):
- **`::scroll-button(<dir>)`.**
  - Click or Enter/Space → `ScrollButtonPseudoElement::HandleButtonActivation` → `ScrollByPageWithSnap`
    (`core/dom/scroll_button_pseudo_element.cc:181-221`; `paint_layer_scrollable_area.cc:1032-1049`).
  - The target is the page-snap position if any, else current + page. The page is
    `max(int(0.875 × snapport), 1)` (`cc/input/scroll_utils.cc:51-56`); the spec says "about 85%". The snapport
    subtracts `scroll-padding`.
  - The scroll is `kProgrammatic`, `kNone` source, behaviour `auto` → the scroller's `scroll-behavior`.
  - `:disabled` when no further target exists, recomputed in the post-layout snapshot (:231-279).
- *(measured, `scroll/btn.html`, 400 px scroller)*:

  | Setup | Offset after each click |
  |---|---|
  | no snap | +350 |
  | `width: 1px`, or `scroll-padding-left: 399px` | **+1** |
  | `scroll-padding-left: 397px` | +2 |
  | snap areas every 1 or 10 px (`x mandatory`) | +350 (dense snap doesn't shrink the step) |
  | 1 px snap areas every 10 px, snapport 1 or 8 px | +10 (next snap position) |
  | `scroll-behavior: smooth`, 350 px | ≈ 314 ms, a new main-thread offset every frame |

  - Each Enter/Space keydown and each auto-repeat keydown also stepped once.
  - A `scroll-timeline`-driven width showed the new offset at the first rAF after the click.
- **`::scroll-marker` / `:target-current`.**
  - Activation scrolls the originating element into view, aligned by its `scroll-snap-align`, and pins the selection
    until a non-targeted scroll (`core/dom/scroll_marker_group_pseudo_element.cc:18-137`).
  - The active marker is recomputed after every scroll offset change and every layout, in the post-layout snapshot
    (`scroll_marker_group_data.cc:205-297, 702-717`):
    - sort the candidates;
    - take the nearest of the largest target ≤ position and the smallest within position + scrollport/2;
    - redistribute near the ends.
  - *(measured, `scroll/marker.html`)*: with 100 px items the index is round-half-down(offset/100), updated in the same
    frame, and the count of markers matching `:target-before` equals the index (a thermometer code).

**Smooth scroll** *(code)*:
- `ProgrammaticScrollAnimator::AnimateToOffset` (`core/scroll/programmatic_scroll_animator.cc:63-176`) runs the curve
  on the compositor when the scroller is composited, else ticks it on the main thread.
- Duration `min(√|Δ|, 90)/60` s, ease cubic-bezier(0.4, 0, 0, 1) (`cc/animation/scroll_offset_animation_curve.cc:158-165`).
- Either way the main thread sees intermediate offsets each frame: a √Δ timer.
- Overscroll isn't readable: offsets are clamped, and elastic overscroll is a compositor transform. `OverscrollAreas`
  is experimental on main; 153 called it `OverscrollGestures`.

### 1.9 SMIL

**Clock and scheduling** *(code)*:
- Every `<svg>` owns a `SMILTimeContainer` (`core/svg/svg_svg_element.cc:81`), and an animation element joins its
  nearest `<svg>` (`core/svg/animation/svg_smil_element.cc:381-385`).
- It ticks in `ServiceScrollAnimations`, before CSS animation timing and rAF (`local_frame_view.cc:4067`).
- It requests frames only when something is due:
  - nothing while a `<set>` is frozen or waiting for an event (`smil_time_container.cc:513-525`);
  - an active `<set>` reports its interval end;
  - only `<animate>` within a finite simple duration asks for every frame (`svg_smil_element.cc:1285-1301`);
  - events more than 40 ms away use a timer.
- `UpdateTimedElements` pops due elements from a priority queue and loops until it reaches the target time, so
  several intervals can pass in one frame (:591-634).
- `ApplyTimedEffects` then re-applies **every** sandwich in the container (:670-694), frozen ones included.
- Times are `base::TimeDelta` (1 µs).

**Begin/end** (`svg_smil_element.cc:549-631`) *(code)*:
- offsets, clock values, `indefinite`;
- `id.begin`/`id.end` syncbases and `id.repeat(n)`;
- **any other name is a DOM event**, listened for on the element with that id in the tree scope, HTML included
  (:260-280, 613-616);
- `accessKey()` is parsed but unimplemented ("FIXME", :610-612); `wallclock()` becomes an event name.
- The target must be an `SVGElement` (:337-349). `<a href="#anim">` starts an animation without script
  (`core/svg/svg_a_element.cc:138-143`).
- An event adds an instance time and schedules a 0 ms wake-up, so the value lands at the next frame. *(measured)* It
  was visible in the first rAF after the click.
- Escaped hyphens in ids are not honoured (§5).

**What it can write** *(code + measured)*:
- SVG DOM attributes, including `class` (`core/svg/svg_element.cc:203-204`), geometry (`x/y/width/height`) and
  `href`.
- About 55 presentation properties (`core/svg/svg_animate_element.cc:93-147`): `visibility`, `display`, `font-size`,
  `pointer-events`, `opacity`…
- **Not** custom properties (`--x` is `kAnimatedUnknown`, :312-320), `style`, or HTML elements.
- CSS values enter as author-origin declarations after the author rules (`core/css/resolver/style_resolver.cc:1334-1353`,
  uncacheable). They beat ordinary author rules and lose to CSS animations and transitions.
- *(measured, `smil/a.html`, `t.html`)*:
  - `<set attributeName="width" begin="btn.click">` on a `<foreignObject>` → an HTML size container inside read
    `calc(100cqw / 1px)` = 300;
  - on an `<svg>` → `anchor-size()` read 250;
  - `<set attributeName="class" to="on">` → `html:has(#flag.on)` matched;
  - begin events that worked: `click` on an HTML button, `change`, `toggle`, `input`, `focus`, `keydown`,
    `scrollend`, `animationend`, `transitionend`;
  - a SMIL change *starts* CSS transitions, so SMIL can feed a transition latch.
- *(measured, `smil/c.html`)*: a two-`<set>` syncbase oscillator ran at its nominal rate (1 ms periods: ≈ 16.7
  intervals per frame, applied once per frame); an `accumulate="sum"` counter at 10 ms went 1 → 203 in 2.02 s.
  - Instance times from syncbases and events are never pruned (`svg_smil_element.cc:1529-1562`): a 10 µs oscillator
    grew the renderer by ≈ 1.5 MB/s.
- **Cost.** Idle: zero frames, zero recalcs *(measured)*. Running: O(every animation element in that `<svg>`) per
  tick, and attribute re-application always invalidates (`svg_element.cc:198-214`).
  - *(measured, `smil/p2.html`)*: a frozen `<set width>` on a `<foreignObject>` plus one running `<animate>` in the same
    `<svg>` caused a layout every frame; in separate `<svg>`s, none. **Isolate latches in their own `<svg>`.**

### 1.10 View transitions

*(code + measured)*:
- Old-element geometry reaches the new page only as UA `@keyframes -ua-view-transition-group-anim-<name>`
  (`core/view_transition/view_transition_style_builder.cc:140-199`), applied only to the pseudo-elements.
  `anchor-name` on a group pseudo isn't visible to DOM elements, and `cqw` inside the pseudo tree resolves against the
  viewport *(measured, `smil/vt*.html`)*.
- What does carry state across a JS-free same-origin navigation (`@view-transition { navigation: auto }`): *which*
  names and `view-transition-class`es the old page captured.
  - *(measured, `smil/vtx/`)*: an old-page checkbox set `view-transition-name`/`-class`; the new page gave the
    matching `::view-transition-old(...)` different durations.
  - `:root:active-view-transition` gated a paused meter animation to run while the transition lasted.
  - A registered `--t` read 116.6 / 616.6 / 1233.4 ms for none / name / name+class, and kept the value after the
    transition.
- Types come from the new page's own `@view-transition` (`view_transition_supplement.cc:564-616`), so they can't
  carry state.
- `:navigation-source` is new on main.

---

## 2. What it means for the projects

### 2.1 The per-registered-property cost: what triggers it, what it costs, how to dodge it

**Mechanism** (§1.4): each new or rebuilt keyframe model costs about 0.06 µs × R for the first animation of an element
and 0.02 µs × R for each further one. R counts registrations **with an `initial-value`**. It doesn't depend on whether
the property is used, which is ENGINE_NOTES 4's "used or not".

- **css-physics BENCHMARKS §4, root cause found.** `.bd`'s `transition: transform` restarts every pass, and each
  restart iterates all 24,896 registrations: 24,896 × 0.06 µs ≈ 1.5 ms per body per pass. BENCHMARKS derived
  1.25 ms. The compositor never mattered; the restart loop did. "Registrations are page-global, so CSS can't shield
  the bodies" is right, but the cost is in the *snapshot loop*, which an upstream fix (§4, idea 3) removes.
- **js-minus-js, where models are created** *(inference from the generators)*:
  1. **Showing the compile chain.** `#cc { display: if(style(--ccgo: 1): block; else: none) }` creates 24 line sources
     × 64 animations and one token-group source of 128 animations per 32 tokens. At R ≈ 4,229 that is
     ≈ 64 × 4,229 × 0.021 µs ≈ 5.7 ms per line source, ≈ 140 ms for the lines alone, once per Run.
     - BENCHMARKS §4a's fixed compile cost is 189 ms, so a large share of it may be this loop.
  2. **Every editor latch write and every RAM-group `--live` latch**: ≈ 0.25 ms per restart.
  3. **Anything that switches an `animation-*` longhand by `if()`/`@container`**: one rebuild per switch.
- **What to do:**
  - Measure first: add 4,000 dummy `@property … initial-value: 0` to the page and A/B Run → compiled
    (`halttime.js`). If it moves by ~0.1–0.2 s, the loop is a real share of compile time.
  - Keep R small where it counts. Pooled temp names and `SHARE` already do that. Registrations without an initial value
    (`syntax: '*'`) are free here, but only usable for untyped values (css-physics' `K`/`J` already are).
  - Create animations once: keep sources rendered and gate their consumers instead. ENGINE_NOTES 10 rules out
    "created paused" anyway.
  - Never toggle `animation-play-state`, `-duration` or `-timeline` per pass: each toggle is a rebuild, and play state
    doesn't latch per pass (§1.6).
  - Transition latches cost 0.06 µs × R per restart: few latches are fine, thousands per frame aren't.

### 2.2 Transition latches: per pass, with two rules (PRIMITIVES §P4, ENGINE_NOTES 23)

- **Per pass** *(measured)*. A latch writes and holds within one frame. PRIMITIVES §P4 ("frame-granular: a transition
  starts from the previous frame's value") and the comment in `readback/ui_rb.py:76-80` are contradicted by 153's
  code, and by the measurement for inherited inputs. The before-change style is the start of the current pass. The
  editor's own input path (a value read inside layout) is untested.
- **Rule 1: input through inheritance.** If the latch's input changes because of the element's *own* animation, the
  restyle is animation-only and no transitions are computed (css_animations.cc:3127).
- **Rule 2: control from outside.** The delay is read from the base style (ENGINE_NOTES 9). It must come from an
  ancestor, from a registered property derived from a register (§2.3), or from a style query.
- **Consequence for the editor scan.** It advances one column per frame by design (`--rbfresh`). With per-pass latches
  it could advance one column per *pass*: 2× today, D + 2× with the PRIMITIVES pass pump. That takes the 64-column
  sweep from ~1.2 s toward 0.6 s or less.
  - The latch input (the probe width) arrives inside layout (size container → `anchor-size()`). Transitions started in
    an in-layout recalc use the same `PostStyleUpdateScope`, so the same old style *(inference)*.
  - Cheapest check: drop `--rbfresh` from the scan counter and run `make l5-input`.
- **Hold cost.** Every held latch is serviced every frame (`Animation::Update`, a sort, the replaceable-animations scan;
  §1.3). It's small per latch but O(latches): retire latches that will never write again (`transition: none` once
  `--rbdet`), the same idea as PRIMITIVES recommendation 6.

### 2.3 Animation taint: what the latches silently depend on

- `transition` / `animation-*` values containing `var()` of an **animated property itself**, or of an **unregistered**
  property derived from one, compute to their initial values. `animation-delay: calc(var(--t) * -1ms)` became `0s`
  *(measured)*. With `transition: --x 0s calc(… var(--anim) …)` the whole shorthand would fall to `all 0s`: no
  latch, no error.
- The repo's latches use `calc((1 − var(--wnow)) × 10⁶ s)` (`memtree.py:67`) and `var(--rbhit)` (`ui_rb.py:123`).
  They work because `--wnow`/`--rbhit` are **registered** properties, which Chrome stores untainted.
  - Per css-variables-2 taint should propagate, so a spec fix would break them (§5).
  - `if(style(--flag: 1): 0s; else: 1000000s)` and `@container style()` gates select a literal branch, which isn't
    tainted under any reading of the spec today. They are the robust form for latch control.

### 2.4 Named timelines: where the lookups go (ENGINE_NOTES 13, the `.ts` nests)

- **ENGINE_NOTES 13, explained.** An animation on every level of a chain is restyled with the chain, so it takes the
  full `CalculateAnimationUpdate` path. Every one of its animations then walks the ancestors to its scope:
  O(depth) per animation, O(depth²) per chain. At ≈ 33 ns per visited ancestor, 64 animations at depth ~1,400 cost
  ≈ 3 ms, which is the note's "~3 ms per level".
- **js-minus-js today.**
  - The `.ls` line sources are still *inside* the character chain: line L's source sits at depth ≈ 65·L, and its
    names resolve against `body { timeline-scope: … }` (`compiler/ccpage5.py:205-210`, `machine/gen_fvm4.py:285`).
  - Each non-animation restyle of a source therefore costs 64 walks of up to ~1,500 elements, plus a linear scan of
    body's whole scope list (thousands of names) at the end of each walk.
  - Whether that happens per pass depends on whether the chain above a source restyles (it does while the scan
    writes, but the chain is `display: none` then).
  - At chain creation it is paid once per animation (≈ 24 × 64 × 26 µs ≈ 40 ms) *(inference)*.
  - **Option:** declare each line's 64 names in a `timeline-scope` on an element just above that line's levels. A
    scope must be an ancestor of both the subject (the latch cell's register) and the source, so this needs the latch
    cells' registers moved under the chain, or the global-scope flag. Simpler: keep body's list short by giving the
    CPU's and the chain's names separate scopes.
- **css-physics.**
  - **`#LS`** has 632 animations at depth ≈ 20, and is restyled only by its own animations (the `.rz` zeroing works),
    so its lookups rarely run.
  - **Register elements** are restyled every awake pass (their `top`/`left` inherit from `LF`). Each re-resolves its 2
    view timelines' attachments, walking from depth ≈ N + 10 to the `.ts` nest:
    316 elements × 2 × ~65 visits × 33 ns ≈ **1.4 ms per pass at 48 bodies** *(inference)*.
  - Shorten it by putting the `timeline-scope` list **on `#LS`** (an ancestor of every register and the consumer
    itself). That saves the 14 wrapper levels and `#LS`'s own walk.
  - HISTORY's "inside `.rz` rendering vanished" was never reduced and predates 153's scope rewrite. Test it again
    before assuming it.
- **The "24-name nests ~3× cheaper" note** (ARCHITECTURE §1, `gen3d.py:1649-1651`) **no longer holds**:
  - In 153 a scope check is a linear scan, and a lookup through a nest scans every inner wrapper's list before
    reaching its own. The expected compare count equals that of one list. *(measured)* One 840-name scope and 35 nests
    of 24 both ran at 2.2–2.7 ms per frame for 420 restyled register elements.
  - The 3× was real in Chrome 141, which rebuilt the scope's hash map on every restyle of the scope element. The scope
    then sat on `#L0`/`#RB`, which restyle every pass.

### 2.5 Registers: precision, cost per pass, compositor

- **Precision.**
  - View-timeline registers are 1/16 px: ≈ 24 bits over 10⁶ px (ARCHITECTURE §1 says 26). Scroll-offset registers are
    integer px in 153.
  - The binding limit is `var()`'s 6 significant digits (ENGINE_NOTES 2), so more timeline precision buys nothing
    until crbug 40266999 changes serialization.
  - Full `double` precision survives only into transitions, additive animations and `style()` comparisons.
- **Per-pass cost of N moving registers** *(code)*:
  - subject restyle with an attachment walk;
  - layout of the subject;
  - `ComputeTimelineState` for the `ViewTimeline` *and* its `DeferredTimeline`, at 2–3 snapshots per frame;
  - `OnValidateSnapshot` of each attached animation;
  - one full resolve of the consumer, which re-applies *all* its animations' interpolations, each serialized with
    `CssText`, and runs its cascade twice.
  This matches BENCHMARKS §2's "register readback floor": with R = 840, 7 moving registers cost 5.2–5.7 ms and all
  moving 10.5–11.4 ms. The consumer's restyle is the fixed part; each moving register adds its subject and timeline
  work.
- **Compositor: never.** Register animations and everything derived from them run on the main thread every pass
  (§1.5). `TrackAnimatedSources` on main is the first step towards compositing inherited animated values, but it's
  test-only.

### 2.6 Triggers for the projects

- **Not a per-pass latch** *(code + measured)*: evaluated at most at frame start and post-layout. With the default
  compositor path, evaluated on the impl thread and delivered 1–3 frames later.
- **Silent in `overflow: hidden` / `visibility: hidden` scrollers by default**, which is how both projects build
  registers (`.regs .sc`, `.rbreg`). A trigger on a register would need a composited, user-scrollable
  (`overflow: auto/scroll`) scroller, or `--disable-blink-features=CompositorTimelineTrigger`, which pages can't set.
  From 157, `ScrollVisibilityHiddenScrollers` also makes such scrollers real when `visibility: hidden` *(code)*.
- **Useful as** a hysteresis comparator, i.e. an edge detector with a dead band (`timeline-trigger` activation/active
  ranges), and as a frame-granular sample-and-hold of a register (`--en pause play` on the register's own animation).
  - css-physics could gate "body woke up" UI effects this way. The solver itself needs per-pass logic.
- **Not an input path**: there's no CSS event trigger in any Chromium. Use SMIL or scroll buttons (§2.7).

### 2.7 JS-free inputs and timers

| Primitive | Write | Read | Latency | Notes |
|---|---|---|---|---|
| `::scroll-button()` | click / Enter / Space / key auto-repeat → offset += `int(0.875 × snapport)` (or next snap) | scroll timeline, `:target-current`, snap | next frame | 1 px snapport gives +1 per activation; stable in 153 |
| `::scroll-marker` | click → scroll to marker's element (snap-aligned) | same | next frame | absolute writes: a radio group that writes a scroll register |
| SMIL `<set begin="id.event">` | any DOM event → attribute (`class`, `width`, `href`, …) | selectors (`:has(#flag.on)`), size containers, `anchor-size()` | next frame | zero idle cost; isolate in its own `<svg>` |
| SMIL syncbase oscillator / `accumulate="sum"` | time | same | per frame (catches up) | instance-time leak below 16 ms periods |
| scroll anchoring | content height above the anchor | the scroller's scroll timeline | per pass | net change only; a ratchet needs suppression on the shrink half |
| `scroll-behavior: smooth` | any programmatic scroll | scroll timeline | per frame | duration √Δ/60 s: a timer whose length is data |
| view transitions | old page's captured names/classes | durations → a gated meter animation | one navigation | a few bits across a same-origin navigation |

- **paint**:
  - SMIL `class` latches or scroll buttons could select the palette without the `<object>`-width trick *(speculation)*.
  - A `::scroll-button` counter is a readable, user-driven integer that survives as long as the document. It does
    not survive reloads (root scroll restoration does, paint HISTORY).
- **css-physics touch**: `ShouldDeferLayoutSnap` is page-global (any gesture), and re-snap sticks to the previously
  snapped element. `#FO` already works within both rules (`touch-snap-defer`).

---

## 3. What's changing (153 → 155 stable → 157 beta → main 158)

Runtime flags (`runtime_enabled_features.json5` per branch; `-` = present without status, i.e. off) *(code)*:

| Flag | 153 | 155 | 157 | main | Matters because |
|---|---|---|---|---|---|
| AnimationTrigger, TimelineTrigger, CompositorTimelineTrigger | stable | stable | stable | stable | §1.7; the cc path is what silences triggers in non-composited scrollers |
| EventTrigger (JS only) | exp. | exp. | exp. | exp. | no CSS event trigger anywhere |
| SkipTickingStaticAnimations | — | — | stable | stable | animations with no visible change stop ticking on the main thread. Held latches don't qualify (their two keyframes differ) *(inference)* |
| TrackAnimatedSources | — | test | test | test | groundwork for compositing animations whose values are inherited (`core/animation/inherited_animations/`) |
| CSSTreeScopedScrollTimeline | — | — | exp. | exp. | timeline names become tree-scoped (shadow DOM only) |
| CSSTimelineScopeGlobal | `-` | `-` | exp. | exp. | "makes timeline names global by default" (csswg-drafts#12581): a name unresolved at the root falls back to a document-wide deferred timeline (`FindGlobalTimeline`, css_animations.cc:1474-1497). It would remove the need for `.ts` wrappers, not the ancestor walk |
| CSSTimelineScopeAll | exp. | exp. | exp. | exp. | `timeline-scope: all` |
| AnimationRangeRejectRelativeLengths | — | exp. | exp. | exp. | stricter `view-timeline-inset`/range parsing (`view_timeline.cc:82-108`) |
| NeutralKeyframeEasingCompliance | — | — | — | stable | easing of synthetic neutral keyframes changes (`keyframe_effect_model.cc:531`) |
| CSSAnimationIterationComposite | exp. | exp. | exp. | exp. | `iteration-composite: accumulate` (`invalidatable_interpolation.cc:265-330`) |
| FractionalScrollOffsets | `-` | exp. | exp. | exp. | scroll registers stop rounding to px (then 1/16 px via the timeline) |
| ScrollVisibilityHiddenScrollers | — | — | stable | stable | user-scrollable `visibility: hidden` scrollers become real scrollers (`scrolls_overflow_`, `paint_layer_scrollable_area.cc:2668-2685`). `overflow: hidden` registers are unaffected; `overflow: auto` ones may gain scroll nodes and compositing |
| SingleAxisScrollContainers | exp. | exp. | stable | stable | `overflow: clip` on one axis with a scrolling other axis stays `clip` instead of becoming `hidden` (`style_adjuster.cc:690-715`): one-axis scrollers |
| CSSScrollSnapTypePair | test | exp. | stable | stable | new `scroll-snap-type: pair …` axis keyword (`longhands_custom.cc:9287-9297`) |
| CSSScrollMarkerGroupModes | exp. | stable | stable | stable | `scroll-marker-group: … links/tabs` |
| CSSPseudoElementScrollButton | — | — | exp. | exp. | JS objects for scroll buttons |
| OverscrollGestures → OverscrollAreas | exp. | exp. | exp. (renamed) | exp. | `overscroll-container-type`; not readable |
| RemoveTargetCurrent | stable | stable | — | — | flag removed |

**Code changes 153 → main** (diffs of `core/animation`, `core/scroll`, `core/svg/animation`,
`core/layout/scroll_anchor*`) *(code)*:
- `css_animations.cc` (313 changed lines): tree-scoped timeline names (`ScopedCSSName` plus a tree scope in every
  lookup), the global-timeline fallback, trigger attachment and native-paint-worklet plumbing.
  - The `CalculateAnimationUpdate` and transition logic, the snapshot loop of §1.4 (`keyframe_effect_model.cc`
    changed only to add `IsDynamicProperty`/static-keyframe checks) and the 16 µs/px constant are unchanged.
- `view_timeline.cc`: inset validation (`ShouldRejectInsetValue`).
- `scroll_anchor.*`: the anchor became a weak reference; the priority-candidate subtree change shipped and its flag
  was removed. Behaviour is the same.
- SMIL: `element_smil_animations.cc` iterates a copy of the sandwich map; `svg_smil_element.cc` changed only
  `onbegin`/`onend` plumbing (JS-only).
- Triggers: grammar identical in 153, 155 and main. The CSSWG moved triggers to animation-triggers-1, removed
  `play-alternate`/`play-pause` (csswg-drafts#12611) and specified CSS event triggers, none of which Chromium has
  implemented.
- `CSSNumericLiteralValue::FormatNumber` switched to `absl::StrFormat("%.6g")` (round-to-even kept): still 6 digits.

---

## 4. Ideas, ranked by expected value × confidence

1. **Per-pass latches for the js-minus-js editor scan** *(code-backed, toy measured)*.
   - Advance the scan one column per pass instead of per frame: drop the `--rbfresh` gate on the column counter; keep
     the latch control on an inherited flag or a style query.
   - 2× faster sweep at today's 2 passes per frame, more with the PRIMITIVES pass pump.
   - Kill test: `make l5-input` with the gate removed; then time Run → compiled.
2. **Measure, then cut, the O(R) snapshot loop in js-minus-js** *(code-backed + measured mechanism; impact
   inference)*.
   - A/B the page with 4,000 dummy `@property … initial-value` added.
   - If Run → compiled rises by ≳ 0.1 s, chain creation (24 × 64 + group × 128 animations) is paying it. Then:
     - create the line and group sources once and keep them rendered, gating the chain's *consumers* instead of
       `display: none` on `#cc`;
     - or cut registrations with initial values.
3. **Report the snapshot loop upstream** *(code-backed)*.
   - `SnapshotCompositableProperties` should iterate the model's own custom-property keyframe groups (or bail when no
     paint worklet uses the property) instead of `GetVariableNames()`. A few-line change.
   - It would remove ENGINE_NOTES 4 and BENCHMARKS §4's cost for everyone with many registrations, and make
     css-physics' pose transitions affordable again. They'd still restart every pass, and HISTORY's snap-back problem is
     separate.
   - MRE: `exp/04/regcost/trans_R4000.html` vs `trans_R0.html` (§5).
4. **css-physics: `timeline-scope` on `#LS` instead of 14 `.ts` wrappers** *(code-backed; gain is inference)*.
   - Shortens every register's attachment walk (316 elements × 2 per awake pass) and `#LS`'s own lookups. Predicted
     ≈ 0.3–1 ms per pass at 48 bodies.
   - Risk: HISTORY's "inside `.rz` rendering vanished".
   - Kill test: `ab.js` on the frozen 48 pile with the scope moved; check rendering.
5. **SMIL as the event layer** *(code-backed + measured)*.
   - `<set begin="X.click|change|toggle|keydown|transitionend|animationend|scrollend" attributeName="class">` +
     `:has()` gives event-driven state with no idle cost.
   - `<set width>` on a `<foreignObject>` + `cqw` gives an event-driven number.
   - For paint (palette and tool state without fetches) and js-minus-js (Run/Edit beyond the checkbox, e.g. "step"
     or "reset" buttons).
   - Isolate each machine in its own `<svg>`; use ids without hyphens (§5).
   - Kill test: one `<set class>` latch in the XHTML page.
6. **`::scroll-button` as a counter/stepper** *(measured)*.
   - A 1 px snapport gives +1 per click, key or auto-repeat, readable by a scroll timeline next frame.
   - Use it for a "step one instruction" button in js-minus-js, or a quantity control in paint.
   - `:target-before` counts give the same value as a thermometer code readable by selectors.
7. **Sample-and-hold via `animation-trigger: --en pause play`** on a register's own animation *(measured)*.
   - Frame-granular, needs a composited scroller by default; for UI-rate latching only.
8. **Scroll-anchoring ratchet as a per-pass integrator** *(measured toy; speculation as a design)*.
   - `scrollTop += Δheight` for growth while unsuppressed; suppress the shrink half with a padding change.
   - Integer, block axis, offset ≥ 1. Readable by a scroll timeline; adds per pass (anchoring runs after every
     layout).
   - Nothing in the projects needs an integrator outside the style engine today.
9. **Full-precision readout through `style()` range queries** *(speculation)*. Registered values compare as
   `double`s in container style queries, so a binary search of range queries reads more than 6 digits. Too
   expensive per bit (1.7 µs per range query) except for a few values.
10. **Cross-navigation bits via view transitions** *(measured, 2-level)*. paint already has a better store; noted
    for completeness.

---

## 5. Possible bugs

| # | Bug | Where | Spec / evidence | Repro |
|---|---|---|---|---|
| 1 | **Perf: every keyframe-model snapshot iterates all registered properties** (O(R) per new animation/transition), though only paint-worklet custom properties can be composited | `keyframe_effect_model.cc:337-354` + `computed_style.cc:2272-2288` | perf, no spec; 0.06 µs × R per restart *(measured)* | `exp/04/regcost/trans_R{0,4000}.html`, `animupd_*`, `m_R*_K16.html` |
| 2 | **Registered custom properties drop animation taint** | `custom_property.cc:194-195` (taint = `ValueMode::kAnimated` only) | css-variables-2 §2: "Animation-tainted is 'infectious': custom properties which reference animation-tainted properties also become animation-tainted." *(measured: `#G` in `latch.html`)* | `exp/04/latch/latch.html` |
| 3 | **`animation-trigger: --t play-pause` / `play-alternate` crashes the renderer** | parser accepts them (`core/css/properties/css_parsing_utils.cc:4756-4758`); `CssValueIDToPlatformEnum<EAnimationTriggerBehavior>` → `NOTREACHED()` (`core/css/css_value_id_mappings.h:572-573`) | animation-triggers-1 action grammar has neither *(measured crash)* | `exp/04/trig/mre/chrome-animation-trigger-play-pause-crash.html` |
| 4 | **Compositor timeline trigger never fires in a non-composited scroller** (`overflow: hidden`, `visibility: hidden`) | `timeline_trigger.cc:63-69` (main thread bypassed once a cc trigger exists); `cc/animation/scroll_timeline.cc:71-75` (inactive without a composited scroller) | animation-triggers-1 §3: a trigger "is activated when some timeline enters the trigger's activation range" *(measured)* | `exp/04/trig/mre/chrome-timeline-trigger-overflow-hidden.html` |
| 5 | **Timeline trigger misses a layout-only change on an idle page** | impl-side evaluation only in `TickAnimations` *(inference)* | same *(measured)* | `exp/04/trig/mre/chrome-timeline-trigger-idle-page.html` |
| 6 | **A 0 s effect keeps a stale phase** (end keyframe shown before the trigger plays; WAAPI `pause()`+`reverse()` progress 1 at time 0) | `animation_effect.cc:330-332` ignores direction and `paused_for_trigger_`; `SetPausedForTrigger` doesn't invalidate (:406-408) | web-animations-1 before-phase definition *(measured)* | `exp/04/trig/mre/chrome-zero-duration-stale-phase.html` |
| 7 | **`::scroll-button` activation doesn't update `scroll-state(scrolled)`** | `ScrollByPageWithSnap` passes `ScrollSourceType::kNone` (`paint_layer_scrollable_area.cc:1047`); `UpdateLastScrolled` needs `kRelativeScroll` (:560) | css-conditional-5 `scrolled`: "the direction of its most recent relative scroll"; css-overflow-5: buttons scroll "by one 'page' … similar to pressing PgUp/PgDn" *(measured)* | `exp/04/scroll/scrolled.html` |
| 8 | **Anchoring stays suppressed after an ancestor's `transform` animation has changed value, even through constant stretches** | suspected `transform_changed` diff for animated transforms (`computed_style.cc:825-835`), unconfirmed | css-scroll-anchoring-1 §2.2.2 triggers on a *change* of computed `transform` *(measured)* | `exp/04/scroll/anchor2.html`, `anchor3.html` |
| 9 | **SMIL ignores escaped hyphens in ids** (`my\-btn.click` dropped) | `ParseCondition` splits on the first `+`/`-` (`svg_smil_element.cc:554-558`); only `.` is escape-aware (:511-525) | SMIL 3.0 Timing: "The reverse solidus character '\' must be used to escape these characters within Id-values" *(measured)*; old report crbug 41291793 closed obsolete 2018 | `exp/04/smil/bug-smil-escaped-hyphen.html` |
| 10 | **SMIL instance times from syncbases/events are never pruned** | `PruneOldInstanceTimes` prunes script-origin times only (`svg_smil_element.cc:1529-1562`) | resource growth, not a spec violation *(measured ≈ 1.5 MB/s at 10 µs periods)* | `exp/04/smil/m.html` |

Not bugs: `if(style(--tainted…))` and `@container style()` selecting `animation-*`/`transition-*` values are
untainted. css-values-5 doesn't address taint in `if()`, so that is a spec gap. Chrome's active-marker choice
differs from the spec's non-normative example.

Unreduced: a scroll-driven animation paused by style at ≥ 100% progress stays stuck after release until the timeline
changes (WAAPI `play()` too; `exp/04/trig/ps*.html`).

## Open questions

- **ENGINE_NOTES 38** (a third pass appears or disappears unexplained): any `ScrollSnapshotTimeline` whose state
  changes in the post-layout snapshot repeats the lifecycle, animations or not (`scroll_snapshot_timeline.cc:227`,
  `local_frame.cc:4389-4398`). `#cpu`'s timelines and the 1,536 extra ones change which client reports first. That
  fits, but isn't verified.
- **Does js-minus-js rebuild models per frame anywhere?** The dummy-registration A/B (§2.1) answers it.
- **Do in-layout (size-container) restyles start transitions from the pass's old style?** The code says yes (one
  `PostStyleUpdateScope` per `UpdateStyleAndLayout`, `StoreOldStyleIfNeeded` when `size_container` is set,
  `style_resolver.cc:180-207`); untested.
- **Is `.ts`-inside-`.rz` still broken in 153?** It is the precondition for idea 4.
- **Scroll offsets around 2²⁴**: why 16777215 rounds to 16777216 (`scroll/big.html`); irrelevant at 10⁶ px.
