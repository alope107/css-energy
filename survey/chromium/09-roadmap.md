# 09 — Roadmap: shipped since 153, in the pipeline, proposed

*Chromium 153 (`refs/branch-heads/8010`) → 155 (8059, stable) → 157 (8103, beta) → main `22b3b159` (158), read
2026-10-18. Sources: `runtime_enabled_features.json5` and `features.cc` diffed across the four versions (parsed, not
eyeballed: `exp/09/scripts/{json5,diffref,featdiff,featdiff2}.py`), the GitHub mirror's commit log for the flag
file and the style/animation/frame directories since 2026-08-01, Gerrit, chromestatus (1,100 entries pulled),
chromiumdash, w3c/csswg-drafts issues (~600 updated in 2026), drafts.csswg.org, wpt.fyi (experimental and stable runs
of 2026-10-18), MDN browser-compat-data 8.1.6, Interop 2026. Experiments: headless Chromium 153.0.8010.12 with
`--enable-blink-features=…`, scripts in `exp/09/exp/`. Internals are covered by chapters 01–08; this chapter
links to them by file name.*

Labels: *(code)* read in the source, *(measured)* run here, *(docs)* spec/chromestatus/blog/WPT, *(inference)*.

---

## 0. The 15 changes that matter most

Milestone dates come from chromiumdash (§1.1). "Est." = my estimate where nothing is scheduled.

| # | Change | Where it stands | Est. | Who | What it would change |
|---|---|---|---|---|---|
| 1 | **Dynamic names: `ident()` as an arbitrary substitution function, so `var(ident("--m" var(--k)))` and `var(var(--n))` work** | CSSWG resolved 2026-08-06 (csswg#14213), WPT `ident-function-substitution.html`; Safari TP 254 passes all 46 `ident-*` tests; Blink: `CSSIdentFunction` **test**, old parse-time model; no CL in Gerrit | ≥ 2027 | both | Dynamic indexing: reading a property chosen by a computed index in one substitution. In 153 behind the flag, `ident()` already works in name-valued properties (`anchor-name`, `container-name`, `view-timeline-name`) with `var()` inside, but not as `var()`'s name, and `anchor-size(ident(…))` crashes the renderer (§2.1) |
| 2 | **`inherit()`**: the parent's computed value of a custom property, inherited or not | `CSSInheritFunction` **experimental** since ≤ 153; I2P only; WPT: Chrome-exp 17/17, Safari TP 17/17, Firefox 2/17 | 2027 | both | A child reads its parent's *non-inherited* register in one step, so chain state can stop flooding subtrees (§2.2). Works in 153 behind the flag *(measured)* |
| 3 | **ResizeObserver loop-limit round now always re-runs the lifecycle** (commit 0728ae248a) | landed 2026-09-23, in **156** (absent in 155, present in 157) | 156 | both | The pass machinery: the loop-limit error round now returns "repeat" once per frame whenever observations were skipped, whatever the lifecycle state. The pump's D + 2 and js-minus-js's RAM-write passes may gain a pass; re-measure (§2.3) |
| 4 | **Timeline names global by default, last in tree order wins on a clash** | CSSWG resolved 2025-08-20 (csswg#12581); flags `CSSTreeScopedScrollTimeline` + `CSSTimelineScopeGlobal` **experimental**, new in 157; `timeline-scope: all` (`CSSTimelineScopeAll`) experimental since ≤ 153 | 2027 | both | css-physics's `.ts` nests and js-minus-js's `body { timeline-scope: … }` list become unnecessary. Two 153 behaviours change: a clash is inactive today, and an unresolved name holds the animation at time 0 *(measured)* (§2.4) |
| 5 | **`random()`** | `CSSRandomFunction` stable on main, ships **156** | 156 (2026-10-20) | css-physics, js-minus-js | A per-element constant, **not** per-frame noise: the value survives restyles *(measured)*. Symmetry breaking, seeds. Element-dependent `random()` disables the matched-properties cache (ENGINE_RESEARCH Q5) |
| 6 | **Calc()-computed registered `<integer>` stored as an integer** (CL 8559024) | Gerrit NEW, failed dry run 2026-10-13 | 159+ | both | Flips probes `style-int-256` and the integer half of `var-6-digits`: `<integer>` would cross `var()` exactly (`String::Number(int)`). `<number>` keeps 6 digits on main *(code)* (§2.5) |
| 7 | **Responsive iframes** (`frame-sizing`, `<meta name=responsive-embedded-sizing>`) | `ResponsiveIframes` stable since 155; chromestatus ships 154 | shipped | paint; css-physics via SVG children | For an **HTML** child the size reaches the parent only at DOMContentLoaded, load and script `requestResize()` *(code)*: a load-time per-cell readback for paint (§2.6). An **SVG** child reports its natural size on every font change, to `<object>` in any build and to `<iframe frame-sizing>` from 154: a per-frame, cross-process channel ([01-lifecycle.md](01-lifecycle.md) finding 1, measured) |
| 8 | **`@mixin`/`@apply`/`@result`, `@private`; `@function` unchanged** | `CSSMixins`, `CSSPrivate` experimental; I2P 2026-07; WPT Chrome-exp 607/618 | 2027 | both (bytes) | Mixins are expanded when the RuleSet is built *(code)*, so they shrink the stylesheet, not the rule visits. `@function` still has no memoization or recursion, and the spec now forbids recursion on purpose (csswg#13943) |
| 9 | **`@property` with optional descriptors (ships 159 per chromestatus) and a multi-name prelude** (`@property --a, --b {…}`, CSSWG resolved, csswg#14225/14227) | no code on main yet (`PropertyRegistration::MaybeCreateForDeclaredProperty` still requires `syntax` and `inherits`) | 159 / 2027 | both | Generator bytes and parse time for 20k–300k registrations (§2.7) |
| 10 | **Event triggers in CSS**: `event-trigger: --t click()`, `keypress("a")`, `pointerdown()`… + `animation-trigger` | spec `animation-triggers-1`; Blink has only the JS `EventTrigger` (experimental); no CSS property, no chromestatus entry | 2027+ | both | Script-free input events driving latches: keyboard for js-minus-js's editor, pointer up/down for css-physics (§2.8) |
| 11 | **HarfRust shaper** | `HarfRustShaping` **test** (off in 153); field-trial testing entry added 2026-09-01, removed 09-07; enable CL 7912622 shows `blink_perf.layout` regressions | not soon | js-minus-js | The CPU font shapes 1.65× slower in Chrome 153 (HarfRust 0.12, [06](06-text-and-fonts.md)), 1.34× at 0.14 and 1.21× at HEAD standalone ([07](07-harfbuzz.md)); the 16,384-subtable cap goes. Playwright passes `--disable-field-trial-config` *(measured)*, so the harness is safe either way |
| 12 | **Lazy declaration parsing for inline `<style>`** | `LazyParseInlineStyleSheets` off; in the field-trial testing config from 157 | Finch | both (little) | Only rules whose selector never matches skip parsing. A failed `@container` still parses the declarations to check for animation properties *(code)*, so the projects' gated rules gain nothing (§2.9) |
| 13 | **Loading for paint**: subresource `Link` headers can't register dictionaries (157); CDT fetch updates still flagged; dictionary `ttl` | `kRestrictLinkHeaderOnSubresource` on in 157; `CDTNew*` experimental in all four; `kCompressionDictionaryTTL` off | 157 / ? | paint | paint uses `<link>` elements, so nothing breaks. `ttl` would let a `no-store` response register a dictionary (§2.10) |
| 14 | **Interop 2026** puts style queries, scroll-driven animations, scroll snap, anchor positioning and `attr()` on the board | Firefox: style queries 151, anchor 147, view timelines 159; no `if()`, `@function`, `ident()`. Safari TP: `if()`, `ident()`, `inherit()` | 2026–27 | css-physics (Firefox) | css-physics's Firefox path keeps improving; `if()` stays Chrome/Safari-only (§2.11) |
| 15 | **The stale-timeline re-run rule is being re-specified** | csswg#12120 (open, 2026-10-02), #14337 (Agenda+), WPT `scroll-timeline-invalidation.html` in Interop 2026 | 2027 | both | The "second pass while view timelines are stale" both projects run on is under spec discussion. Chrome's behaviour isn't flagged to change yet (§2.3) |

---

## 1. How it works: Chromium's feature pipeline

### 1.1 The release train, and mapping a commit to a milestone

Chrome now branches every two weeks (chromiumdash `fetch_milestone_schedule`) *(docs)*:

| M | Branch | Stable | | M | Branch | Stable |
|---|---|---|---|---|---|---|
| 153 | 2026-08-17 | 09-08 | | 158 | 10-26 | 11-17 |
| 154 | 08-31 | 09-22 | | 159 | 11-09 | 12-08 |
| 155 (8059) | 09-14 | 10-06 | | 160 | 11-30 | 2027-01-05 |
| 156 (8078) | 09-28 | 10-20 | | 161 | 12-14 | 01-19 |
| 157 (8103) | 10-12 | 11-03 | | 162 | 2027-01-11 | 02-02 |

A commit on main dated between branch(N−1) and branch(N) ships in N unless merged back. Main at `22b3b159` is 158;
anything flipped now ships 2026-11-17 at the earliest. The repo tests on 153: two milestones behind stable 155, five
behind main. A status flip on main reaches stable 3–5 weeks after it lands (up to two weeks to the next branch point,
then about three weeks of beta).

### 1.2 Runtime flags, base::Features, Finch

`third_party/blink/renderer/platform/runtime_enabled_features.json5` (1,277 entries on main, 1,220 in 153) declares
every Blink feature. The header (`:16-24`) defines the statuses:

- `stable`: on everywhere.
- `experimental`: on with `--enable-experimental-web-platform-features`.
- `test`: on only in content_shell web tests.
- no status: off everywhere.
- A dict status (`{"Android": "stable", "default": "experimental"}`) per platform.

Each entry also generates a `base::Feature` of the same name unless `base_feature: "none"` (`:120-139`). It defaults
to enabled iff the status is `stable`, and by default (`copied_from_base_feature_if: "enabled_or_overridden"`,
`:156-185`) an override of that base::Feature from the command line or Finch sets the Blink flag. So there are three
ways to turn a flag on: `--enable-blink-features=X`, `--enable-features=X`, or a Finch study. A stable feature can
also be killed by Finch. Non-Blink switches live in `third_party/blink/common/features.cc` (`BASE_FEATURE(kX,
FEATURE_{EN,DIS}ABLED_BY_DEFAULT)`), `services/network/public/cpp/features.cc`, `net/base/features.cc`,
`cc/base/features.cc` and `content/public/common/content_features.cc`.

**Field-trial testing config.** `testing/variations/fieldtrial_testing_config.json` enables extra features in
non-Chrome-branded builds. `ShouldUseFieldTrialTestingConfig` (`components/variations/service/
variations_field_trial_creator.cc:143-155`) returns true for non-branded builds unless `--disable-field-trial-config`
or `--variations-server-url` is passed. Chrome for Testing is presumably not `GOOGLE_CHROME_BRANDING`
*(inference)*. Playwright passes `--disable-field-trial-config`: `chrome://version` in the repo's harness shows it on
the command line *(measured)*.
**So the harness never sees testing-config features, but a person opening a page in a hand-launched CfT or Chromium
does.** On main that config enables, on Linux, among others `LazyParseInlineStyleSheets`,
`SingleAxisScrollContainers`, `XMLRustForNonXslt`, `MemoryConsumerForNGShapeCache` and `Canvas2dDeferredFlush`
(`exp/09/v/ftc_main.json`) *(code)*. Branded Chrome instead gets Finch seeds, which can enable experiments for a
fraction of users: a benchmark taken in a user's Chrome may differ from the harness's.

**Origin trials** gate a feature per page by token (`origin_trial_feature_name`). Current relevant trials:
`OverscrollAreas` and `HTMLInCanvas`. None matters for these projects. A static `_headers` file could carry a token
for paint, though.

### 1.3 chromestatus is a plan, not a fact

chromestatus milestones come from the intent threads. Several of them disagree with the code:

| chromestatus says | the code says |
|---|---|
| CDT "Updates" ship 156 (4895435813683200) | `CDTNewCrossOriginHandling`, `CDTNewDestination`, `CDTNewReferrerAndReferrerPolicyHandling` experimental in 153, 155, 157 and main |
| corner shorthands ship 157 (5152215540039680) | enabled 2026-09-30, reverted the same day (`CSSCornersShorthand` experimental) |
| text-decoration-skip-spaces ship 155 | stable in 155 and 157, reverted on main 2026-10-16 (f64cc47488) |
| optional `@property` descriptors ship 159 | no implementation on main |
| `object-fit` on SVG in `<object>` ships 157 | `SVGEmbeddedAsReplacedElement` experimental on main |
| ::highlight(\*), flow-start/end, media pseudo-classes ship 158 | all `experimental` on main |
| text-decoration-inset in the 154 release notes | flipped to stable 2026-09-29 → 157 |

Rule used below: the **flag status per branch** is the fact; chromestatus is the intent. The commit log gives the
date. Stage types in the API: x30 dev trial, x50 origin trial, x60 ship. `browsers.chrome.desktop` is the planned
desktop milestone. Queries: `?q=browsers.chrome.desktop>=154`, `?q=category=CSS`, `?q=updated.when>2026-03-01`
*(docs)*.

### 1.4 The spec side, and how to read it

A CSSWG resolution ("RESOLVED:" in the meeting-bot comment) is followed by a spec edit, then WPT tests, then
implementations. Three cheap signals beat chromestatus:

- **wpt.fyi "experimental" runs** (Chrome with `--enable-experimental-web-platform-features`, Firefox Nightly,
  Safari TP; `https://wpt.fyi/api/search?run_id=…&q=<path>`). Pass counts show who is implementing.
- **Safari Technology Preview** leads on CSS functions this year: it passes all `ident-*` tests (46/46),
  `inherit-*` (17/17) and `if-*` (251/256) *(docs)*.
- **Gerrit** (`https://chromium-review.googlesource.com/changes/?q=…`, public REST). It showed CL 8559024 (the
  `<integer>` fix) still NEW, and CL 7912622 (HarfRust enable) parked with regressions.

---

## 2. What it means for the projects

### 2.1 Dynamic names: what works today, what the spec now says, what Blink lacks

**The spec (docs).** css-values-5 §8.8 (current ED): "The `ident()` function represents an arbitrary `<ident>` …
It is an **arbitrary substitution function**", argument grammar `ident( <declaration-value> )`. Its replacement
substitutes ASFs in the argument, parses `<ident-arg>+` (`<string> | <integer> | <ident>`), computes each piece and
concatenates. The ASF appendix makes every ASF substitute nested ASFs in its arguments first, so `var()`'s name
argument may itself be built: WPT `ident-function-substitution.html` tests `var(ident("--" attr(data-name
type(*))))` and `var(var(--n))` where `--n: ident("--" …)`. Resolved 2026-08-06 (csswg#14213, proposed by WebKit
and Gecko engineers as "easier to implement"). Earlier "validate ident() at parse time" (csswg#12668) is superseded.

**Blink (code).** Main still implements the older model: `ident()` is parsed eagerly with literal pieces only.
- `ConsumeIdentFunction` (`core/css/properties/css_parsing_utils.cc:1717-1765`) accepts custom-idents, strings and
  integers; anything else, including `var(`, returns nullptr.
- `ConsumeVariableReference` (`core/css/parser/css_variable_parser.cc:161-197`) accepts `ident()` as `var()`'s first
  argument only if `ConsumeIdentFunction` succeeds, so `var(ident("--m" var(--k)))` is invalid at parse time. The
  comment there cites csswg#11500 and the planned "argument grammar" rework, which `CSSArgumentGrammar` (test) has
  implemented only for `attr()` (`style_cascade.cc:2432`, `css_variable_parser.cc:591`).
- At computed time `ConsumeAndComputeVariableName` (`style_cascade.cc:101-120`) evaluates a literal `ident()` and
  maps an invalid result to the unreachable name `unknown`.
- In properties, a declaration containing `var()` is parsed after substitution, so `ident("--a" var(--k))` there
  reaches `ConsumeIdentFunction` with literal pieces and works.

**Measured in 153 with `--enable-blink-features=CSSIdentFunction`** (`exp/ident2.js`):

| Construct | Flag off | Flag on |
|---|---|---|
| `--op: var(ident("--m" 3))` | invalid (−99) | **13** (works) |
| `--op: var(ident("--m" var(--k)))` | invalid | **invalid** (parse-time rejection, as the code says) |
| `anchor-name: ident("--a" var(--k))`, read by `anchor-size(--a3 width)` | fallback 7 | **33** (works) |
| `container-name: ident("b" var(--k))` + `@container b3 style(--q: 1)` | no match | **match** |
| `view-timeline-name: ident("--t" var(--k))` | inactive | **active** |
| `width: anchor-size(ident("--a" 2) width, 7px)` (literal or with `var()`) | 0 (invalid) | **renderer crash** |

The crash has a code explanation on main: `CSSMathExpressionAnchorQuery::ToQuery`
(`core/css/css_math_expression_node.cc:4088-4097`) builds the anchor name from `custom_ident->Value()`, which is the
empty `string_` for an `ident()`-backed `CSSCustomIdentValue` (`css_custom_ident_value.cc:38-43`), instead of
`ComputeIdent()`/`Resolve()`. See §6.

**What it means.**
- **js-minus-js read ports** pick an anchor name with a two-level `if()` (O(√N) `style()` tests, ~200–600 µs per
  port, PRIMITIVES §P7). With `anchor-size(ident("--c" var(--a)) width)` a port is one name construction and one
  anchor lookup. Grid placement ports already measured ~15 µs (PRIMITIVES), so the win over the grid port is unclear.
  The real gain is that RAM can keep `anchor-name` leaves. Needs: the crash fixed, the flag shipped. The write side
  already works behind the flag: one rule `anchor-name: ident("--c" var(--addr))` instead of per-address rules.
- **css-physics contact slots** (COMPARISON "Anchor-name reads as dynamic indexing"): `var(ident("--x" var(--partner)))`
  reads a partner's register in style, with no layout trip. That is the version of the idea without the
  "value arrives in layout" caveat. It needs the ASF model, which Blink doesn't have. Cost would be one hash lookup
  per read in the cascade *(inference)*. The N² *rule visits* would go, the K-slot ranking would stay.
- **`container-name: ident("b" var(--i))`** could replace css-physics's literal owner names `b{i}`. It's cosmetic:
  the names are written per element anyway.

### 2.2 `inherit()`

**Spec (docs):** css-values-5 `inherit()`, defined on custom properties only (csswg#2864, 2023 resolution). `result:
inherit()` inside `@function` passes through like plain `inherit` (csswg#12987, 2025-11). Rename to `parent()`
rejected (csswg#13426). **Blink:** `CSSInheritFunction` experimental in 153 and main, I2P only, no milestone
(chromestatus 5996914579472384). The substitution is `var()`'s with the parent's computed value
(`css_variable_parser.cc:570-580`).

**Measured, 153 with the flag** (`exp/flags.js`): with `#p{--a:5}` on a registered `--a` (`inherits: false`), a child
`--b: calc(inherit(--a) + 1)` computes **6**, `inherit(--a, 9)` gives 5, and an unregistered `inherit(--v)` gives 4.

**Why it matters.**
- ENGINE_NOTES 5 and 41: an inherited custom property that changes restyles the whole subtree below.
- PRIMITIVES rec. 2: make js-minus-js's next-state properties `inherits: false` where only `.vp3` reads them.
- `inherit()` is the general tool for both. A chain level computes its state as non-inherited registers and the next
  level reads them with `inherit(--x)`, so a change no longer floods leaves, readers and `.regs` under the level.
- Both projects' chains are one element per step: each level reads only its parent. That is exactly the
  one-step-up reach of `inherit()`.
- The MPC hit test also compares the parent's inherited variables
  (`ParentStyle()->InheritedEqualIncludingInheritedVariables`). Fewer inherited registers would make leaf styles
  cacheable again *(inference)*.

### 2.3 Passes per frame: one change landed, one rule under discussion

**Landed (code, 156).** `LocalFrameView::NotifyResizeObservers` (`core/frame/local_frame_view.cc:2328-2369`, commit
0728ae248a, 2026-09-23) changed from:

```cpp
// 153–155
if (min_depth != kDepthBottom) { DeliverObservations(); }
else { if (skipped && !dispatched) { ClearObservations(); …error…; ScheduleAnimation();
                                     SetLoopLimitErrorDispatched(true); }
       if (Lifecycle().GetState() >= kPrePaintClean) return false; }
return true;
```
to: deliver → repeat; at the depth limit with skipped observations → `ClearObservations()`, dispatch the error once,
**repeat once** (`needs_to_repeat_lifecycle = true`); otherwise no repeat.

Two differences matter:
- At the depth limit, 153 repeated only if the lifecycle was dirty (state < `kPrePaintClean`), skipped observations
  or not. 156 repeats once per frame whenever observations were skipped (the error flag resets each frame in
  `ClearResizeObserverLimit`, `:2903-2910`), and never just because the lifecycle is dirty.
- 156 clears skipped observations every time. 153 kept them when the error had already been dispatched.

`RunResizeObserverSteps` returning true re-arms the post-layout snapshot (01-lifecycle §1.3), so the extra round is
an extra style+layout pass whenever a view timeline is stale. The internal observer behind
`contain-intrinsic-size: auto` takes part. So:

- **The pass pump** (PRIMITIVES finding 1: D + 2 passes; siblings 3) may become D + 3 / 4 on 156+ *(inference)*.
- **js-minus-js's RAM leaves** (`content-visibility: hidden` + `contain-intrinsic-size: auto`): several written
  leaves at the same depth in one frame produce skipped observations. On 156+ that adds one repeat per frame. It is
  useful if an issue is waiting, wasted (~50–100 ms of style+layout, BENCHMARKS) if not *(inference)*.
- Check: count `LocalFrameView::NotifyResizeObservers` per frame on Chrome 156+ with js-minus-js's trace tooling
  (01-lifecycle §5 lists the trace signatures).

**Unchanged (code):** `SnapshotScrollTimelinesPostLayout` still has no status. `RunSnapshotPostLayoutStateSteps` is
stable. The one-shot snapshot boolean is the same.

**Under discussion (docs):** csswg#12120 ("not clear when to update stale timelines", 2026-10-02) and #14337 (Agenda+;
Gecko implemented "any range input changed makes the timeline stale, not the scroll position").
`scroll-timeline-invalidation.html` is an Interop 2026 test that Blink and Gecko fail. Firefox's same-frame re-run
(bug 2048416) waits on #12120. Any resolution that tightens staleness to *range* inputs would keep Chrome's register
reads (the subject's position is a range input of a view timeline). A resolution that limits re-runs to one per frame
would cap the pump *(inference)*.

**Also resolved (docs):** csswg#9256, 2026-05-27: "Scroll and view timelines don't become inactive when there's no
scroll range". js-minus-js ENGINE_NOTES 35 (a register in an `overflow: hidden` scroller with no in-flow content is
active) is now spec-backed. ENGINE_NOTES 12 ("an animation on an inactive timeline costs nothing") must not rely on a
zero scroll range to make a timeline inactive.

### 2.4 Timeline names: global scope and clash resolution

**Spec (docs):** csswg#12581, 2025-08-20:
- "change timeline scoping to be global by default (like anchor names)";
- "change timeline clash resolution to use last in tree order";
- the same for triggers.

**Blink (code):** two flags, both experimental and new in 157 (`CSSTimelineNameConflictResolution`, experimental in
153/155, was removed).
- `CSSTreeScopedScrollTimeline` makes `DeferredTimeline::EffectiveScrollTimeline` return the last attached timeline
  in flat-tree order (`core/animation/deferred_timeline.cc:22-46, 87-95`). Without it, more than one attached
  timeline returns `nullptr`.
- `CSSTimelineScopeGlobal` (depends on it): when `FindAncestorTimeline` reaches the root without a match, it falls
  back to `DocumentAnimations::GetGlobalDeferredTimeline(tree_scope, name)` (`core/animation/css/css_animations.cc:
  1476-1494, 1515-1521, 1546-1551`). The ancestor walk still runs first, so the O(depth) lookup 04-animations-and-scroll
  describes is unchanged.

**Measured, 153** (`exp/tl.js`; `@keyframes` from 0 to 100, `animation: … 1000s linear both`):

| Case | 153 | with global scope + clash rule |
|---|---|---|
| name declared outside the reader's ancestors, no `timeline-scope` | **0**: timeline `null`, play state running, time held at 0, `from` keyframe applied | the real progress |
| same, hoisted by `timeline-scope` (control) | 45.45 | 45.45 |
| two `view-timeline`s with the same name under one scope | **−1**: no effect (DeferredTimeline with 2 attachments is inactive) | last in tree order |
| `timeline-scope: all` (flag `CSSTimelineScopeAll`, experimental) | 0 (unsupported) | 45.45 with the flag *(measured)* |

**For the projects.**
- css-physics's `.ts` wrappers (ARCHITECTURE "Timeline names are hoisted…") become unnecessary once
  `CSSTimelineScopeGlobal` ships. So does the CLAUDE.md gotcha "keep `.ts` above `#RB`".
- js-minus-js's `body { timeline-scope: … }` list of thousands of names (04-animations-and-scroll: a linear scan per
  lookup) goes too.
- Risk: anything that today relies on a name *not* resolving gets an active timeline once some element anywhere
  declares the name. The "held at 0" fallback and "clash = inactive" are the two behaviours that flip. Both projects
  should check for name reuse across `display` states before Chrome ships it.

### 2.5 Number precision through `var()`

- `<number>`: no change. `CSSNumericLiteralValue::CustomCSSText` still serializes `kNumber` and length units with 6
  significant digits (the `kMinInteger = -999999 … kMaxInteger = 999999` block, `core/css/css_numeric_literal_value.cc:
  ~296-300`) *(code)*. No flag, CL or chromestatus entry proposes a change. Bug 40266999 stays open.
- `<integer>`: CL 8559024 ("Registered custom property `<integer>` incorrectly computed to `<number>`", bug 571450199)
  changes `style_builder_converter.cc` to `CSSNumericLiteralValue::Create(math_value.ComputeInteger(…), kInteger)`
  when the primitive is an integer *(code, Gerrit patch)*. `kInteger` serializes with `String::Number(int)`
  (`css_numeric_literal_value.cc:227-229`), which is exact.
- Status: NEW, dry run failed on `linux-chromeos-rel` 2026-10-13. If it lands:
  - `style-int-256` flips (the purpose of the fix);
  - `var-6-digits` flips for `<integer>` (1048575 survives `var()`), not for `<number>`;
  - registered integers are still stored as `double`, so exactness holds to 2^31 (`ComputeInteger` clamps) and
    js-minus-js ENGINE_NOTES 3 (floats, |v| < 2^24 in the DSL) is unaffected;
  - css-physics's digests pack 6 bodies per word because of the rounding. If they are `<integer>`, the packing could
    widen (bugs/README already flags the re-check).
- **`CSSCalcEarlyNaNAndInfFolding`** (new in 157, **off**) disables the early folding of `calc()` to NaN/±∞ while
  building a `CalculationValue` (a0ca576ea8, `css_math_expression_node.cc:639-644`). It's a default behaviour change
  in 157 for expressions mixing percentages with `round()`/division, like `calc(4px / round(100% / 25px))`. Neither
  project divides by zero on purpose. Run `make engine-costs` and the smoke tests on 157 anyway *(inference)*.

### 2.6 Responsive iframes: a child→parent channel, per frame only for SVG children

**Mechanism (code, main):**
- `frame-sizing: content-width | content-height | content-inline-size | content-block-size` on an `<iframe>`
  (`css_properties.json5`, flag `ResponsiveIframes`).
- `LayoutIFrame::GetNaturalDimensions` (`core/layout/layout_iframe.cc:71-112`) uses the child frame view's natural
  size, or the owner's `LastNaturalSizingInfo`, scaled by zoom. Only `LayoutIFrame` does this: `<object>`/`<embed>`
  are not responsively sized.
- The child opts in with `<meta name="responsive-embedded-sizing" content="allow-origins=…">` before `<body>`
  (`core/html/html_meta_element.cc:694-697, 771-815`; the `allow-origins=` prefix is required since 2026-08-27,
  commit 198fdcc167, so after 153). The value is a CSP `frame-ancestors` source list matched against the parent.
- The child reports `LocalFrameView::RecordNaturalDimensions()` (its layout-overflow size, `:1301-1307`) to the owner
  in exactly three places (`Document::RequestResizeResponsiveIframe`, `core/dom/document.cc:8405-8428`):
  `FinishedParsing` (DOMContentLoaded, `:8186`), `DispatchLoadEventAndFinalize` (the load event, `:4416`), and
  `window.requestResize()` (script).

**So:**
- **css-physics process parallelism** (BENCHMARKS §5: cross-site iframes get their own processes; PRIMITIVES §4: "no
  way to read a result back"): there is now a way back, but at document-load granularity. A child would have to
  navigate itself (a `<meta http-equiv=refresh>` loop) to report again, at page-load cost per report. No per-frame
  channel for an HTML child *(code + inference)*. An SVG child is different: its natural size follows its root
  `<svg>`'s font-relative `width` on every font change, across processes, to an `<object>` without any flag (and to
  an `<iframe frame-sizing>` from 154). [01-lifecycle.md](01-lifecycle.md) §1.8 measured a one-frame round trip with
  a whole CSS machine inside the SVG's `<foreignObject>`; that, not responsive iframes, is the route to process
  parallelism.
- **paint:** a cell rendered as an `<iframe>` whose height encodes which of its 16 probes decoded would report the
  value to the parent at its load event. The parent could then read every cell's value as a number with
  `anchor-size()` or a size container, which enables canvas-wide operations (fill, count, export) in CSS. Costs: an
  `<iframe>` takes one of the ~1,000 frames per page (paint uses `<object>`s because of this), and the cell document
  must finish loading. *(inference)*
- In 153 behind the flag (pre-ship, older `content` syntax) the opt-in was accepted (`requestResize()` stopped
  throwing) but the iframe sized to 0 or stayed 150 px *(measured, `exp/riframe.js`)*. Test on 155+ before building on it.

### 2.7 Mixins, `@private`, `@function`, `@property`: stylesheet size, not runtime

- **`@mixin`** (code): `@mixin --name(params) { @result { … } }`, `@apply --name(args) [{ @contents block }]`
  (`core/css/parser/css_parser_impl.cc:2493-2566, 2758-2820`). `RuleSet::AddChildRules` expands `@apply` by cloning
  the mixin's rules with `MixinParameterBindings` into the applying rule (`core/css/rule_set.cc:1082-1104`).
  - The expanded rules are ordinary rules: same buckets, same visits, same container-query evaluation. The bindings
    join the MPC key (ENGINE_RESEARCH Q5).
  - 153 needs `@result` around declarations *(measured: without it nothing applies; with it, parameters and defaults
    work)*. csswg#13524 ("Auto-wrap mixin body in `@result` if omitted?") is closed as accepted.
  - Spec churn (csswg-mixins-2: `@macro` merged in and out, `@result`, `@env`, `@private`, scoped mixins) makes 2027
    the earliest ship.
  - For css-physics: a pair rule template as a mixin would shrink the generated CSS bytes and parse time, not the N²
    visits.
- **`@private`** (`CSSPrivate`, experimental, crbug.com/542651959): custom properties visible only within the
  enclosing rule and the elements it matches, names rewritten (`PrivateNameMap`, `css_parser_impl.cc:2550`). It is a
  hygiene tool for temps (js-minus-js's pooled `qp<i>`, css-physics's `SHARE`). Untyped (csswg#14442 open), so no
  `calc()` materialisation: PRIMITIVES says a *registered* temp is what materialises a value.
- **`@function`** (shipped 139): unchanged on main.
  - Cycle detection is still keyed on the function and taken before the arguments are resolved
    (`style_cascade.cc:1918-1925`). So there is no recursion, and even `--f(--f(1))`, a nested call that isn't
    recursive, is invalid. csswg#13943 calls that a spec bug (Chrome bug 514021797); the fix moves the substitution
    context to execution time and keeps recursion banned.
  - Still no result cache; any call sets `SetHasTreeScopedReference()` (MPC-uncacheable) and
    `SetAffectedByCSSFunction()`.
  - New since 153: `@navigation` queries inside function bodies, and per-invocation `random()` keys.
  - csswg#14338 (2026-08-26): arguments, locals and result evaluate in the caller's context. Blink already does this.
  - PRIMITIVES' verdict stands: don't use it.
- **`@property`**: chromestatus 5168674259468288 plans optional descriptors for 159 (omitted `syntax` → `*`,
  `inherits` → true, initial → guaranteed-invalid). `PropertyRegistration::MaybeCreateForDeclaredProperty`
  (`core/css/property_registration.cc:138-163`) still returns null without `syntax`/`inherits` *(code)*. 153 doesn't
  register `@property --od{syntax:"<number>"}` *(measured: `1.50` stays unnormalised)*.
  - The multi-name prelude `@property --a, --b, --c { … }` is resolved (csswg#14225; CSSOM `names` array, #14227),
    with no implementation or flag. Mass registration by prefix (csswg#13212) is open.
  - For css-physics (one `@property` per register name, thousands of rules) both cut bytes and parse time.

### 2.8 Event triggers: the input primitive both projects lack

`animation-triggers-1` (split out of css-animations-2 by PR 13571) defines:

```
event-trigger: --t click() | dblclick() | pointerenter() | pointerleave() | pointerdown() | pointerup()
             | keypress("<keys>") | focusin() | focusout() | input() | change()   [ / <exit events> ]
animation-trigger: --t play-forwards | play-backwards | pause | reset | play-once …
```

Stateful pairs (`click() / click()`) give enter/exit. Blink has only the Web Animations `EventTrigger` constructor
(`core/animation/event_trigger.idl`, flag `EventTrigger` experimental, restricted to `Node` targets 2026-09-11).
There are no CSS properties in `css_properties.json5`, `CompositorEventTrigger` is off, and chromestatus has no
entry *(code + docs)*. `timeline-trigger`/`animation-trigger` shipped in 146; "No auto-rewind" in 151.

- **js-minus-js:** `keypress("a")` triggers on the editor host would latch keystrokes without `contenteditable`
  (ENGINE_NOTES 44–48 list its editing hazards).
- **css-physics:** `pointerdown()`/`pointerup()` pairs give a press latch, which HISTORY lists as a dead end with
  `:active`.
- Both: a click-driven `animation-trigger: --t play-once` is a script-free edge detector, PRIMITIVES §4's
  "timeline-trigger as an edge detector" without the scroll indirection.
- Estimate: not before 2027 *(inference: spec still has open issues, no Blink CSS work visible)*.

### 2.9 Style-engine performance in the pipeline

No parallel or off-thread style recalc exists or is flagged: `grep -ri parallel` over `core/css`, `core/style` and the
style parts of `core/dom` finds only the CSS parser's SIMD fast paths *(code)*. What is coming:

| Change | Status | Effect for the projects |
|---|---|---|
| `LazyParseInlineStyleSheets` (c9cab49680): `StyleEngine::CreateSheet` passes `CSSDeferPropertyParsing::kYes`, so inline `<style>` declarations are parsed on first access to `StyleRule::Properties()` (`style_rule.cc:526-533`). Selectors are still eager | off; testing config 157+; a WebView flag | Little. Only rules whose *selector* never matches stay unparsed: when a matched rule's container query fails, `ElementRuleCollector` still calls `AffectsAnimations(rule_data)`, which reads `Properties()` (`element_rule_collector.cc:688-694, 329-331`). css-physics's and js-minus-js's gated rules have matching selectors, so they all get parsed on the first restyle *(code)* |
| `ConstructableStylesheetCache` | test | none (no constructed sheets) |
| Length conversion data computed on demand (dd3aa04954, 157) | on | small per-element saving in `StyleResolverState` |
| No `StyleBaseData` for elements that can't start transitions (fcd4ab5f86, 157) | on | memory per element |
| `SkipTickingStaticAnimations` (3fdff6af94, 157): an animation whose keyframes are all `AreEquivalent` (`KeyframeEffectModelBase::…CheckIfStatic`, `keyframe_effect_model.cc:789-860`) isn't ticked on main even if not composited | stable | **Not** js-minus-js's ~5,600 chain animations (PRIMITIVES rec. 6): their keyframes go H → −1 (`ccpage5.py:125,141,228`), dynamic. Static latches like `@keyframes setp { from {--p:1} to {--p:1} }` stop costing per frame |
| `SkipPaintInvalidationWhileStayingInvisible` (1e10300698, 157) | stable | paint-only changes on `visibility: hidden` boxes skip invalidation (the commit measured −91% paint time). Only matters if a project animates colours on hidden boxes |
| MPC collision histogram (72fa0538bf), MPC cleared on settings change | on | instrumentation; nothing behavioural |
| `TrackAnimatedSources` (test), pre-computed `:hover` styles (`CompositeHoverStyle` off) | — | compositor work for colour/text-decoration |
| `MonospaceGlyphCompaction` (test, 18-part series) | test | compact glyph storage for monospace runs. The CPU font's advances vary (sentinels), so probably not applicable *(inference)* |
| `FractionalScrollOffsets` (experimental since 155) | exp | scroll offsets stop being integer-snapped. Touches css-physics's touch handles and any register that is a scroll offset, not the `top`/`left` registers *(inference)* |

### 2.10 Loading and the dictionary store (paint)

- **`kRestrictLinkHeaderOnSubresource`** (off in 153/155, **on** in 157 and main). Its param
  `disable_compression_dictionary` defaults true (`third_party/blink/common/features.cc:1959-1980`).
  `IsCompressionDictionaryLoadAllowed` (`core/loader/preload_helper.cc:246-265`) now refuses a `Link:
  rel=compression-dictionary` header on a *subresource* response; preload and resource-load hints on subresources go
  too. Document `Link` headers after load and `<link rel=compression-dictionary>` elements are untouched *(code)*.
  paint writes with `<link>` elements and `mask-image` responses, so nothing breaks. It does close the door on
  registering dictionaries from a CSS file's or an image's `Link` header.
- **CDT fetch updates** (I2S for 156, flags still experimental everywhere). The default path (`preload_helper.cc:
  1055-1067`): `mode: cors`, `credentials: omit`, no referrer, destination `compression-dictionary`. When the flags
  ship: credentials follow `crossorigin` (default anonymous → same-origin credentials) and the referrer follows the
  policy. paint is same-origin with no cookies, so no effect is expected. ENGINE_RESEARCH Q8's "CORS anonymous
  (CDTNewCrossOriginHandling)" describes the flagged path; the default is `cors` + `omit`.
- **`kCompressionDictionaryTTL`** (dev trial since 142, still disabled): `Use-As-Dictionary: …, ttl=600` would make a
  response usable as a dictionary for `ttl` seconds regardless of HTTP caching. The stated motivation is "use
  non-cacheable HTTP responses as dictionaries". paint's rule that registration needs a fresh-cacheable response
  (paint/CLAUDE.md) would relax. Watch it; enable-able with `--enable-features=CompressionDictionaryTTL` for an
  experiment.
- **Cross-origin no-cors dictionaries** (proposed, 5509970048843776, needs `Cross-Origin-Resource-Policy:
  cross-origin`), **pervasive dictionaries** (`kPervasiveSharedDictionaries` on in main; only for a hardcoded set of
  pervasive resources), **`kHttpCacheZstdCompression`** (on): no effect on paint.
- **XML**: `XMLRustForNonXslt` stable in 153, pulled in 155, back in 157. XSLT is disabled by default on main
  (61634354c2, 158). Both XML parsers cap nesting at `kMaxXMLTreeDepth = 5000` (`core/xml/parser/
  xml_document_parser_rs.cc:170`, `xml_document_parser.cc:101` on main; `:166` in the 153 Rust parser) *(code)*.
  js-minus-js's 1,561-level chains have 3× headroom; its pages use no XSLT.

### 2.11 Other engines

From BCD 8.1.6, wpt.fyi runs of 2026-10-18 (stable: Chrome 155, Firefox 158, Safari 27; experimental: Chrome 158
exp, Firefox 160a1, Safari TP 254) and chromestatus views *(docs)*:

| Feature (projects) | Chrome | Firefox | Safari |
|---|---|---|---|
| `@property` (both) | 85 | 128 | 16.4 |
| style queries on custom properties (both) | 111; range 142 | **151** (bugs/README: animation re-match and `style(--x)` bugs open) | 18 |
| `if()` (js-minus-js, paint) | 137 | none; Nightly 10/256 WPT | 27 stable 2.7% WPT; **TP 251/256** |
| `@function` | 139 | none (19% WPT) | TP |
| `ident()` | test flag | Nightly 8/46 | **TP 46/46** |
| `inherit()` | experimental | 2/17 | **TP 17/17** |
| `random()` | 156 | preview | 26.2 |
| `sibling-index()` (js-minus-js) | 138 | 154 | 26.2 |
| `progress()` (css-physics candidate) | 138 | 155 | 26 |
| typed arithmetic `calc(a / 1px)` (js-minus-js, paint) | 140 | **158** | 26 |
| view/scroll timelines, `timeline-scope` (both) | 115/116 | **159** (preview in BCD; view-timelines WPT 3.8% in 158 stable) | 26 |
| anchor positioning, `anchor-size()` (js-minus-js, paint) | 125 | 147 | 26 |
| `content-visibility`, `contain-intrinsic-size: auto` (js-minus-js) | 85/117 | 125/117 | 18/17 |
| compression dictionaries (paint) | 130 | preview (WPT 28%) | none (11%) |
| `white-space-collapse: preserve-spaces` | none, no flag | **124** | none |
| `frame-sizing` | 154 | none | none |
| `scroll-axis-lock` (css-physics touch) | 153 | none | none |

Interop 2026 focus areas that touch the projects: **container style queries, scroll-driven animations, scroll snap,
anchor positioning, `attr()`**, plus zoom, `shape()`, view transitions. The rest (dialogs, IndexedDB, WebRTC, …)
doesn't matter here. css-physics's Firefox path (ARCHITECTURE §6) benefits from three of them in 2026–27. `if()` is
not an Interop area, so css-physics's Firefox fallbacks for `if()` remain necessary.

---

## 3. What's changing: the tables

Statuses are per branch: 153 | 155 | 157 | main. "—" = flag absent, "off" = present without status.

### 3.1 Shipped or flipped 154–158 (relevant subset of the 316 status changes)

| Feature | Flag | 153 / 155 / 157 / main | chromestatus | Ships | Rel. | Why |
|---|---|---|---|---|---|---|
| Responsive iframes | `ResponsiveIframes` | exp / stable / stable / stable | 5108373464547328 | 154 | paint | load-time child→parent size (§2.6) |
| `scroll-marker-group` modes | `CSSScrollMarkerGroupModes` | exp / stable / stable / stable | 5109685301673984 | 154 | — | carousels |
| FontFace `width`, `font-width` descriptor | — | | 5145402365050880 | 154 | js-minus-js | alias of stretch; irrelevant to the CPU font |
| `symbols()` | `CSSCounterStyleSymbolsFunction` | exp / stable / stable / stable | 5146996093616128 | 155 | js-minus-js | anonymous counter styles: digit glyph mapping without `@counter-style` rules (P10) |
| `margin-trim` | `MarginTrim` | exp / stable / stable / stable | 5197863732772864 | 155 | — | |
| `text-decoration-skip-spaces` | `CSSTextDecorationSkipSpaces` | exp / stable / stable / **exp** | 4832783806627840 | 155–157, reverted for 158 | — | |
| JPEG XL decoding | `kJXLImageFormat` | off / on / on / on | 5114042131808256 | 155 | paint | another decoder for probe images |
| **`random()`** | `CSSRandomFunction` | exp / exp / stable / stable | 5324559251275776 | 156 | both | §0 #5 |
| `scroll-snap-type: … pair` | `CSSScrollSnapTypePair` | test / exp / stable / stable | 5124378896498688 | 156 | css-physics | both axes snap to one element: `#FO`'s follower can't split targets |
| Single-axis scroll containers (`overflow: scroll clip`) | `SingleAxisScrollContainers` | exp / exp / stable / stable | 5067363861004288 | 156 | css-physics | a one-axis register scroller; snap support flagged for 158 |
| `:navigation-source` | `NavigationSourcePseudoClass` | — / exp / stable / stable | 6327898878377984 | 156 | — | |
| **RO loop-limit round repeats** | (none) | old / old / new / new | — | 156 | both | §2.3 |
| `text-overflow: <string>` | `TextOverflowString` | exp / exp / stable / stable | 6294595288825856 | 157 | — | |
| `text-decoration-inset` | `CSSTextDecorationInset` | exp / exp / stable / stable | 5178263526834176 | 157 | — | |
| `position-visibility: anchor-valid`, singular names | `CSSPositionVisibilityAnchorValid`, `PositionVisibilitySingularValues` | — / — / stable / stable | 5136856479039488, 5136123851571200 | 157 | js-minus-js, paint | hide a reader whose anchor is missing |
| HTML-in-canvas | `CanvasDrawElement` | exp / exp / stable / stable | 5172548013916160 | 157 | — | needs script |
| Static animations not ticked | `SkipTickingStaticAnimations` | — / — / stable / stable | — | 157 | both | §2.9 |
| Paint invalidation skipped while invisible | `SkipPaintInvalidationWhileStayingInvisible` | — / — / stable / stable | — | 157 | — | §2.9 |
| Clear stale shaping on line-break overflow | `LineBreakerClearShapeResultOnOverflow` | — / — / stable / stable | — | 157 | js-minus-js | line breaker reshapes; the CPU line doesn't wrap |
| Variable-font `ital` axis | `FontVariableItalicAxis` | — / — / stable / stable | — | 157 | js-minus-js | only with `font-style: italic` |
| Early NaN/∞ folding disabled | `CSSCalcEarlyNaNAndInfFolding` | — / — / off / off | — | 157 | both | §2.5 |
| Subresource `Link` can't register dictionaries | `kRestrictLinkHeaderOnSubresource` | off / off / on / on | — | 157 | paint | §2.10 |
| Raster-inducing scroll everywhere | `RasterInducingScroll` | Linux,Win / same / stable / stable | — | 157 | css-physics | scroll handles: no main-thread repaint per scroll on Linux already |
| Rust XML parser for non-XSLT | `XMLRustForNonXslt` | stable / exp / stable / stable | 5309598397497344 | 153 (pulled 155) | js-minus-js | XHTML pages; depth cap 5000 either way |
| SVG `textPath side` | `SVGTextPathSideAttribute` | — / exp / exp / stable | 5422782593761280 | 158 | — | |
| Neutral-keyframe easing fix | `NeutralKeyframeEasingCompliance` | — / — / — / stable | — | 158 | both | implicit keyframes use the default easing; registers use explicit `from`/`to`, so no effect *(inference)* |
| XSLT off by default | `XSLT` | stable ×3 / **off** | — | 158 | — | |
| Pervasive dictionaries | `kPervasiveSharedDictionaries` | off → on (main) | 5137485911949312 | 154–158 | — | hardcoded pervasive resources only |

Flags removed since 153 because they shipped earlier (behaviour unchanged): `CSSTypedArithmetic` (140),
`CSSContrastColor` (147), `ContainerNameOnly` (148), `CSSGapDecoration` + `CSSGridGapSuppression` (149),
`CommaSeparatedContainerQueries`, `CSSOverscrollBehaviorChain` (150), `CSSLetterAndWordSpacingPercentage`,
`TextEmphasis*`, `TreeRubyPlacement`, `MergeStickyLayers`, `MergeFixedLayers`, `CompositeBGColorAnimation`,
`ScrollingContentsCullRectOnScrollNode`, view-transition and soft-navigation cleanups. `CSSTimelineNameConflictResolution`
(experimental) was removed in favour of `CSSTreeScopedScrollTimeline`.

### 3.2 In development: flags at `test` / `experimental` on main

| Feature | Flag (main) | 153 | chromestatus / bug | Rel. | Why |
|---|---|---|---|---|---|
| **`ident()`** | `CSSIdentFunction` test | test | 6230159413477376 (I2P) | both | §2.1. Old model; crash with `anchor-size()` |
| Argument grammar (ASF arguments substituted first) | `CSSArgumentGrammar` test | test | csswg#11500 | both | only `attr()` so far; the prerequisite for `var(ident(… var()))` |
| **`inherit()`** | `CSSInheritFunction` exp | exp | 5996914579472384 | both | §2.2 |
| `@mixin`/`@apply`/`@result`/`@contents` | `CSSMixins` exp | exp | 5108022310469632 (I2P 2026-07) | both | §2.7 |
| `@private` | `CSSPrivate` exp | — | crbug 542651959 | both | §2.7 |
| `@custom-media` | `CSSCustomMedia` test | test | 5101681238605824 | — | parsed but never evaluated: no caller passes a `CustomMediaRulesMap` to `MediaQueryEvaluator` (`media_query_evaluator.cc:1664-1675` returns unknown) *(code + measured)* |
| `container-progress()`, `media-progress()` | `CSSContainerProgressNotation`, `CSSMediaProgressNotation` exp | exp | csswg#11826 | js-minus-js, paint | `container-progress(width, 0px, Npx)` normalises a container's size without `cqw / 1px` |
| Grid lanes (masonry) | `CSSGridLanesLayout` exp | exp | 5149560434589696 | — | still active (fit-tolerance rename 2026-10-15) |
| `line-clamp` | `CSSLineClamp` exp | exp | 4885575595458560 | — | |
| Global timeline names, clash rule | `CSSTimelineScopeGlobal`, `CSSTreeScopedScrollTimeline` exp | — | 6301748095483904, 5139380420345856 | both | §2.4 |
| `timeline-scope: all` | `CSSTimelineScopeAll` exp | exp | 5083692054740992 | both | one wrapper instead of css-physics's 24-name nests |
| Event triggers (JS) | `EventTrigger` exp; `CompositorEventTrigger` off | exp | — | both | §2.8 |
| HarfRust shaper | `HarfRustShaping` test | off | crbug 427409139, CL 7912622 | js-minus-js | §0 #11 |
| Monospace glyph compaction | `MonospaceGlyphCompaction` test | — | crbug 523940241 | js-minus-js | §2.9 |
| Lazy inline-sheet parsing | `LazyParseInlineStyleSheets` off (+testing config) | — | crbug 560011757 | both | §2.9 |
| Fractional scroll offsets | `FractionalScrollOffsets` exp | off | crbug 40732416 | css-physics | §2.9 |
| Relative lengths rejected in WAAPI ranges | `AnimationRangeRejectRelativeLengths` exp | — | csswg#13853 | — | script-only |
| Calc simplification/serialization per css-values-4 | `CSSCalcSimplificationAndSerialization` off | off | 5730414630010880 | both | would change how unregistered `calc()` serializes through `var()` |
| `scroll-snap-stop: before` | `CSSScrollSnapStopBefore` test | — | 5133912740331520 | css-physics | |
| Snap for single-axis scrollers | `SingleAxisScrollContainersForScrollSnap` exp | test | 5086608215900160 (158) | css-physics | |
| Overscroll areas (`overscroll-container-type`, `:overscroll-closed`) | `OverscrollAreas` exp + OT | — | 5261280285949952 | css-physics | a new script-free state from a gesture *(speculation as input)* |
| `matchContainer()` | `ElementMatchContainer` test | test | 5150754462629888 | — | JS; adds a lifecycle re-run step (`RunContainerQueryListSteps`, `local_frame_view.cc:2891`) |
| SVG children with 3D transforms | `SvgCss3dTransforms` exp | — | — | css-physics | flat SVG faces in `preserve-3d` scenes |
| CDT fetch updates | `CDTNew*` exp | exp | 4895435813683200 | paint | §2.10 |
| Dictionary TTL | `kCompressionDictionaryTTL` off | off | 6408307086589952 | paint | §2.10 |
| Post-layout-only timeline snapshot | `SnapshotScrollTimelinesPostLayout` off | off | — | both | would change the frame-start snapshot (01-lifecycle) |

### 3.3 Proposed or spec-only

| Item | State | Rel. | Why |
|---|---|---|---|
| `ident()` as ASF, `var(var(--n))` | resolved csswg#14213 (2026-08); WPT; Safari TP | both | dynamic indexing (§2.1) |
| `var-at()` / list indexing | csswg#14352 open; Antti warns `nth-item()` is quadratic over untyped tokens | both | an index into a list-valued property: a lookup table without names |
| `@property` multi-name, optional descriptors, prefix registration | #14225/#14227 resolved; #13211 (159 per chromestatus); #13212 open | both | §2.7 |
| `@if` block rule | csswg#12909 open (desugars to `if()` + `revert-rule`) | both | gates whole rule groups by `style()` without a container, so a gate could test the element's own value |
| Style queries on standard properties | csswg#14527 proposes only `writing-mode` | — | general standard-property style queries are off the table |
| Event triggers in CSS | `animation-triggers-1` ED | both | §2.8 |
| Time functions (`now()`, `year()` …) | csswg#13659, #13655 open | js-minus-js | a wall clock without an infinite animation (`#clk`) |
| `counter()` inside `calc()` | csswg#1026 open ("inherently circular in general") | js-minus-js | would replace span-width readback for counters |
| `first-valid()` | in css-values-5; no engine | both | fallbacks for ASF-built values |
| `random-item()` | spec; Safari TP 99/99, Chrome 26/99 | — | |
| Named arguments for functions | csswg#11749 Agenda+ | — | |
| Mixins invoked via custom properties | csswg#10006 "unknown/future" | — | Tab: `@apply` is processed at stylesheet level, it can't depend on element values |
| `white-space-collapse: preserve-spaces` | css-text-4; Firefox 124 only; no Blink flag or bug activity seen | js-minus-js | keeps spaces while collapsing newlines in the state line |
| Cross-origin no-cors dictionaries | 5509970048843776 proposed | paint | dictionaries from another origin's `mask-image` |
| Mute media in skipped `content-visibility` subtrees | 5121817965625344 proposed | — | |

---

## 4. Ideas, ranked by expected value × confidence

1. **Put `--enable-blink-features` profiles in `shared/js/browser.js` for "future Chrome" runs.** *(code-backed)*
   `CSSIdentFunction,CSSInheritFunction,CSSTimelineScopeAll,CSSRandomFunction` all work in 153 (§2.1–2.4) and can be
   prototyped now: an `ident()` RAM write side, `inherit()` chains, one `timeline-scope: all`. Cheapest experiment:
   a `css-physics/experiments/costs/`-style page with a 50-level chain of 200 registers and a few leaves per level,
   once as inherited registers and once as `inherits: false` registers each level reads with `inherit()`; time a
   change at the top (`tools/stylebench.js`). If it wins, try it on the solver and compare the frozen 48-body step
   (BENCHMARKS §1) against an A-vs-A control (PRIMITIVES finding 5's method).
2. **Re-measure the pass pump and js-minus-js's passes per frame on 156+.** *(code-backed)* The RO change (§2.3) can
   add one pass per frame. Run PRIMITIVES' `passes/rate.js` (`nest8`, `nest32`, `sib4`) on a 157 build and count
   `NotifyResizeObservers` per frame in a js-minus-js trace. One run settles it.
3. **paint: canvas-wide reads through responsive iframes.** *(inference)* A cell document whose layout-overflow height
   is the decoded probe's value reports it to the parent at its load event (§2.6). The parent gets 480 numbers
   readable by `anchor-size()`. First: on 155+, one `<iframe frame-sizing: content-height>` around a probe page;
   check its height after load. Kill: frames per page (~1,000), or load events that come too late.
4. **Plan the dynamic-indexing rewrite against the ASF spec, not Blink's flag.** *(docs)* Write the css-physics
   contact-slot and js-minus-js read-port designs as `var(ident(…))` / `anchor-size(ident(…))`. Test them in Safari TP
   for semantics (it passes all `ident-*` WPT), and keep the `if()` mux until Blink ships. The read-port side also
   needs the anchor `ToQuery` fix (§6).
5. **Drop `timeline-scope` scaffolding when `CSSTimelineScopeGlobal` ships**, and before that audit for name reuse
   across hidden/visible states, because clashes and unresolved names change meaning (§2.4). *(code + measured)*
   Probe both (§5).
6. **Seed with `random()` from 156.** *(measured)* It is a per-element constant, so use it once: css-physics's
   initial jitter or tie-breaking, js-minus-js's `Math.random()` seed (then an LCG in the DSL). Mind MPC: an
   element-dependent `random()` makes that element uncacheable, so put it on one element and inherit the result.
7. **Generator-side byte savings once `@property` grows a multi-name prelude**, and mixins for pair templates. Parse
   time only; measure page load before and after. *(inference)*
8. **paint: try `CompressionDictionaryTTL`** (`--enable-features=CompressionDictionaryTTL`) with `ttl` on a `no-store`
   response. If registration then works, the "fresh-cacheable response" rule is a policy choice Chrome may lift.
   *(speculation)*
9. **`text-fit` (shipped 150) as an in-layout divider.** *(speculation)* `text-fit: grow` scales a line's font size so
   its text fills the container width: the resulting line height is ∝ container width / text width, read back by a
   size container. One division per element, in layout. Experiment: a 1-line box with known text, sweep widths, read
   the height.
10. **A failed `@container` gate scans the rule's declarations.** *(code, 153 and main; found while checking lazy
    parsing)* `ElementRuleCollector` calls `AffectsAnimations(rule_data)` on every selector-matched rule whose
    container query fails (`element_rule_collector.cc:688-694` main, `:687` in 153). That loop walks all declarations
    until it finds an animation property; custom properties `continue` (`:329-340`). So a gated rule full of
    `--x: calc(…)` declarations costs O(declarations) per failed visit. That is a few ns each, so probably a small part
    of css-physics's 0.67 µs per visit (BENCHMARKS §2). Cheap check: `costs/` with one gate over 1 vs 100
    declarations, all failing. If it shows, split big gated rules.
11. **Event triggers** (§2.8): nothing to do until Blink grows the CSS properties. Comment on the spec with the
    keyboard use case if the user wants to influence it. *(speculation)*

---

## 5. Watch list: probes for `engine/check.js`

Each probe is a page plus a control, in check.js's style. Today's reading is from Chromium 153 *(measured,
`exp/*.js`)*. `@supports` rows need no script in the page: `@supports (decl) { #x { --o: 1 } }`.

| Probe id | Page (sketch) | Control | 153 today | Flips when |
|---|---|---|---|---|
| `ident-literal` | `--op: var(ident("--m" 3))`, `--m3: 13` | `var(--m3)` | invalid | `CSSIdentFunction` ships |
| `var-ident` (exists) | `var(ident("--m" var(--pc)))` | same | invalid | ident() as ASF + argument grammar (2 changes) |
| `var-var` | `--n: ident("--m" 3); --op: var(var(--n))` | `var(--m3)` | invalid | argument grammar for `var()` |
| `anchor-name-ident` | `anchor-name: ident("--a" var(--k))`, read `anchor-size(--a3 width, 7px)` | literal name | 7 (fallback) | `CSSIdentFunction` ships |
| `anchor-size-ident` | `width: anchor-size(ident("--a" var(--k)) width, 7px)` | literal | 0 (invalid); **crash** with the flag | ships *and* `ToQuery` uses `ComputeIdent` |
| `container-name-ident` | `container-name: ident("b" var(--k))` + `@container b3 style(--q: 1)` | literal name | no match | `CSSIdentFunction` ships |
| `inherit-fn` | parent `--a: 5` (registered, non-inherited), child `--b: calc(inherit(--a) + 1)` | parent's own `--a` | 0 (invalid) | `CSSInheritFunction` ships |
| `random-fn` | two elements `--r: random(0, 1000)` differ; same element stable after a restyle | `--r: 5` | 0 / 0 | 156 |
| `int-exact` | calc()-computed `<integer>` 1048575 → `var()` → `calc(x − 1048570)` = 5 | 123456 exact | 10 | CL 8559024 lands (also flips `style-int-256`) |
| `timeline-global` | `animation-timeline: --g`, `view-timeline: --g` on a non-ancestor, no `timeline-scope` | the same under `timeline-scope` (45.45) | 0 (held) | `CSSTimelineScopeGlobal` ships |
| `timeline-clash` | two `--c` view timelines under one scope, subjects at 20 and 80 | single name | −1 (no effect) | `CSSTreeScopedScrollTimeline` ships (reads the second) |
| `timeline-scope-all` | `timeline-scope: all` on a common ancestor | named scope | 0 | `CSSTimelineScopeAll` ships |
| `mixin` | `@mixin --m(--w) { @result { width: var(--w) } } #x { @apply --m(9px) }` | `width: 9px` | auto (1264) | `CSSMixins` ships |
| `custom-media` | `@custom-media --wide (min-width: 100px); @media (--wide) {…}` | `@media (min-width: 100px)` | no match | wired and shipped |
| `property-optional` | `@property --od { syntax: "<number>" }`, `--od: 1.50` reads `1.5` | full `@property` | `1.50` (unregistered) | 159 (planned) |
| `property-multiname` | `@property --m1, --m2 {…}`, `--m2: 2.50` reads `2.5` | single name | `2.50` | implemented |
| `fn-recursion` (fact) | `@function --f(--n) { result: if(… --f(calc(var(--n) − 1))) }` is invalid | non-recursive function | invalid | never, per csswg#13943; a flip would be a bug |
| `ro-loop-round` | PRIMITIVES `passes/mkpass.py sib4` page, passes per frame | `base` page | 3 | 156 (expect 4) *(inference)* |
| `sup-*` (one page) | `@supports`: `event-trigger: --t click()`, `frame-sizing: content-height`, `white-space-collapse: preserve-spaces`, `timeline-scope: all`, `width: inherit(--x)`, `anchor-name: ident(--a 3)`, `display: grid-lanes`, `scroll-snap-type: pair mandatory`, `line-clamp: 2` | `width: if(style(--x: 1): 1px; else: 2px)` (1 since 137) | all 0 | each one ships |
| `harfrust` | a GSUB with 16,400 aliased subtables (PRIMITIVES `aat/mkcap.py`): shaped iff HarfRust | 5 subtables | unshaped | `HarfRustShaping` default |
| `link-subresource-dict` (paint) | needs a server: a CSS file with `Link: <d>; rel=compression-dictionary`, then a probe | `<link>` element | registers | 157 (stops) |

`CSS.supports()` in Chromium 153 *(measured, `exp/sup.js`)*: without flags, every `sup-*` declaration above is
unsupported. Of the other declarations `sup.js` tried, `overflow: scroll clip`, `text-fit: grow`,
`animation-trigger: --t play-forwards` and `timeline-trigger: --t view()` already parse. With
`CSSIdentFunction,CSSInheritFunction,CSSRandomFunction,EventTrigger,CSSTimelineScopeAll,ResponsiveIframes,
CSSGridLanesLayout,CSSContainerProgressNotation,CSSLineClamp` everything flips except `event-trigger` (no CSS
property even with the flag), `preserve-spaces` and `scroll-snap-type: pair` (`test` in 153).

---

## 6. Possible bugs

1. **`anchor()`/`anchor-size()` ignore `ident()` in the anchor name; the renderer crashes.** *(measured in 153 with
   `CSSIdentFunction`; code on main)*
   - `width: anchor-size(ident("--a" 2) width, 7px)`, literal or with `var()`, crashes the page.
   - `CSSMathExpressionAnchorQuery::ToQuery` (`core/css/css_math_expression_node.cc:4092-4096`) does
     `ScopedCSSName(custom_ident->Value(), …)`. For an `ident()`-backed `CSSCustomIdentValue`, `Value()` returns the
     empty `string_` (`css_custom_ident_value.cc:38-43`). It should call `ComputeIdent(length_resolver)` or `Resolve()`
     like `css_to_style_map.cc:361` and `style_builder_converter.cc:2326` do.
   - Spec: css-values-5 §8.8, "ident() can be used anywhere that an identifier is expected".
   - Only behind a `test` flag, so not a shipped bug. Worth an MRE when the flag moves.
2. **`@custom-media` parses but never applies, and its `cssText` drops the name.** *(code + measured)*
   - `@custom-media --wide (min-width: 100px); @media (--wide) {…}` never matches in 153 with `CSSCustomMedia`.
   - On main no caller passes a `CustomMediaRulesMap` (`grep CustomMediaRulesMap` finds only
     `media_query_evaluator.cc`), and `EvalFeature` returns unknown when it's null (`:1664-1675`).
   - `CSSCustomMediaRule::cssText` (`core/css/css_custom_media_rule.cc:47-60`) appends the query but not the name:
     `@custom-media (min-width: 100px)`.
   - Spec: mediaqueries-5 §custom-mq. Incomplete work behind a `test` flag.
3. **Responsive iframes in 153 with the flag**: with the opt-in accepted (`requestResize()` succeeds) the iframe sized
   to 0 for 123 px of content, or stayed 150 px *(measured)*. 153 predates the shipped syntax, so retest on 155+
   before calling it a bug.

Not a bug, but worth knowing: an `animation-timeline` name that resolves to nothing gives the animation a `null`
timeline with its time held at 0, so `fill: both` applies the `from` keyframe *(measured)*. A clash instead gives "no
effect". Code and projects that treat "unresolved" and "clashing" the same are wrong in 153 already.

## 7. Open questions

- Does 156+'s loop-limit repeat add a useful pass or a wasted one for js-minus-js (§2.3)? Needs a trace on a 157
  build. The repo has no 156+ binary; `npx playwright install` is forbidden (memory note), so a CfT 157 zip would be
  the route.
- When `ident()` moves to the ASF model, will Blink keep `ident()` in name-valued properties working without `var()`
  (today's path)? The spec says yes; the implementation will be rewritten.
- Firefox 159's view timelines: do they run the same-frame re-run for stale timelines? bugs/README says no (bug
  2048416, waiting on csswg#12120). §2.3 suggests the spec may settle it in 2027.
- `CSSTimelineScopeGlobal`'s global map is keyed by `(TreeScope, name)` and attaches every matching timeline. Does
  the attach order (`ComparePreorderTreePosition`, `deferred_timeline.cc:30-44`) cost O(k · depth) per attach for
  css-physics's thousands of names? Measure before dropping the scope nests.
