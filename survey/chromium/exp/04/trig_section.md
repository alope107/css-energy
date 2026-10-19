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
- The spec has moved to animation-triggers-1 (ED 2026-10-16). Its CSS event trigger (`event-trigger: --n click()`,
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
