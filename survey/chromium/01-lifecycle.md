# 01. The frame lifecycle: how Chrome produces a frame, and where the projects' passes fit

Source: Chromium main `22b3b159` (2026-10-18, M158) unless a line says 153 (branch 8010) or 155 (8059). Paths are
from the src root; `core/` = `third_party/blink/renderer/core/`, `platform/` = `third_party/blink/renderer/platform/`.
Probes ran in the repo's headless Chromium 153.0.8010.12 (`/usr/local/bin/chromium` = Chrome for Testing, full Chrome,
so Playwright's `--headless` is new headless) on a loaded machine (load average 5–7: other agents). They answer
yes/no and frame-count questions only. Probe files: `exp/01/`
(`svgchan/`: channel, process and feedback-loop probes; `gap/`; `roerr/`; `svgcalc/`).
Labels: *(code)*, *(measured)*, *(docs)*, *(inference)*.

Neighbours: style recalc, invalidation and container queries in [02-style-engine.md](02-style-engine.md);
animations, timelines and scroll machinery in [04-animations-and-scroll.md](04-animations-and-scroll.md); layout
in [05-layout.md](05-layout.md); loading in [08-interactivity-and-loading.md](08-interactivity-and-loading.md).

## Findings in brief

1. **A child document can send numbers to its parent across processes without script, today, in 153.** An SVG
   document in an `<object>` reports its natural size to the embedding page on every font change, over IPC, and
   the parent lays the `<object>` out at that size. With `<svg width="1000em">` and `font-size` computed from the
   child's state, the parent's `anchor-size()` → `cqw` reader got the child's value with **1 frame of round-trip
   latency** at 60 fps, float32 precision quantized to 1/64 px *(measured)*. css-physics HISTORY ("Iframes for
   parallelism") and js-minus-js ENGINE_NOTES 32 say the only channel is parent→child; that is wrong.
2. **A single origin can get extra processes without script.** A child served with `Content-Security-Policy:
   sandbox` lands in a separate renderer (one shared process per origin of sandboxed documents). A child served with
   `Origin-Agent-Cluster: ?1` gets a process per origin, so K origins give K processes even on one site
   *(measured, code)*. Both are static `_headers` rules. With (1), the "multicore" idea is alive, with a narrow
   channel: about 1 value down and 1–2 up per child document per frame.
3. **Responsive iframes** (`frame-sizing: content-width|content-height` on the `<iframe>`, `<meta
   name="responsive-embedded-sizing" content="allow-origins=…">` in the child) shipped in **M154**: experimental in
   153, stable in 155 *(code, docs)*. An HTML child reports its size only at DOMContentLoaded, at load, and on
   `window.requestResize()`, so it is no per-frame channel without script. An SVG child in such an iframe reports
   on every font change, as in (1) *(code)*.
4. **The pass-count mechanism is the same 153 → main except for the loop-limit round.** One post-layout snapshot
   of scroll-linked state per lifecycle, re-armed whenever the ResizeObserver step delivers. The RO depth rule bounds
   RO-driven re-runs, and there is no numeric cap anywhere (see 10). The prior survey's "pass pump" is confirmed in
   code. The exception: in 153–155 the loop-limit (error) round returns "no repeat" once pre-paint is clean; from
   156 (commit `0728ae248a`, [09-roadmap.md](09-roadmap.md) §2.3) it repeats the lifecycle once per frame whenever
   observations were skipped *(code, both trees; lead's check)*. New details: an RO-triggered re-run also
   re-runs compositing inputs, pre-paint, post-layout IntersectionObserver and the RO gather, while a
   snapshot-triggered re-run skips them. And a pump whose observations get skipped fires a window `error` event
   and forces another frame, every frame *(code; 60 error events/s measured on the prior survey's `nest8` and
   `sib4` pages)*.
5. **Anchor positioning's "last successful option" doesn't re-run the lifecycle in steady state.** A newly
   successful option is applied without a re-run; only a change of `position-try-fallbacks` or of `@position-try`
   rules re-runs it *(code; matches the prior survey's measured "no effect")*. Container-query-list steps re-run
   it, but they are test-only and need script. View-transition steps need a navigation or script.
6. **ENGINE_NOTES 37/38 from the code.** The third ("settle") pass needs a re-arm, and on js-minus-js's full page
   that is the RAM leaves' remembered-size recording after pass 2. The CPU-only page has no such delivery, hence
   2 passes. There's a trace recipe below (§1.10) that attributes every iteration to its trigger.
7. **A 100 ms BeginMainFrame is followed by the next one at once.** The idle gap between main frames was a median
   0.1–0.2 ms, under 0.5% of main-thread time, with or without `--disable-frame-rate-limit` *(measured)*. cc sends
   BeginMainFrame N+1 in the same scheduler pass as commit N, and the commit is non-blocking *(code)*.
   **Uncapping the frame rate buys nothing** for these pages; raster already overlaps the next main frame.
8. **The animation clock is frozen per frame** at the `frame_time` of the vsync tick in progress when the
   BeginMainFrame was sent, clamped to 100 µs. Every pass of a frame sees the same time. Successive frame times jump
   in vsync multiples (100.0 or 116.7 ms), which explains ENGINE_NOTES 18 *(code)*.
9. **Throttling:** offscreen *same-origin* frames are never render-throttled. Offscreen *cross-origin* frames,
   opaque-origin ones included (sandboxed, CSP-sandboxed, data:), skip their whole lifecycle, and their animations
   stop. A multicore child must keep at least 1 px in the viewport *(code)*.
10. **A same-process SVG `<object>` whose size feeds back into its own style is an unbounded in-frame loop.** The
    lifecycle loop re-runs whenever any frame still needs layout after pre-paint (`local_frame_view.cc:1686-1689`),
    with no counter. A same-origin `<object>` whose `<svg width="1em">` has `font-size: min(calc(100vw + 1px),
    1000px)` grew from 300 to 1000 px in **one BeginMainFrame: 700 lifecycle iterations, 48–57 ms**, with no
    ResizeObserver round and no snapshot re-arm *(measured)*. It is a pass pump without the depth rule, though it
    refreshes only what style and layout compute directly (size queries, anchors, natural sizes), not timelines or
    remembered sizes. An oscillating version (`calc(100vw + 1px - 2 * mod(100vw, 2px))`) **hangs the renderer**:
    no frame within 8 s *(measured; possible bug, §5)*.
11. **Missing invalidation (possible bug):** an outer `<svg width="calc(1em + 0px)">` doesn't notify its
    `<object>` when the font changes. The same-process parent never updated and the cross-process one updated
    sporadically *(measured)*. The cause is `SVGLength::IsFontRelative` seeing only literals (TODO
    crbug.com/979895).
12. **Tracing `devtools.timeline` adds a full layout-tree walk to every layout.** The `Layout` event's beginData
    calls `CountObjectsNeedingLayout`, a pre-order walk of every layout object, skipping display-locked subtrees
    (`local_frame_view.cc:702-715, 913-917`). The repo's traces include this cost in every pass *(code)*.

---

## 1. How it works

### 1.1 Threads and the frame pipeline

```
 viz (GPU process)        renderer: compositor thread            renderer: main thread
 ─────────────────        ───────────────────────────            ─────────────────────
 DelayBasedBeginFrame ──► cc::Scheduler::OnBeginFrame
 Source, 60 Hz            BeginImplFrame(args)
                          SEND_BEGIN_MAIN_FRAME ───────────────► ProxyMain::BeginMainFrame (proxy_main.cc:174)
                          (impl keeps ticking every vsync:        ApplyCompositorChanges (scroll deltas)
                           compositor animations, scrolls,        WidgetBase::BeginMainFrame: rAF-aligned input
                           DidNotProduceFrame(kWaitingOnMain))    Page::Animate(frame_time): clock frozen,
                                                                    scroll animations, frame-start timeline
                                                                    snapshot, SMIL, CSS/WA timing, rAF
                                                                  AnimateLayers (may wait for previous commit)
                                                                  UpdateLifecycle(kAll):
                                                                    loop { style+layout, snapshot,
                                                                           compositing inputs, pre-paint,
                                                                           post-layout IO, ResizeObserver }
                                                                    paint, layerize (PaintArtifactCompositor)
                                                                  UpdateLayers, WillCommit
                          READY_TO_COMMIT ◄─────────────────────  post NotifyReadyToCommitOnImpl
                          COMMIT → pending tree                   DidBeginMainFrame: RunPostLifecycleSteps
                          SEND_BEGIN_MAIN_FRAME (N+1) ─────────►   (AX, IntersectionObservers, throttling)
                          PrepareTiles → raster workers (≤4)    ◄─ next BeginMainFrame starts at once
                          ACTIVATE → DRAW → SubmitCompositorFrame
```

- **BeginFrames.** In new headless (`chrome --headless`), viz's root sink uses a `DelayBasedBeginFrameSource` at
  `BeginFrameArgs::DefaultInterval()` = 1/60 s, unless `--disable-frame-rate-limit` selects a
  `BackToBackBeginFrameSource`. External begin-frame control (`HeadlessExperimental.beginFrame`) exists only in
  chrome-headless-shell (`//headless`), not in the Chrome for Testing binary the repo runs
  (`components/viz/service/frame_sinks/root_compositor_frame_sink_impl.cc:168-240`) *(code)*.
- **Compositor thread.** `cc::Scheduler` (`cc/scheduler/scheduler.cc`) runs a `SchedulerStateMachine`. Its
  `NextAction` puts SEND_BEGIN_MAIN_FRAME ahead of COMMIT, ACTIVATE and DRAW. Renderers commit to a pending tree
  (`commit_to_active_tree = !is_threaded`, `platform/widget/compositing/layer_tree_settings.cc:218`). Main frame
  before commit is forced on (`cc/trees/proxy_impl.cc:144`). Main frame before activation is on with ≥ 4 CPUs
  (`content/browser/gpu/compositor_util.cc:501-511`) *(code)*.
- **Main thread, BeginMainFrame.** `WidgetBase::BeginMainFrame` (`platform/widget/widget_base.cc:1173`) first
  dispatches rAF-aligned input (coalesced touch and mouse moves) at `args.frame_time`. Then
  `WebFrameWidgetImpl::BeginMainFrame` (`core/frame/web_frame_widget_impl.cc:3053`) calls
  `RecomputeMouseHoverStateIfNeeded` and `Page::Animate(frame_time)` → `PageAnimator::ServiceScriptedAnimations` (`core/page/page_animator.cc:78`).
  That runs the HTML event-loop steps 6–14: reveal, autofocus, resize, scroll, media queries, animation update and
  events, fullscreen, video frame callbacks and rAF. Animation timing is updated per document through
  `LocalFrameView::ServiceScrollAnimations` (`core/frame/local_frame_view.cc:4041`), which ticks scroll animations,
  snapshots scroll timelines at frame start (`:4063-4066`: `SnapshotScrollTimelinesPostLayout` has no status, so
  it is off in 153 and main), services SMIL and calls `UpdateAnimationTimingForAnimationFrame` *(code)*.
- **Main thread, lifecycle.** `ProxyMain::BeginMainFrame` → `RequestMainFrameUpdate` → `WidgetBase::UpdateVisualState`
  (`widget_base.cc:1156`) → `WebFrameWidgetImpl::UpdateLifecycle(kAll, kBeginMainFrame)` (`:1843`) →
  `PageAnimator::UpdateAllLifecyclePhases` → `LocalFrameView::UpdateAllLifecyclePhases` (`local_frame_view.cc:2200`)
  → `UpdateLifecyclePhases` (`:2405`) → `UpdateLifecyclePhasesInternal` (`:2547`, §1.2). Paint and
  `PushPaintArtifactToCompositor` (layerization, `:3399`) follow; `DocumentAnimations::UpdateAnimations` runs
  after paint (`:3140`), starting pending animations and requesting the next frame *(code)*.
- **Commit.** Non-blocking: `bool blocking = block_on_next_commit_` (`cc/trees/proxy_main.cc:337`) is set only when
  the frame carries an input response. Main can still wait inside the *next* BeginMainFrame, at `AnimateLayers`
  (`:362`), if the impl thread hasn't finished copying the previous commit (`LayerTreeHost::WaitForCommitCompletion`)
  *(code)*.
- **After commit.** `WebFrameWidgetImpl::DidBeginMainFrame` → `LocalFrameView::DidBeginMainFrame` →
  `RunPostLifecycleSteps` (`local_frame_view.cc:1083-1108`): accessibility, the IntersectionObserver steps (lazy
  loading, iframe throttling status, author observers), post-lifecycle observers. These results apply to the next
  frame *(code)*.

`DocumentLifecycle` states (`core/dom/document_lifecycle.h:49-82`): kVisualUpdatePending → kInStyleRecalc →
kStyleClean → kInPerformLayout → kAfterPerformLayout → kLayoutClean → kInCompositingInputsUpdate →
kCompositingInputsClean → kInPrePaint → kPrePaintClean → kInPaint → kPaintClean. Every loop iteration resets every
unthrottled view to at most kVisualUpdatePending (`local_frame_view.cc:2580-2587`), so a re-run is "dirty
phases only", not a full redo: a clean document passes through style and layout in microseconds.

### 1.2 The update loop: where the passes come from

`UpdateLifecyclePhasesInternal` (`local_frame_view.cc:2547-2792`), stripped to its control flow:

```cpp
bool should_run_post_layout_snapshot_client_steps = true;      // :2555, one-shot
bool should_run_container_query_list_steps = true;              // main only, flag "test"
while (true) {                                                  // :2579, no counter
  RunStyleAndLayoutLifecyclePhases(target_state);               // :2924  style + layout (+ inner loops, §1.4)
  if (should_run_post_layout_snapshot_client_steps) {           // :2601
    should_run_post_layout_snapshot_client_steps = false;
    if (RunSnapshotPostLayoutStateSteps(...)) continue;         // :2794  → re-run, skips pre-paint
  }
  RunCompositingInputsLifecyclePhase(); RunPrePaintLifecyclePhase();   // :2632, :2636
  if (RunPostLayoutIntersectionObserverSteps()) continue;       // :2678  c-v:auto first observation
  for each unthrottled view: needs |= RunResizeObserverSteps(); // :2690  RO + anchor fallback
  if (needs) { should_run_post_layout_snapshot_client_steps = true; continue; }   // :2697 re-arm
  [ContainerQueryList steps: same re-arm; test-only]            // :2706-2724
  if (!RunViewTransitionSteps()) break;                         // :2730
}
ClearResizeObserverLimit();                                     // :2760  depth limit resets per frame
RunPaintLifecyclePhase(kNormal);                                // :2789
```

**The snapshot.** `RunSnapshotPostLayoutStateSteps` → `LocalFrame::UpdatePostLayoutSnapshotClients`
(`core/frame/local_frame.cc:4389`): `valid &= !client->UpdateSnapshot()` over every `PostLayoutSnapshotClient`
in every unthrottled frame. Clients in main: `ScrollSnapshotTimeline` (scroll and view timelines),
`ScrollStateQuerySnapshot` and `SnappedQueryScrollSnapshot` (`scroll-state()` container queries),
`AnchorPositionScrollData`, `ScrollMarkerGroupData`, `ScrollButtonPseudoElement` and `TextOverflowPostLayoutSnapshot`
*(code)*. For a timeline, `ScrollSnapshotTimeline::UpdateSnapshotInternal`
(`core/animation/scroll_snapshot_timeline.cc:221-291`) compares the new `TimelineState` (current time, scroll
offsets, view offsets, zoom) with the stored one. If the layout part changed (`!HasConsistentLayout`: a view-timeline
subject moved, or the range changed), every attached animation gets `OnValidateSnapshot(true)` →
`InvalidateEffectTargetStyle()`. The next pass's `Document::UpdateStyleAndLayoutTree` calls
`UpdateAnimationTimingIfNeeded()` (`core/dom/document.cc:2829`), which brings the outdated animations up to the
new snapshot.

**The re-arm.** `RunResizeObserverSteps` (`:2870-2889`) returns true when
`StyleEngine::UpdateLastSuccessfulPositionFallbacksAndAnchorScrollShift()` invalidated something, or when
`NotifyResizeObservers()` (`:2328-2369`) delivered. Delivery happens when
`ResizeObserverController::GatherObservations` finds any observation whose size is out of sync **and deeper than
the shallowest depth delivered earlier in this lifecycle** (`core/resize_observer/resize_observer.cc:137-154`,
`min_depth_`). Depth is counted per observation by walking the flat tree to the root
(`resize_observation.cc:101-107`: O(depth) per changed observation per round). An observation that changed but
isn't deeper is *skipped*. Then the controller clears observations, dispatches one `ErrorEvent` "ResizeObserver
loop completed with undelivered notifications", calls `ScheduleAnimation()` and returns true once more
(`IsLoopLimitErrorDispatched`) *(code)*.

**The UA's own ResizeObservers** go through the same controller:
- `Document::intrinsic_size_observer_` (`document.cc:5639-5656`, delegate `:751-767`, `DeliveryTime::kBeforeOthers`)
  records last remembered sizes for `contain-intrinsic-size: auto`. `Element::ProcessContainIntrinsicSizeChanges`
  (`core/dom/element.cc:6262-6297`) observes an element only while it is **not** skipping its contents ("The only
  case where we _don't_ record new sizes is if we're skipping contents"). So a `content-visibility: hidden` leaf is
  unobserved while locked, and observed while a write unlocks it.
- `lazy_loaded_auto_sized_img_observer_` (`document.cc:5658-5694`) serves `<img loading=lazy sizes=auto>`.
- Media captions use internal observers too (`html/track/*`).
- Any delivery from them re-arms the snapshot exactly as an author RO would *(code)*.

### 1.3 Every re-entry trigger

| Trigger | Code | Re-runs when | Re-arms snapshot | Bound | Without script |
|---|---|---|---|---|---|
| Post-layout snapshot | `:2601-2608`, `local_frame.cc:4389` | any client's state changed in the pass | — | once, plus once per re-arm | yes (timelines, `scroll-state()`) |
| c-v:auto relevance | `:1668-1692`, `display_lock_document_state.cc:140-176` | **first** observation of an element dirtied style/layout; later changes go to the next frame's start-of-lifecycle tasks | no | once per element | yes |
| Other post-layout IO | same | only if the delivery dirties layout; `position-visibility` only toggles paint | no | — | yes, no effect |
| **Any frame still needing layout after pre-paint** | `:1686-1689` (the `frame_view.NeedsLayout()` term) | something dirtied layout after the frame's own layout, e.g. a same-process SVG subdocument's natural size changed by its own viewport | no | **none** | yes: 700 iterations in one frame (measured, §1.8) |
| Internal RO: `contain-intrinsic-size: auto` | `:2328`, `document.cc:5639` | a non-skipped element's content box size changed, deeper than the last delivery | **yes** | depth rule | yes: the pass pump |
| Internal RO: `sizes=auto` lazy images | `document.cc:5658` | img width changed | yes | depth rule | yes (may refetch) |
| RO loop-limit error | `:2347-2367` | skipped observations; **153–155: no re-run** once pre-paint is clean (`if (state >= kPrePaintClean) return false`), 156+: one re-run | 156+ only | once per lifecycle; also `ScheduleAnimation()` | yes (measured, §5) |
| Author RO / ContainerQueryList | `:2690`, `:2706` | delivery / `matchContainer()` change | yes | depth / once | no |
| Anchor last-successful option | `style_engine.cc:5095-5117`, `out_of_flow_data.cc:35-73` | `position-try-fallbacks` changed and layout recorded no new option, or `@position-try` rules changed | yes | — | practically no |
| View transitions | `:2829-2868` | a transition dirtied style/layout | no | — | cross-document VT only |

Not re-entry triggers, though often suspected:
- **Scroll anchoring and snap.** `PerformScrollAnchoringAdjustments` and `ExecutePendingSnapUpdates`
  (`:2948-2951`) run inside every `RunStyleAndLayoutLifecyclePhases`, after layout. They move scroll offsets,
  which the snapshot sees only if it hasn't run yet in this lifecycle. A snap correction in pass ≥ 2 is stale
  until the next frame unless an RO re-arm follows *(code)*.
- **New successful position options.** `ApplyPendingSuccessfulPositionFallbackAndAnchorScrollShift` returns false:
  "Last attempt resulted in new successful fallback, which means the anchored element already has the correct
  layout" (`out_of_flow_data.cc:57-62`). Remembered anchor scroll offsets are applied without a re-run either
  (TODO at `:45-49`). The prior survey's "position-try flipping per pass: 2 passes (no effect)" is this *(code +
  measured there)*.
- **Lazy loading and author IntersectionObservers.** They run in `RunPostLifecycleSteps`, after the frame.

**There is no numeric cap.** The loop is `while (true)`. Its bounds are:
- the one-shot snapshot;
- the RO depth rule: each RO-driven round needs a strictly deeper changed observation, so rounds ≤ the depth of
  the deepest observed element;
- one loop-limit-error round (156+; in 153–155 the error round doesn't re-run);
- one first-observation round per c-v:auto element;
- for "still needs layout" re-runs, convergence of whatever keeps dirtying layout. Nothing else bounds them.

Without same-process subdocument feedback, useful passes per frame are therefore at most 2 + (number of RO
rounds), + 1 from 156 for the error round. A nest of D `contain-intrinsic-size: auto` elements that change every
pass gives D + 2 (the prior survey measured 33.7 per frame at D = 32). Siblings gave 3 there: the first RO round
delivers and re-arms; the second finds them at the same depth and skips them, and in 153 that error round ends the
loop. From 156 it re-runs once more, so expect 4 *(measured there; code for the reason)*.

Each *kind* of re-run costs differently. A snapshot re-run `continue`s before compositing inputs and pre-paint.
An RO, IO or anchor re-run has already done compositing inputs, pre-paint, the post-layout IntersectionObserver
computation (all c-v:auto elements and post-layout observers in every frame) and the RO gather (every observation's
size check, plus a root walk for each changed one), and does them again on the next round *(code)*. Pre-paint is
incremental, but every element whose `top`/`left` changed needs paint-property and invalidation work (§1.9).

**All same-process frames share one loop.** The loop runs over `unthrottled_frame_views`, every local frame in the
renderer's frame tree. A pump nest in a same-origin `<iframe>` or `<object>` therefore re-runs and re-snapshots the
parent too; each window has its own RO controller and depth limit *(code)*.

### 1.4 Inner loops inside one pass

Inside one `RunStyleAndLayoutLifecyclePhases` (`:2924`) → `UpdateStyleAndLayoutIfNeededRecursive` (`:3526`; this
frame, then plugins, then local child frames) → `UpdateStyleAndLayout` (`:3591`) → `UpdateStyleAndLayoutInternal`
(`:3696`):

```cpp
do {
  frame_->GetDocument()->UpdateStyleAndLayoutTreeForThisDocument();   // style recalc
  ForAllChildLocalFrameViews(...: if (document.IsSVGDocument())
      document.UpdateStyleAndLayoutTreeForThisDocument();)           // :3705-3713
  if (NeedsLayout()) UpdateLayout();                                 // layout (size-container restyles happen in here)
} while (post_style_update_scope.Apply());                           // ::backdrop, top-layer removal only
```

followed by an autosize loop (only with `auto_size_info_`) and a "third pass: if layout hasn't stabilized"
(`if (NeedsLayout())`, `:3658`) *(code)*.

- **Same-process SVG subdocuments.** "Update style for all embedded SVG documents underneath this frame, so that
  intrinsic size computation for any embedded objects has up-to-date information before layout." A same-origin SVG
  `<object>`'s style runs before the parent's layout in every pass, so its natural size reaches the parent in the
  same pass.
  - If the subdocument's style depends on its own viewport (`vw`, `vh`), the parent's layout resizes it.
    `UpdateGeometries` runs after layout, and the child, laid out after the parent in
    `UpdateStyleAndLayoutIfNeededRecursive`, restyles and changes its natural size. That leaves the parent's
    `<object>` needing layout after pre-paint, and the loop of §1.2 runs again (§1.3, last-but-one row).
  - Each such iteration costs the dirty style and layout of both documents, compositing inputs and pre-paint: about
    70–80 µs for two trivial documents (700 iterations in 48–57 ms, measured).
- **Container-query restyles inside layout** (`UpdateStyleAndLayoutTreeForSizeContainer` per size-container
  layout-cache miss; [02-style-engine.md](02-style-engine.md)), anchor `position-try` attempts (up to 6 style
  recalcs per out-of-flow element; [05-layout.md](05-layout.md)) and chained shapings (prior survey) all happen
  inside `UpdateLayout`. They multiply work within a pass, not passes.

### 1.5 The animation clock

- `PageAnimator::ServiceScriptedAnimations` freezes the page clock and every document clock for the frame:
  `Clock().SetAllowedToDynamicallyUpdateTime(false); Clock().UpdateTime(monotonic_animation_start_time)`
  (`page_animator.cc:84-85, 96-99`) *(code)*.
- Each document's time is `zero_time + ClampTimeResolution(frame_time − zero_time)`: 100 µs, or 5 µs when
  cross-origin isolated (`core/timing/time_clamper.h:23-24`) *(code)*.
- The clock is released only in `PostAnimate` when no rAF is pending (`:362-376`). So every style pass of a frame,
  RO-pump passes included, sees **the same time** for time-based animations and transitions *(code)*.
- Scroll-driven animations see the **latest snapshot**: a pass after a snapshot re-run sees a newer timeline value.
  Time-based and scroll-based animations therefore diverge within a frame, and only scroll-based ones can
  "advance" between passes *(code)*.
- `frame_time` is the `frame_time` of the impl frame in progress when cc sent the BeginMainFrame
  (`scheduler.cc:688`, `begin_main_frame_args_`): a vsync tick 0–16.7 ms before the main frame starts. After a
  100 ms frame the next one starts at once, inside some later impl frame. Successive frame times jump by
  vsync-quantized steps (100.0 or 116.7 ms) that track wall time on average *(code; inference for the
  quantization)*.

### 1.6 When the main thread is slow (50–150 ms per BeginMainFrame)

From `cc/scheduler/scheduler_state_machine.cc` (agent-checked line numbers):
- **The impl thread keeps ticking.** `ProactiveBeginFrameWanted()` is true while a BeginMainFrame is in flight
  (`:1210-1222`). Every vsync the compositor runs an impl frame, ticks compositor animations and scroll offsets
  with its own `frame_time`, draws if something changed, and otherwise sends `DidNotProduceFrame(kWaitingOnMain)`.
  viz doesn't throttle it *(code)*.
- **Deadline modes** are NONE, IMMEDIATE, WAIT_FOR_SCROLL, REGULAR, LATE and BLOCKED. A renderer never blocks: the
  base `CheckShouldBlockDeadlineIndefinitely()` returns `!commit_to_active_tree`, i.e. false (`:1412-1414`). With
  nothing to draw and main busy, the mode is LATE (deadline = frame_time + interval). The old "main thread high
  latency mode" (`skip_next_begin_main_frame_to_reduce_latency`) is gone; `main_thread_missed_last_deadline_` only
  feeds tracing (`scheduler.cc:646-652`) *(code)*.
- **When the next BeginMainFrame goes out.** `ShouldSendBeginMainFrame` (`:511-611`) allows one per impl frame, in
  state IDLE or READY_TO_COMMIT (main frame before commit), not while draw-throttled (`kMaxPendingSubmitFrames =
  1`, `:34`), and not between the deadline and the next BeginFrame (`:572-575`). SEND_BEGIN_MAIN_FRAME outranks
  COMMIT in `NextAction`. When main posts ready-to-commit for frame N, the impl thread, which in LATE mode spends
  almost the whole vsync inside the begin frame, posts BeginMainFrame N+1 in the same `ProcessScheduledActions`
  pass as COMMIT N. It doesn't wait for vsync, activation or draw *(code)*.
- **Measured.** A 48,000-element page with one inherited registered property animated at the root (restyling
  everything every frame; `gap/heavy.html`):

  | Flags | BeginMainFrame median | Idle gap between BMFs, median | Gap share of main-thread time |
  |---|---|---|---|
  | (Playwright defaults) | 102.9 ms | 0.1 ms | 0.3% |
  | `--disable-frame-rate-limit` | 97.4 ms | 0.2 ms | 0.3% |
  | `--disable-gpu-vsync` | 110.7 ms | 0.1 ms | 0.1% |
  | `--disable-gpu` | 96.2 ms | 0.2 ms | 0.5% |

  At 12,000 elements (~22–28 ms frames) the gap was still 0.1–0.2 ms, 1.6–2.3% of main-thread time. The
  BeginMainFrame medians differ by load noise (load average 5–7), not by flag *(measured)*.
- **Raster overlaps the next main frame.** COMMIT N → POST_COMMIT → `PrepareTiles` → raster tasks on up to 4
  worker threads (`clamp(nproc/2, 1, 4)`), while main runs BeginMainFrame N+1. Commit N+1 can't happen while
  pending tree N is unactivated (`ShouldCommit`, `:641-651`).
  - **153:** when raster is slower than a main frame, main blocks inside BeginMainFrame N+2 in
    `LayerTreeHost::WaitForCommitCompletion` at `AnimateLayers`. In a trace this looks like main-thread time
    inside `ProxyMain::BeginMainFrame` that is neither style nor layout.
  - **Main** (commit `60cb36196b`, 2026-10-07, `kDeferMainFrameBeforeCommitWithPendingTree`, enabled; not in 155)
    holds BeginMainFrame N+2 back instead, so main idles rather than blocks *(code)*.
- **Headless specifics.** New headless is full Chrome on Ozone headless with SwiftShader for WebGL; viz ticks at 60
  Hz. `--run-all-compositor-stages-before-draw` swaps in `HeadlessSchedulerStateMachine`: deadlines block while a
  main frame or pending tree is in flight, and draw waits for raster (no checkerboard). It doesn't change when
  BeginMainFrames are sent. `--disable-frame-rate-limit` gives back-to-back BeginFrames and turns off draw
  throttling. `--disable-gpu-vsync` changes nothing on Linux's BeginFrame cadence. `--enable-gpu-benchmarking` only
  turns on rendering stats and the JS API. `--enable-begin-frame-control` and `--deterministic-mode` are
  chrome-headless-shell switches *(code)*.

### 1.7 Throttling and skipping

- **Hidden pages.** `WidgetBase::SetHidden` → `LayerTreeHost::SetVisible(false)`. The state machine sends no
  BeginMainFrame while invisible and unsubscribes from BeginFrames (`scheduler_state_machine.cc:486-488,
  1162-1164`), so there is no rAF, no animation ticks and no lifecycle.
  - `--disable-background-timer-throttling` only lifts timer throttling.
  - `--disable-renderer-backgrounding` only changes process priority.
  - `--disable-backgrounding-occluded-windows` maps OCCLUDED to VISIBLE.
  - Playwright passes all three. Headless pages are visible.
  *(code)*
- **Iframe render throttling.** `FrameView::UpdateViewportIntersection` (`core/frame/frame_view.cc:63`, run from
  `RunPostLifecycleSteps`) sets `hidden_for_throttling` = display:none, or zero intersection with the *top-level*
  viewport and non-zero area. There is no margin, and `visibility: hidden` doesn't count.
  `LocalFrameView::CanThrottleRendering` (`local_frame_view.cc:5143-5155`) then throttles only if the frame is also
  cross-origin to the main frame: "We only throttle hidden cross-origin frames". Opaque origins (sandbox without
  allow-same-origin, CSP `sandbox`, data:) count as cross-origin. Display-locked owners (`content-visibility`) and
  throttled ancestors throttle regardless of origin *(code)*.
- **What a throttled frame skips:** the whole lifecycle (`UpdateLifecyclePhases` returns early, `:2446`), rAF,
  animation timing, ResizeObserver, and paint (its painted output is discarded, `:4977`). Its CSS animations don't
  tick and don't request frames. On unthrottling they jump to the current time.
- **OOPIFs.** An offscreen cross-site iframe stays "rendered out of viewport". Its widget stays visible (it still
  gets BeginFrames), but Blink throttles its lifecycle. A display:none OOPIF hides its widget, and BeginFrames stop
  (`content/browser/renderer_host/cross_process_frame_connector.cc:403-435`) *(code)*.
- **Render-blocking.** Subframes start with `lifecycle_updates_throttled_ = !IsMainFrame()` until
  `BeginLifecycleUpdatesIfRenderingReady` (`document.cc:8230`) sees no render-blocking resources. Only fonts time
  out (1.5 s after navigation start, plus 100 ms). XHTML documents begin lifecycle updates once the document element
  exists (`document.cc:1315-1323`). Paint holding (500 ms commit deferral for the outermost main frame) is disabled
  by Playwright's `--disable-features=PaintHolding` *(code)*.
- **Display locks.** `content-visibility: hidden` and non-relevant `auto` skip style, layout, pre-paint and paint
  of the subtree (`core/display_lock/display_lock_context.h:93-148`). Forced updates (`getComputedStyle`, ranges)
  unlock temporarily. `anchor()`/`anchor-size()` don't force: an anchor inside a c-v:auto lock unlocks it through
  `kDescendantIsAnchorTarget`, and a hidden lock stays locked. The relevance observer has a 150% viewport margin,
  `thresholds = {FLT_MIN}`, and post-layout delivery (`display_lock_document_state.cc:110-138`) *(code)*.

### 1.8 Threads, processes, and what crosses between frames

**Off the main thread** *(code unless noted)*:
- The compositor thread: impl-side animations of transform, opacity, filter and backdrop-filter, and scroll-driven
  versions of those; scrolling, including scroll snap during gestures; pinch.
- Raster and image decode, on the raster worker pool.
- Network fetch, through `BackgroundResourceFetch`, enabled.
- **Web font decode and OTS sanitizing.** `FontResource::BackgroundFontProcessor` decodes on a `USER_BLOCKING`
  worker sequence (`core/loader/resource/font_resource.cc:95-110, 201-216`).
- There is no off-thread CSS parsing feature (none in `blink/common/features.cc`), and the HTML parser's threaded
  options (`kThreadedPreloadScanner`, `kThreadedBodyLoader`) are disabled.
- **Main thread only:** style, layout and shaping (HarfBuzz runs inside layout), pre-paint, paint and layerization,
  every lifecycle step above, SVG/SMIL, and ResizeObserver/IntersectionObserver.

**Processes** (desktop Linux, Chrome for Testing 153; content-layer details from gitiles):
- **Site isolation.** `kSitePerProcess` is enabled. Each *site* (scheme + eTLD+1) gets its own renderer; same-site
  cross-origin frames share it. `workers.dev` is itself on the Public Suffix List, so `auberon.workers.dev` is one
  site and all its Workers and previews are same-site *(code; PSL entry checked)*.
- **`Origin-Agent-Cluster: ?1`** on a document gives its origin a separate process, because
  `IsProcessIsolationForOriginAgentClusterEnabled()` follows `UseDedicatedProcessesForAllSites()`
  (`content/public/browser/site_isolation_policy.cc:240-252`). It needs a potentially trustworthy origin and is ignored on
  redirects. Origin-keyed processes *by default* (`kOriginKeyedProcessesByDefault`) are disabled *(code)*.
- **`IsolateSandboxedIframes`** is enabled, with grouping per-origin (`blink/common/features.cc:917-928`). A
  document sandboxed without allow-same-origin goes to one process per (precursor) origin, separate from
  unsandboxed frames. The iframe `sandbox` attribute and the `Content-Security-Policy: sandbox` response header
  both count; `<object>` can only use the header *(code)*.
- Process count is effectively unlimited on desktop (`kRemoveRendererProcessLimit`) *(code)*.
- Measured (renderer processes from CDP `SystemInfo.getProcessInfo`; baseline 3, the page plus two browser-UI
  renderers):

  | Children (SVG `<object>`s) | Extra renderers | OOPIF targets |
  |---|---|---|
  | 1 same-origin | 0 | 0 |
  | 1 same-origin, CSP `sandbox` | +1 | 1 |
  | 3 same-origin, CSP `sandbox` | +1 (shared) | 3 |
  | 3 same-site other-port origins | 0 | 0 |
  | 3 same-site other-port origins, `Origin-Agent-Cluster: ?1` | +3 | 3 |
  | 3 same-site other-port origins, CSP `sandbox` | +3 | 3 |
  | 3 or 4 cross-site (127.0.0.2–5) | +3 / +4 | 3 / 4 |

  css-physics BENCHMARKS §5's "two sandboxed share one process" is the same per-origin grouping: one process for
  both, separate from the parent's.

**Every script-free channel between frames I found:**

| Direction | Channel | Carrier | Granularity |
|---|---|---|---|
| parent → child | content-box size of the `<iframe>`/`<object>` → child viewport (`vw`, `vh`, size media queries) | `RemoteFrame` visual properties | integer px, every parent layout (inference: `gfx::Size`) |
| parent → child | CSS `zoom` of the owner → child `css_zoom_factor` (`remote_frame.cc:1100-1117`) | visual properties | float |
| parent → child | used `color-scheme` of the owner → child's `prefers-color-scheme` (`frame_owner_properties.mojom:39-44`) | owner properties | 1 bit |
| parent → child | viewport intersection: throttling, c-v:auto relevance and lazy loading inside the child | intersection updates | geometry, next frame |
| parent → child | `display: none` of the owner | owner properties | 1 bit |
| **child → parent** | **SVG document's natural size** (outer `<svg>` `width`/`height`, font-relative units) → `<object>`/`<embed>` (any build) or `<iframe style="frame-sizing: …">` (154+) | `IntrinsicSizingInfoChanged` IPC | float32 → LayoutUnit (1/64 px), on every font change |
| child → parent | HTML document's layout-overflow size → `<iframe style="frame-sizing: …">`, opt-in meta | same IPC | at DOMContentLoaded and load only, else `window.requestResize()` |
| child → parent | load failure → `<object>` fallback content | load state | once |

**How the SVG natural-size channel works:**
- `LayoutSVGRoot::StyleDidChange` (`core/layout/svg/layout_svg_root.cc:298-309`) calls `IntrinsicSizingInfoChanged`
  when `StyleChangeAffectsIntrinsicSize`: the writing mode flipped, or the outer `<svg>`'s `width`/`height` are
  font-relative and the font changed (`:258-282`).
- `IntrinsicSizingInfoChanged` (`:285-296`) forwards when `IsEmbeddedThroughFrameContainingSVGDocument()`: the
  owner is remote, or a local `<object>`/`<embed>` (`:111-129`).
- Cross-process: `RemoteFrameOwner::NaturalSizingInfoChanged` (`core/frame/remote_frame_owner.cc:73-85`) sends
  `IntrinsicSizingInfo{size (gfx::SizeF), aspect_ratio, has_width, has_height}` through
  `WebFrameWidgetImpl::IntrinsicSizingInfoChanged` to the browser. The parent's
  `RemoteFrame::IntrinsicSizingInfoOfChildChanged` (`core/frame/remote_frame.cc:776-803`) accepts it for plugin
  owners (`<object>`/`<embed>`) always, and for iframes only with `ResponsiveIframes`. It stores the size on the
  `RemoteFrameView` and marks the owner for layout (`HTMLPlugInElement::NaturalSizingInfoChanged`,
  `html/html_plugin_element.cc:266-270`).
- The natural width is `SVGSVGElement::IntrinsicWidth()` (`core/svg/svg_svg_element.cc:658-670`): the `width`
  attribute resolved by `SVGLengthContext`, so `em` is the root `<svg>`'s computed font-size. Percentages give no
  natural size.

**Probes** (`svgchan/`, Chromium 153):
- **Cross-process round trip.**
  - Parent at `127.0.0.1` animates the `<object>`'s height in steps.
  - Child at `localhost` (an OOPIF target) has `<svg width="1em" height="100%">` with `font-size: calc(50vh + 7px)`.
  - The parent's rAF loop saw width = height/2 + 7 one frame after every height change, every time. The pure-CSS
    reader (`anchor-size(--o width)` → `container-type: inline-size` → `--v: calc(100cqw / 1px)`) agreed *(measured)*.
- **Precision.**
  - `width="1000em"`, `font-size: calc(50vh / 7 + 0.123px)`: expected 714337.2857, got 714337.25.
  - Expected 3694.4286, got 3694.421875.
  - That is float32 then LayoutUnit floor *(measured)*.
  - Font size is clamped to 10,000 px (`kMaximumAllowedFontSize`), so `width="1000em"` reaches 10^7 px.
    LayoutUnit's range ends near 3.3·10^7 px.
- **Same-process `<object>`:** 0 frames, also when read only after the frame, from a `setTimeout` posted in rAF,
  so no script-forced layout helped (the subdocument restyle and re-run of §1.4) *(measured)*.
- **Feedback.**
  - Child `font-size: min(calc(100vw + 1px), 1000px)` on `<svg width="1em" height="100%">`; the `<object>` has
    `width: auto`.
  - Same process: 300 → 1000 px inside one BeginMainFrame. The trace showed 698–700
    `LocalFrameView::RunStyleAndLayoutLifecyclePhases`, 701 `PrePaint`, 1,410 `LocalFrameView::UpdateStyleAndLayout`
    (2 views) and 5–7 `NotifyResizeObservers` in the whole trace.
  - Cross process: +1 px per parent frame (302 → 340 in 40 frames).
  - Unclamped (`calc(100vw + 1px)`), the same process reached the 10,000 px font-size clamp before the first rAF,
    with load taking 2 s longer.
  - Oscillating (`calc(100vw + 1px - 2 * mod(100vw, 2px))`): no frame within 8 s *(measured)*.
- **CSP-sandboxed same-origin `<object>`:** separate process, channel works (75 of 80 frames exact; the other 5 are
  the one-frame lag at each step) *(measured)*.
- **`<iframe>` (cross-site, sandboxed or CSP-sandboxed) in 153:** OOPIF, but no channel: `frame-sizing` is
  unsupported in 153 (`CSS.supports` false). That is expected from the code (experimental flag) *(measured)*.
- **Full chain inside the child.**
  - An SVG child with an XHTML scroller in `<foreignObject>`, a stepped view-timeline subject, `timeline-scope`
    on the root `<svg>`, `@keyframes` into a registered `--v`, and `font-size: calc(10px + var(--v) * 1px)`.
  - The parent saw 760.25, 510.5, 260.75, 11 as the subject stepped *(measured)*.
  - So layout-state readback and the upward channel compose. A whole CSS machine can live in an SVG document's
    `<foreignObject>` and report through its root.

**What the channel can carry, per child document per frame:**
- Up: the natural width, plus the natural height if a second font-relative unit (`ch`, `ex`, `cap`, `ic`) is
  driven independently, e.g. a variable font whose "0" advance follows an axis. Caveat: with both natural
  dimensions and no CSS size on the owner, the size is the natural size, so the owner's size can't also carry the
  down channel. With a natural ratio and a CSS height, the parent gets only the ratio.
- Down: the owner's height (and/or width), integer px; zoom; 1 bit of color scheme.
- Latency: 1 frame at 60 fps with light pages *(measured)*. With 100 ms frames on both sides, expect 1–3 parent
  frames, because each side only sees the other's latest value at its next style pass *(inference)*.

### 1.9 Costs outside style and layout

**Pre-paint** (`core/paint/pre_paint_tree_walk.cc`):
- The walk descends only into objects with `NeedsPaintPropertyUpdate`, `ShouldCheckForPaintInvalidation`,
  `ShouldCheckLayoutForPaintInvalidation`, a descendant flag, or a forced subtree walk (`:412-452, 1505-1512`).
- Every object laid out in the pass sets `ShouldCheckForPaintInvalidation` on itself and the descendant flags on
  every ancestor (`layout_object.cc:5384-5408`). So the walk costs ∝ objects laid out or moved, plus their ancestor
  chains: a dirty leaf at the bottom of a 1,561-level chain re-walks the chain *(code; inference for the chain
  cost)*.
- A box whose paint offset changed forces its whole subtree to be re-walked, down to the next isolation (paint
  containment, or style plus layout containment; `paint_property_tree_builder.cc:576-595, 4271-4287`). Each
  descendant whose offset changed repaints its painting layer.
- A `PaintOffsetTranslation` (from a transform, `will-change`, isolation, a scroller…) keeps descendants' offsets
  fixed, so only that one node changes *(code)*.
- Pre-paint runs once per lifecycle iteration that reaches it: every RO, IO or "still needs layout" round, but not
  snapshot re-runs (§1.3).

**Paint and layerization:**
- Paint runs only if the root layer `SelfOrDescendantNeedsRepaint` (`local_frame_view.cc:3324-3327`).
- Stacked layers (positioned or stacking contexts) with a cached subsequence are copied wholesale
  (`paint_layer_painter.cc:416-426`). Inside a repainting layer, clean display items are reused
  (`paint_controller.cc:227-266`).
- Layerization (`PaintArtifactCompositor::Update`, `Layerize` / `Blink.CompositingCommit.UpdateTime`) is a full
  update whenever the chunk count changes, or a chunk's bounds, identity or foreign layer changes
  (`paint_artifact_compositor.cc:525-570, 652-676`); otherwise it takes the repaint fast path. A moved positioned
  element changes some chunk's bounds, so pages that move elements every frame pay a full layerization every frame
  *(code; inference for "every frame")*.
- **Any raster invalidation in a cc layer re-converts all of that layer's chunks**
  (`content_layer_client_impl.cc:229-245` drops the cached `cc::DisplayItemList`; `PaintChunksToCcLayer::ConvertInto`
  then rebuilds it). The cost is ∝ items in the layer, not the dirty area.
  - This is ENGINE_NOTES 36's mechanism. `will-change: transform` on the static pane gives it its own transform
    node, `PaintOffsetTranslation` and stacking context, so a cached subsequence and its own cc layer. The root
    layer's per-pass invalidations then stop re-converting the pane's items *(code; inference that this is the
    ~7 ms)*.
  - Confirm with `chrome.gpuBenchmarking.runMicroBenchmark("rasterize_and_record_benchmark")`'s
    `raster_invalidation_and_convert_time_ms`, or CDP `LayerTree.layerPainted` (§1.10).

**Big scrollers:**
- A composited, user-scrollable scroller is painted over its visible rect plus 4,000 px
  (`kCullRectPixelDistanceToExpand`, `blink/common/features.cc:626-651`; halved per axis when it scrolls both
  ways). It is re-culled after 512 px of scroll.
- cc rasters only within 1,000 screen px of the viewport (`max_preraster_distance`) and keeps tiles to 3,000 px.
- An `overflow: hidden` scroller, which isn't user-scrollable, is never auto-composited and is culled to its
  visible clip. Its content lives in the parent's cc layer, usually the root's (`paint_artifact_compositor.cc:297-345`).
- So the 10^6 px registers cost nothing to raster far away, but a register scroller that is `overflow: hidden` puts
  its moving subjects in the root layer. That makes it a root-layer invalidation source *(code; inference for the
  last step)*.

**Hit testing:**
- None per frame unless the mouse position is known. Every layout marks hover dirty (`local_frame_view.cc:2006`),
  and the next BeginMainFrame then runs `RecomputeMouseHoverStateIfNeeded` → a synthetic mousemove → `HitTest`, an
  `UpdateAllLifecyclePhasesExceptPaint` (`layout_view.cc:122-139`).
- The hit-test cache is cleared by every style update (`document.cc:2854`). A harness that clicked or moved the
  mouse once pays a real hit test per frame with layout, and the `:hover` restyles it causes *(code)*.

**Accessibility:**
- There is no `AXObjectCache` unless an AXContext exists: an assistive technology, `--force-renderer-accessibility`,
  any CDP `Accessibility.*` call (a persistent complete-mode context), DevTools inspect overlays, or
  `element.computedRole`/`computedName`.
- Creating the cache forces a full-document style recalc (`document.cc:3626-3636`). Without a cache,
  `RunAccessibilitySteps` returns at once *(code)*. Headless Playwright has no AT.

**Compositor animations:**
- Compositable properties are transform, translate, rotate, scale, opacity, filter and backdrop-filter, plus
  background-color and clip-path through native paint worklets (`core/animation/compositor_animations.cc:78-83`).
- The paint-worklet ones only work on document timelines. A scroll-driven animation composites only if its source
  is user-scrollable with a scroll node, so `overflow: hidden` sources can't.
- Custom properties never composite (no paint worklet) *(code)*. Every registered-property readback in both
  projects runs on the main thread.

### 1.10 Profiling toolkit

**Per-phase slices that are always there** with `blink` and `devtools.timeline`:
- `ProxyMain::BeginMainFrame` (cc) contains:
  - `WebFrameWidgetImpl::BeginMainFrame` (Animate)
  - `UpdateLayoutTree` (end arg `elementCount`)
  - `Document::updateStyle` (blink, blink_style)
  - `Layout` / `LocalFrameView::layout`
  - `PrePaint`, wrapping `RunCompositingInputsLifecyclePhase` and `RunPrePaintLifecyclePhase`
  - `LocalFrameView::RunPaintLifecyclePhase`
  - `Layerize`
  - `Commit` (disabled-by-default-devtools.timeline)
- `Commit` spans cc `UpdateLayers` to the end of the main-frame task, after Blink paint and layerization. "Between
  `Commit`s" is exactly one main frame, and passprof's cut is right *(code)*.
- `LocalFrameMetricsAggregator` (formerly LocalFrameUkmAggregator) emits a `blink` slice per phase timer:
  `Blink.Style.UpdateTime`, `Blink.Layout.UpdateTime`, `Blink.CompositingInputs.UpdateTime`,
  `Blink.PrePaint.UpdateTime`, `Blink.Paint.UpdateTime`, `Blink.CompositingCommit.UpdateTime` (that is
  layerization, not cc commit), `Blink.Accessibility.UpdateTime` and `Blink.Animate.UpdateTime`
  (`core/frame/local_frame_metrics_aggregator.cc:57-87`).
  - **Size-container restyles inside layout have no slice of their own** and count under
    `Blink.Layout.UpdateTime`. Only `StyleResolver::ResolveStyle` instants
    (disabled-by-default-devtools.timeline.invalidationTracking) reveal them *(code)*.

**Style counters.** `Document::updateStyle`'s end args under `blink_style` (`document.cc:2899-2924`,
`style_resolver_stats.cc:59-79`): matchedPropertyApply, matchedPropertyCacheHit/Added, rulesRejected,
rulesFastRejected, rulesMatched, stylesChanged/Unchanged/Animated, elementsStyled, baseStylesUsed,
independentInheritedStylesPropagated, customPropertiesApplied. The harness's `frames` preset already enables
`blink_style`. These are the cheapest way to see MPC hit rates and rule rejections per pass. They cover document
recalc only, not recalc inside layout *(code)*.

**Attributing every lifecycle iteration to its trigger** (code-backed recipe for ENGINE_NOTES 38). On the main
thread, within one `ProxyMain::BeginMainFrame`, each `LocalFrameView::RunStyleAndLayoutLifecyclePhases`
(blink,benchmark) is one iteration of the loop in §1.2. Classify each iteration by what follows it before the next
one:

| Sequence | Trigger of the next iteration |
|---|---|
| no `PrePaint` in between | post-layout snapshot changed (first, or re-armed) |
| `PrePaint`, no `LocalFrameView::NotifyResizeObservers` | post-layout IO (c-v:auto first observation) or a frame still needing layout |
| `PrePaint`, `NotifyResizeObservers` | ResizeObserver delivery (internal ones included), loop-limit error, or anchor fallback, all of which re-arm the snapshot |

Window `error` events with "ResizeObserver loop completed with undelivered notifications" count loop-limit rounds;
the harness can listen for them. `StyleRecalcInvalidationTracking` reasons ("ScrollTimeline", "Animation") name
what each re-run restyled.

**Other categories and tools** *(code)*:
- `disabled-by-default-devtools.timeline.invalidationTracking`:
  - `ScheduleStyleInvalidationTracking`, `StyleInvalidatorInvalidationTracking` (with the selectors behind each
    invalidation set) and `StyleRecalcInvalidationTracking`.
  - `LayoutInvalidationTracking`, but only from `SetNeedsLayout`: an abs-pos `top`/`left` move goes through
    positioned and simplified layout and **emits nothing**, so css-physics register moves are invisible to it.
  - Per-element `StyleResolver::ResolveStyle`. It inflates style time ∝ elements styled; A/B before trusting
    absolute numbers.
- `disabled-by-default-blink.debug`: `SelectorStats`. A per-selector timer with match attempts, fast rejects and
  matches, dumped after each `UpdateLayoutTree`; heavy. Recalcs inside layout accumulate into the next dump.
- `disabled-by-default-blink.invalidation`: per-object paint invalidation reasons, raster invalidation tracking.
- `disabled-by-default-devtools.timeline.frame`: BeginFrame, RequestMainThreadFrame, ActivateLayerTree,
  DrawFrame and DroppedFrame on the impl side.
- `cc` plus `disabled-by-default-devtools.timeline`: `RasterTask` on worker threads; `TileManager::PrepareTiles`.
- Observer costs of the harness's own presets:
  - `devtools.timeline` makes every layout walk the whole layout tree (`Layout` beginData).
  - `DOMStats` walks the DOM whenever its version changed.
  - `invalidationTracking` assigns node ids and rebuilds the selector map.
- CDP `Performance.getMetrics`: RecalcStyleCount counts **every** `probe::RecalculateStyle`, size-container recalcs
  inside layout included (`style_engine.cc:4032-4034`). RecalcStyleCount per frame − 1 ≈ in-layout container
  recalcs. LayoutCount counts the outer layouts only.
- CDP `CSS.startRuleUsageTracking` / `takeCoverageDelta`: dead rules, e.g. `@container style()` branches that never
  match. It forces one full recalc when started.
- CDP `LayerTree.enable`: `layerPainted` per cc layer per commit (which layer re-records), compositing reasons.
- `--enable-gpu-benchmarking` → `chrome.gpuBenchmarking.runMicroBenchmark("rasterize_and_record_benchmark")`:
  record time with and without caching, `raster_invalidation_and_convert_time_ms`, layerization time, rasterize
  time. Run it from the harness via `Runtime.evaluate`; the page stays script-free.
- `--enable-blink-features=InfiniteCullRect` (turn culling off to price it), `BlinkRuntimeCallStats`; `--disable-
  blink-features=RasterInducingScroll`.
- `--enable-logging --vmodule`: nearly useless in release builds (the paint dumps are DCHECK-only).

---

## 2. What it means for the projects

### 2.1 Passes per frame: what more of them buys

- **Throughput.** Main-thread time is a sequence of back-to-back BeginMainFrames (measured gap < 0.5% at 100 ms
  frames, §1.6). More passes per frame don't add main-thread time; they reshuffle it. Per frame, the fixed work is
  Animate, paint, layerization, commit, post-lifecycle steps and, with a mouse, a hit test. css-physics at 48 bodies
  measured 0.37 ms layout and 0.47 ms paint per frame against 2 × 48.8 ms of style (BENCHMARKS, "Live 48"). So at
  heavy loads a pump changes steps per *frame* (fewer drawn frames, same steps per second), not steps per second.
  It pays where per-frame costs are large: js-minus-js's root re-recording before `will-change` (ENGINE_NOTES 36,
  ~7 ms), layerization, pre-paint of a big tree *(inference)*.
- **Light pages are the exception.** Below 16.7 ms per frame, the main thread idles until the next vsync. There
  the pump converts idle time into steps. css-physics's 32-body runs sit at 16.1–18.8 ms frames (BENCHMARKS), so no
  slack. 16-body or mostly-asleep scenes have slack, and D = 1–2 pump levels would turn it into 1–2 more steps per
  vsync *(inference from §1.6 + prior survey)*.
- **Latency of in-layout channels** is the other real gain. Remembered sizes refresh per pass inside a pump (prior
  survey finding 2), the transition latch works per pass ([04-animations-and-scroll.md](04-animations-and-scroll.md)
  §1.3, measured; the frozen clock doesn't matter to a 0 s transition), and readback scans are frame-locked only by
  their own counter. All of these get faster with more passes per frame, independent of throughput.
- **What an extra pass costs.** A snapshot re-run is style+layout only. An RO re-run adds compositing inputs,
  pre-paint, the post-layout IntersectionObserver computation and the RO gather (§1.3). The gather walks
  root-ward once per changed observation: O(depth) each, so deep chains with many observed elements pay
  O(observed × depth) per round *(code)*. Keep pump elements few, shallow-to-deep in a small subtree, away from
  the big chains.
- **Make the pump's last level deliver, never skip.** A level that changes again after a deeper one delivered is
  skipped. Then: one ErrorEvent per frame, one more round, and `ScheduleAnimation()`, so the page never idles
  (measured: 60 error events/s on `nest8` and `sib4`). For js-minus-js, two issues writing RAM leaves at the same
  depth in one frame hit this path *(inference)*.

### 2.2 The ENGINE_NOTES on passes, explained from the code

- **14** ("view-timeline registers update every layout pass; remembered sizes once per frame"). Timelines refresh
  at every snapshot: frame start, and after pass 1 (and after each re-arm). Remembered sizes are recorded only in
  the RO step, which runs once per loop round that reaches it, normally once per frame. A pump makes it once per
  round *(code)*.
- **15** ("re-runs while view timelines are stale; later passes already show next frame's counter").
  - At frame start, `ServiceScrollAnimations` snapshots timelines against the previous frame's final layout
    (`local_frame_view.cc:4063-4066`).
  - Pass 1 moves the subjects; the post-layout snapshot sees the move and re-runs.
  - Pass 2 therefore computes from values pass 1 produced. A counter advanced through a timeline advances twice in
    one frame. The freshness flag is the right fix.
  - This is specified behaviour: scroll-animations-1 §5.1 asks for a re-run while timelines are stale *(code,
    docs)*.
- **16** ("when nothing changes, Blink stops re-running").
  - Every re-run condition is a *change*: snapshot state differs (`TimelineState::operator==`,
    `scroll_snapshot_timeline.h:183`), an RO size differs, layout is dirty.
  - Between frames, `ScrollSnapshotTimeline::ShouldScheduleNextService` requests a new frame only if the current
    time differs from the last (`:164-176`).
  - Saturated counters make both false: the frame stops after pass 1 and no new frame is requested *(code)*.
- **18** (time-driven scan skips columns on slow frames). The clock is the vsync-quantized frame time, frozen per
  frame. A 100 ms frame advances time-based animations by ~100 ms at once *(code)*.
- **37** ("more than two issues per frame run on stale state; limit not found").
  - Blink has no limit of two. Passes are 1 + one snapshot re-run + RO rounds (+ an error round from 156).
  - On the full page, the third pass exists because the RAM leaves (unlocked for a write, so observed by the
    intrinsic-size RO) deliver after pass 2. That re-arms the snapshot, which sees `#cpu`'s timelines moved by
    pass 2.
  - A third issue in pass 3 sees a fresh snapshot. The prior survey found the failures were the write-channel cap
    `CH = 'ABCD'[:2K]`, and the code agrees: nothing else stops a third issue *(code + prior measurement)*.
- **38** ("Blink doesn't always run the settle pass").
  - The settle pass needs a re-arm, i.e. an RO delivery (or an error round) after pass 2.
  - The full page writes RAM leaves every frame, so it always gets one. The CPU-only page has no RAM writes, so it
    only gets one when some other `contain-intrinsic-size: auto` element changes size, hence "mostly 2".
  - "The trigger is `#cpu`'s ScrollTimeline style invalidation after the second shaping" is the re-armed snapshot
    seeing pass 2's layout, as the code predicts.
  - Unexplained by the code: 1,536 extra view-timeline animations removing the third pass. More snapshot clients
    can't suppress a re-arm, and the RO step doesn't look at timelines.
  - Run the §1.10 classification on both traces. If the CPU-only page's occasional third pass is preceded by
    `NotifyResizeObservers`, find which observed element changed in the variant without the extra animations
    *(code; the 1,536 effect is an open question)*.

### 2.3 Multicore: the dead end isn't dead

css-physics HISTORY ("Iframes for parallelism: … the only script-free channel between frames is the iframe's size,
parent to child. A single-origin artifact can't use it."), BENCHMARKS §5 and ENGINE_NOTES 32 are contradicted on
both counts:

- **Child → parent exists.** An SVG document's natural size (§1.8), measured in 153: script-free, cross-process,
  1 frame round trip, 24-bit precision.
- **One origin gets 2 processes** (CSP `sandbox` on the children). **K origins get K + 1** with
  `Origin-Agent-Cluster: ?1`, each a `_headers` rule. On `auberon.workers.dev`, separate Workers are separate
  origins of the same site, so OAC splits them.
- **The child can host a whole CSS machine.** XHTML inside `<foreignObject>`, view-timeline readback, registered
  properties; the measured chain ran inside an SVG document and reported through the root's `font-size`.
- **Constraints:**
  - About 1 value down and 1–2 up per child document per frame.
  - 1–3 frames of latency under load.
  - The child must keep ≥ 1 px in the viewport, or it is throttled (cross-origin rule, §1.7).
  - Each child parses its own stylesheet.
  - Each child renders itself: an OOPIF is a flat composited surface in the parent, and 3D (`preserve-3d`) doesn't
    cross the frame boundary.
- **Fit.**
  - css-physics: K independent islands (rooms, tanks) in K processes cut the N² pair work to K·(N/K)² *and* run
    the K parts in parallel. At 48 bodies (~9 fps today), two 24-body islands would each do about a quarter of the
    pair work, on separate cores *(inference)*. Cross-island coupling has to fit through a few numbers per frame.
  - js-minus-js: no natural split (compile then run). K independent programs, or a "multicore" CPU with a 1-word
    interconnect, are possible but low value.
  - paint: no use.

### 2.4 The in-frame fixpoint loop (same-process SVG objects)

- **What it is.** §1.4's feedback is a script-free, unbounded "repeat the lifecycle until it stops changing", with
  a 70–80 µs floor per iteration *(measured)*. Every iteration re-runs whatever style and layout are dirty in every
  same-process frame. Size-container readers (`cqw`), `anchor-size()`, grid placement and natural sizes refresh
  every iteration. View timelines, remembered sizes, transitions and animations don't: there is no snapshot or RO
  step until the loop converges.
- **A register machine without the depth rule** *(inference from code + the 700-iteration probe)*:
  - An `<object>` whose child echoes its viewport height as its natural width is a D flip-flop clocked by
    iterations.
  - Size containers that read object A (`anchor-size(--A width)` → `cqw`) and size object B's height are the
    combinational logic.
  - The machine iterates until no register changes. To yield a frame, gate progress on a cycle counter compared
    with a time-derived budget: time is frozen per frame and advances between frames.
- **js-minus-js** uses size-container readers already. Moving its *per-cycle* state from view-timeline registers to
  object registers would remove both the 2-pass limit and the pump's depth rule. Big redesign; untested beyond the
  toy.
- **css-physics's** state is view-timeline readback, which this loop doesn't refresh.
- **Hazard.** A non-converging loop hangs the tab (§5). Clamp every register.

### 2.5 Measurement in the harnesses

- **Rates.** rAF/s ≈ BeginMainFrames/s ≈ Commits/s for pages that change every frame. They aren't quantized to
  vsync (§1.6). `countFrames` (rAF count over `performance.now()`) is a sound frame rate. rAF *timestamps* are
  vsync-quantized; use wall time for throughput.
- **Flags.** `--disable-frame-rate-limit` / `--disable-gpu-vsync` change nothing for 50–150 ms frames (measured).
  For light pages they remove vsync waits, so they'd measure "work per second" rather than what a user sees.
  `--run-all-compositor-stages-before-draw` only makes impl draws wait for raster.
- **153-specific trace artifact.** With slow raster (software, `--disable-gpu`), a `LayerTreeHost::WaitForCommitCompletion`
  inside the next `ProxyMain::BeginMainFrame` is main-thread time that is neither style nor layout. Look for it
  before attributing a frame's remainder *(code)*.
- **Observer effects.** The `devtools.timeline` category adds a layout-tree walk per layout. `invalidationTracking`
  adds per-element work. Compare a traced run's frame rate with an untraced `countFrames` before quoting per-pass
  milliseconds from traces *(code; size unmeasured)*.
- **Hover.** A harness that moved the mouse adds a hit-test lifecycle per frame (§1.9). Use `HOVER=1` only when
  measuring hover.

### 2.6 Throttling facts per project

- **paint.**
  - Same-origin `<object>` cells are never render-throttled offscreen. They run their lifecycle whenever dirty;
    idle cells cost nothing.
  - `content-visibility: hidden` on a cell's ancestor does throttle them, same-origin or not. That is an option for
    off-canvas cells that must stay loaded *(code)*.
  - Cells loaded from data: URLs or with a CSP sandbox would be opaque-origin: throttled offscreen and, if
    sandboxed, in another process *(code)*.
- **css-physics and js-minus-js** are main-frame documents and are never throttled while visible. A hidden tab gets
  no BeginMainFrames at all, whatever the Playwright flags.

---

## 3. What's changing (153 → 155 → main)

| Item | 153 | 155 (stable) | main (158) | Effect here |
|---|---|---|---|---|
| `ResponsiveIframes` (`frame-sizing`, `responsive-embedded-sizing` meta, `window.requestResize()`) | experimental | **stable** (shipped M154, chromestatus 5108373464547328) | stable | `<iframe>` gets the SVG natural-size channel; HTML children report at DCL/load only |
| Lifecycle loop (`UpdateLifecyclePhasesInternal`) | — | — | adds ContainerQueryList steps (`ElementMatchContainer`, status test) | none without script; otherwise identical |
| `NotifyResizeObservers` loop-limit round (`0728ae248a`, 2026-09-23) | no re-run once pre-paint is clean | same as 153 | re-runs once per frame when observations were skipped (156+) | one more pass per frame for pumps whose last round skips, and for same-depth RAM writes (09 §2.3) |
| `kDeferMainFrameBeforeCommitWithPendingTree` (cc, `60cb36196b`, 2026-10-07) | — | — | enabled | main idles instead of blocking in `WaitForCommitCompletion` when raster lags |
| `StaleIntersectionGeometryForThrottledFrames` | absent | absent | stable | throttled frames report "not intersecting" instead of geometry |
| `AvoidEmbeddedContentViewLocation` (frame rects propagated after the loop) | stable | test (killswitch off) | stable | timing of child-frame size propagation; the down channel |
| `RasterInducingScroll` | stable on Linux/Windows | — | stable everywhere | non-composited scrollers scroll on the compositor by re-rastering |
| `SkipPaintInvalidationWhileStayingInvisible` | absent | absent | stable | paint-only changes on `visibility: hidden` objects skip invalidation |
| `SkipTickingStaticAnimations` | absent | absent | stable | animations whose values can't change aren't ticked on main |
| `PrePaintBoxInvalidatorUsesFragments`, `ClearDisplayLockPrePaintFlags` (155), `UsePaintGeometryForIntersection` (155) | absent | partly | stable | pre-paint and IO internals |
| `CompositeBGColorAnimation` | stable | stable | removed (always on) | — |
| `PageAnimator` step 11 | all controllers | — | active controllers only; rAF legacy time from the clamped timeline | refactor, same behaviour |
| `ScrollSnapshotTimeline::BlockSnapshotUpdate` | absent | — | present | timelines pause while a form control shows an autofill preview |

Unchanged 153 → main:
- the one-shot snapshot and its RO re-arm;
- `RunSnapshotPostLayoutStateSteps` stable, `SnapshotScrollTimelinesPostLayout` off;
- the RO depth rule; the display-lock IO parameters;
- `IsolateSandboxedIframes` per-origin; site isolation; non-blocking commit; main frame before
  commit/activation; the 60 Hz BeginFrame source in new headless.

Work in progress visible in code:
- `ContainerQueryListController` ("The spec PR has no termination rule … limit them to at most once per lifecycle
  update", crbug.com/40887402).
- TODO crbug.com/1329159 in `RunSnapshotPostLayoutStateSteps` ("Determine if the source for a view timeline has
  changed").
- The anchor remembered-scroll-offset TODO (`out_of_flow_data.cc:45-49`).

---

## 4. Ideas, ranked by expected value × confidence

1. **Parallel islands for css-physics through process-isolated SVG children** *(code-backed + measured
   primitives)*.
   - Each island is an SVG document (scene in `<foreignObject>`) in an `<object>`, served from its own origin with
     `Origin-Agent-Cluster: ?1`. Or use one origin plus CSP `sandbox` for exactly one extra process.
   - Each island renders itself. Optional coupling: per-frame scalars up through `font-size` → `width="1000em"`,
     and down through the `<object>`'s height.
   - Cheapest experiment: two 24-body islands from 127.0.0.1:A and :B with OAC headers. Compare each island's
     passes/s and the parent's frame rate against one 48-body page (BENCHMARKS "Live 48": 9 fps). Keep both
     islands ≥ 1 px on screen.
   - Kill criterion: the islands' combined steps/s isn't ≥ 1.5× the single page.
2. **Attribute every pass** with the §1.10 classification *(code-backed)*. Cheap: one trace each of js-minus-js's
   CPU-only and full pages, plus a window `error` listener in the harness. It settles ENGINE_NOTES 38 and tells
   whether the RO error path fires on the full page (§2.1).
3. **Use the pump only where frames are light** *(code-backed)*. css-physics at ≤ 32 bodies: a D = 1–2 nest of
   `contain-intrinsic-size: auto` elements whose size follows the step counter, built deepest-changes-last so it
   never skips. Measure steps per second, not fps, against today's.
4. **The in-frame fixpoint loop as a clock** *(code-backed mechanism, measured toy; application speculation)*.
   - Prototype a 2-register counter. Object A's natural width = its viewport height; a container reads A and
     sets B's height to A + 1.
   - Measure iterations per frame and µs per iteration as the parent grows (100, 1,000 elements dirty per
     iteration).
   - If the per-iteration floor stays ~0.1 ms, a js-minus-js CPU cycle in this form would beat 2–3 shapings per
     frame by orders of magnitude in cycle count, provided the cycle logic can be size-container-only.
5. **Isolated cascades as subroutines** *(speculation)*.
   - A same-origin SVG subdocument has its own stylesheet, `@property` registry and MPC. Its style runs before the
     parent's layout every pass, and its result (natural size) is visible in the same pass.
   - ENGINE_NOTES 4 says every registered property costs on every animated element. Moving a block of
     computation with many private properties into a subdocument would keep them off the main document's
     elements.
   - Experiment: move one js-minus-js service (e.g. PRINT decoding) into an SVG `<object>` and compare per-pass
     style time.
6. **Root-layer hygiene** *(code-backed)*.
   - Any raster invalidation in a cc layer re-converts all of that layer's items (§1.9).
   - Give every large static region its own layer (`will-change: transform`). Give the moving registers'
     scroller(s) one too: `overflow: hidden` scrollers aren't composited, so their subject moves land in the root
     layer.
   - Measure with `rasterize_and_record_benchmark`'s `raster_invalidation_and_convert_time_ms` and
     `LayerTree.layerPainted` before and after.
7. **Trace hygiene** *(code-backed)*. Report per-pass ms from traces only after an A/B of `devtools.timeline` vs
   untraced `countFrames`. Add `blink_style`'s `Document::updateStyle` counters (MPC hits, rules rejected,
   customPropertiesApplied) to `passprof.py`. They are free when `blink` is traced and turn "style is slow" into
   "N custom properties applied per pass".
8. **Don't**:
   - uncap the frame rate (measured: no idle to recover);
   - expect anchor-fallback flipping to add passes (code: it doesn't);
   - rely on `--run-all-compositor-stages-before-draw` (no effect on main-frame timing).

---

## 5. Possible bugs and open questions

**Possible bugs** (not filed; MREs could be derived from the probe files):

1. **Unbounded lifecycle loop: a script-free same-process page hangs its renderer.**
   - Page: `<object data="osc.svg" style="display:block;height:20px">`, with `osc.svg` = `<svg width="1em"
     height="100%">` and `svg { font-size: calc(100vw + 1px - 2 * mod(100vw, 2px)) }`.
   - Result: no animation frame within 8 s (Chromium 153); the converging variant ran 700 lifecycle iterations in
     one frame.
   - Cause: `RunPostLayoutIntersectionObserverSteps` re-runs the loop whenever any frame view `NeedsLayout()` after
     pre-paint (`local_frame_view.cc:1686-1689`). Same-process SVG subdocuments resize after the parent's layout
     and re-dirty it through `HTMLPlugInElement::NaturalSizingInfoChanged`. ResizeObserver has a depth rule for
     exactly this class of feedback; this path has none.
   - Impact: self-DoS for same-origin content. On platforms without full site isolation (Android below its memory
     threshold), a cross-site SVG in an `<object>` is same-process, so a third party could hang the embedder
     *(inference)*.
   - Spec: HTML's "update the rendering" has no such re-run step for natural sizes. Embedded-content natural sizes
     would normally take effect at the next rendering update *(docs, inference)*.
2. **Outer `<svg>` `width`/`height` with `calc()` containing font-relative units don't notify the embedding
   `<object>` when the font changes.**
   - `LayoutSVGRoot::IntrinsicSizeIsFontMetricsDependent` uses `SVGLength::IsFontRelative`, which only recognizes
     numeric literals (`core/svg/svg_length.h:106-111`, "TODO(crbug.com/979895) … might have revealed an existing
     bug with calculated lengths").
   - Measured with `width="calc(1em + 0px)"`: the same-process `<object>` stayed at its first width; the
     cross-process one matched in 15 of 80 frames.
   - Inline `<svg>` in HTML updates correctly (its own relayout re-resolves).
3. **UA-internal ResizeObserver skips fire author-visible errors.**
   - The intrinsic-size observer behind `contain-intrinsic-size: auto` shares the controller with author
     observers. When it has skipped observations, Blink dispatches "ResizeObserver loop completed with undelivered
     notifications" on `window` and schedules another frame (`local_frame_view.cc:2347-2367`).
   - Measured: 60 error events per second on script-free pages (`nest8`, `sib4` of the prior survey).
   - The RO spec's error concerns author observers. css-sizing-4 records last remembered sizes "at the time
     ResizeObserver events are determined and delivered", but says nothing about reporting errors for them. Low
     impact, but it keeps such pages from ever idling.

**Open questions:**
- Why 1,536 extra view-timeline animations removed js-minus-js's occasional third pass (ENGINE_NOTES 38): needs the
  §1.10 classification on both variants.
- The cross-process channel's latency when both sides run 100 ms frames: 1, 2 or 3 parent frames? Not measured
  here (machine shared).
- Whether `<foreignObject>` content inside an SVG document supports everything css-physics uses: preserve-3d
  rendering, touch scrolling, scroll snap. View timelines and registered properties work (measured).
- The real cost of the `devtools.timeline` layout-tree walk on js-minus-js's page (likely ~1 ms per layout at
  50k objects; unmeasured).
- Whether `ch`/`cap` driven by a variable-font axis gives an independent second up-channel value (natural height)
  without the natural-ratio coupling.
