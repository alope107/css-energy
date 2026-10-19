# Engine facts for Chrome 153 (research report, 2026-10-18)

*Source reading only (Chromium M153 branch, HarfBuzz, OTS, HarfRust, chromestatus), no browser runs. `PRIMITIVES.md` says which of these were then measured.*

> **Extended and corrected by [chromium/](chromium/README.md) (2026-10-18):** Q1 (`max_ops` is also charged by
> `unsafe_to_break` spans and, since HarfBuzz 14.4.0, `move_to`; `HB_NO_BORING_EXPANSION` is dead, so avar2 is live:
> chromium/06, 07); Q3 (the cap counts LookupList entries; shaper stages re-run one entry: chromium/07 §2.3); Q6 (the
> loop-limit ResizeObserver round re-runs the lifecycle from 156: chromium/01, 09 §2.3); Q8 (the CORS-anonymous
> dictionary fetch is the flagged path; the default is `cors` + `credentials: omit`: chromium/09 §2.10).

Method: source read at the Chromium **M153 branch** (`refs/branch-heads/8010`, from
`chromiumdash.appspot.com/fetch_milestones?mstone=153`) via `chromium.googlesource.com/.../+/refs/branch-heads/8010/<path>?format=TEXT`,
plus `main` where noted; HarfBuzz/OTS/HarfRust from fresh GitHub clones (HarfBuzz 14.6.0 HEAD; M153 bundles
**HarfBuzz 14.3.1-10, rev dfdc088c**, checked that the constants below are identical at that rev); chromestatus API
(`/api/v0/features/<id>`, stage 160/260 `desktop_first` = shipping milestone). Abbreviation: CS = `https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/`.

---

## Q1. AAT in Chrome web fonts — **AAT tables are dropped from web fonts.** Confidence: high (code)

**OTS config** (`CS/third_party/blink/renderer/platform/fonts/web_font_decoder.cc`, `BlinkOTSContext::GetTableAction`):
```cpp
switch (tag) {
  case kCbdtTag: case kCblcTag: case kColrTag: case kCpalTag: case kCff2Tag: case kSbixTag: case kStatTag:
#if HB_VERSION_ATLEAST(1, 0, 0)
  // Let HarfBuzz handle how to deal with broken tables.
  case kAvarTag: case kBaseTag: case kCvarTag: case kFvarTag: case kGvarTag: case kHvarTag:
  case kMvarTag: case kVvarTag: case kGdefTag: case kGposTag: case kGsubTag:
#endif
    return ots::TABLE_ACTION_PASSTHRU;
  default:
    return ots::TABLE_ACTION_DEFAULT;
}
```
OTS (`ots/src/ots.cc`, `GetTableAction`): `TABLE_ACTION_DEFAULT` → `TABLE_ACTION_DROP` unless the tag is in
`supported_tables[]`; that list has no morx/mort/kerx/trak/feat/ankr (Graphite tags only `#ifdef OTS_GRAPHITE`). So
**morx, kerx, trak, feat, ankr are stripped** before HarfBuzz sees the font. (Locally installed fonts don't go
through OTS, so on macOS a system font's morx still shapes; not usable from a page.) Note **GSUB/GPOS/GDEF are passed
through unsanitized by OTS**; only HarfBuzz's own sanitizer checks them (see Q3). Web-font size cap: 128 MB
decompressed (`kMaxDecompressedSizeMb = 128`).

**HarfBuzz build** (`CS/third_party/harfbuzz/BUILD.gn`; the dir was renamed from `harfbuzz-ng`): defines are
`HAVE_OT HAVE_ICU HAVE_ICU_BUILTIN HAVE_FONTATIONS HB_NO_MMAP HB_NO_RESOURCE_FORK HAVE_HARFRUST HB_NO_PAINT=
HB_NO_SUBSET_LAYOUT HB_NO_SUBSET_CFF HB_NO_FALLBACK_SHAPE HB_NO_UCD HB_NO_WIN1256 HB_NO_BUFFER_VERIFY HB_NO_DRAW
HB_NO_BORING_EXPANSION HB_NO_VAR_COMPOSITES` (+pragma ones). **No `HB_NO_AAT` / `HB_NO_AAT_SHAPE`**: in
`hb-config.hh` those come only from `HB_MINI` / `HB_NO_SHAPER` / `HB_NO_OT_SHAPE`, none defined. `hb-aat-*` sources
are compiled. So AAT shaping is compiled in, but no web font can reach it.

**morx vs GSUB** (`src/hb-ot-shape.cc`):
```cpp
static inline bool _hb_apply_morx (hb_face_t *face, const hb_segment_properties_t &props)
{ /* https://github.com/harfbuzz/harfbuzz/issues/2124 */
  return hb_aat_layout_has_substitution (face) &&
         (HB_DIRECTION_IS_HORIZONTAL (props.direction) || !hb_ot_layout_has_substitution (face)); }
...
bool has_gsub = !apply_morx && hb_ot_layout_has_substitution (face);
```
Horizontal text: **morx wins over GSUB**. Vertical: GSUB wins if present. morx alone: applied. kerx is used
unless both GSUB and GPOS are present (issue 3008). trak needs a STAT table.

**Limits** (`src/hb-limits.hh`, same at M153's rev): `HB_BUFFER_MAX_LEN_FACTOR 256`, `HB_BUFFER_MAX_LEN_MIN 65536`,
`HB_BUFFER_MAX_OPS_FACTOR 4096`, `HB_BUFFER_MAX_OPS_MIN 65536` (`hb_buffer_t::enter`: `max_ops = max(len*4096, 65536)`,
`max_len = max(len*256, 65536)`, len = buffer length at shape start), `HB_MAX_NESTING_LEVEL 64`,
`HB_MAX_CONTEXT_LENGTH 64`. **Chrome doesn't change them**: no `-D` overrides in BUILD.gn, and `harfbuzz_shaper.cc`
only sets language/script/direction on the buffer.
- **AAT StateTableDriver** (`hb-aat-layout-common.hh`): `if (is_not_epsilon_transition || buffer->max_ops-- <= 0)
  (void) buffer->next_glyph ();`. max_ops is only charged for *non-advancing* (DONT_ADVANCE) transitions, and when
  it runs out the driver **forces an advance**; it doesn't stop. Insertion actions charge `max_ops -= count` and
  return when it hits ≤ 0 (`hb-aat-layout-morx-table.hh`). Output growth is capped by max_len (`enlarge` fails →
  `successful=false` → the drive loop `for (...; buffer->successful;)` ends).
- **GSUB**: max_ops is charged only on **nested lookup calls** (`recurse()`: `buffer->max_ops--`, failure →
  `successful=false`; also `if (buffer->max_ops <= 0) break;` before each recursion) and in cluster merges
  (`max_ops -= end - start`). **Top-level lookup passes aren't charged**: each lookup in the map is a full pass
  over the buffer, and nothing caps the number of top-level lookup applications per shaping. Other caps: nesting 64,
  context length 64. `HB_MAX_LOOKUP_VISIT_COUNT 35000`, `HB_MAX_FEATURE_INDICES 8000`, `HB_MAX_LANGSYS 2000`, etc. are
  used only by subset/closure/collect contexts, not shaping. `hb-ot-map.cc` "Sort lookups and merge duplicates":
  the same lookup *index* listed twice in one stage runs once, so S-fold repetition needs distinct LookupList
  indices (aliased offsets, as the repo does).

## Q2. Graphite — **not enabled.** Confidence: high
`CS/third_party/ots/BUILD.gn` neither compiles `silf.cc`/graphite sources nor defines `OTS_GRAPHITE`, so Silf/Glat/
Gloc/Feat/Sill fall to DEFAULT→DROP. `src/src/hb-graphite2.cc` is in HarfBuzz's `unused_sources`. The Blink shaper
list is `{"ot"}` (or `{"harfrust"}`, see below).

### HarfRust (asked by coordinator)
- `harfbuzz_shaper.cc` (M153): `ShapingBackend()` returns `{"harfrust"}` if `RuntimeEnabledFeatures::HarfRustShapingEnabled()`, else `{"ot"}`.
- `runtime_enabled_features.json5`: M153 `{ name: "HarfRustShaping" }` with **no status, so off by default**.
  Like any RuntimeEnabledFeature it can be turned on with `--enable-blink-features=HarfRustShaping` (not verified
  by running). On `main` it's `status: "test"` (tests only). M153 links `//third_party/rust/harfrust/v0_12` (main: v0_14).
- HarfRust (github.com/harfbuzz/harfrust, README): a Rust port matching HarfBuzz 14.5.1. **It supports AAT**
  (`harfrust/src/aat/{morx,kerx,trak,kern}.rs`) but not Graphite. Same buffer limits (`MAX_OPS_FACTOR 4096`,
  `MAX_OPS_MIN 65536`, `MAX_LEN_FACTOR 256`, `MAX_LEN_MIN 65536`, `MAX_NESTING_LEVEL 64`, `MAX_CONTEXT_LENGTH 64`).
  It parses through read-fonts with **no hb_sanitize pass, so I found no 16,384-subtable cap** (only
  `MAX_CACHED_SUBTABLES 8` and `MAX_LIGATURE_DIGEST_WORK 16_384`, both performance knobs). README: "Malformed fonts
  will cause an error", where HarfBuzz falls back. For web fonts **morx is still gone, because OTS strips it before
  any shaper runs**. Confidence: high on code, medium on the flag behaviour.

## Q3. The 16,384 cap is HarfBuzz's, not OTS's; **past it the whole GSUB is dropped.** Confidence: high (code)
- In Chrome OTS **passes GSUB through** (Q1), so OTS's GSUB checks never run. OTS's `layout.cc`/`gsub.cc` have no
  subtable/lookup-count constant anyway (only structural checks such as `kMaxClassDefValue`, `kMaxDeltaFormatType`).
- The cap is `src/hb-sanitize.hh`:
```cpp
#ifndef HB_SANITIZE_MAX_SUBTABLES
#define HB_SANITIZE_MAX_SUBTABLES 0x4000
#endif
  bool visit_subtables (unsigned count)
  { max_subtables += count; return max_subtables < HB_SANITIZE_MAX_SUBTABLES; }
```
  called from `Lookup::sanitize` (`hb-ot-layout-common.hh`): `if (unlikely (!c->visit_subtables (subtables))) return_trace (false);`.
  The count is **cumulative over the whole GSUB sanitize, once per LookupList reference** (aliased lookups count
  every time), and the comparison is strict: total ≤ 16,383 passes.
- What happens past it: there's no neutering any more (the comment says sanitize "no longer" modifies data).
  `OffsetTo::sanitize` fails → `LookupList` fails → `GSUBGPOS::sanitize` returns false → `sanitize_blob` returns
  `hb_blob_get_empty()`. **The entire GSUB table is discarded**, not just the lookups past the cap. The repo's
  observation ("every register read 0") fits that. GSUB accelerators sanitize eagerly (`lazy_some_gpos` is
  GPOS-only).
- A second sanitizer budget can also kill the table: `max_ops = clamp(table_bytes × 64, 16384, 0x3FFFFFFF)`
  (`HB_SANITIZE_MAX_OPS_FACTOR 64`), charged on range checks. Aliased lookups are re-sanitized per reference, so
  heavy aliasing multiplies this cost. (Inference from code; not measured.)
- LookupList count is uint16 (≤ 65,535 lookups). No other HarfBuzz lookup or glyph count limits found for shaping.
  OTS limits don't apply to morx (morx is dropped, not sanitized).

## Q4. CSS features (Chrome milestone = shipped on desktop+Android). M153 `runtime_enabled_features.json5` status in brackets.

| Feature | Shipped | Notes |
|---|---|---|
| `@function` (custom functions) | **139** [CSSFunctions: stable] | Typed params `--x <number>`, defaults, `returns <type>`, locals = custom props in the body, `result:`; `@media`/`@supports`/`@container` allowed in the body (`StyleCascade::FlattenFunctionBody`). Args are resolved eagerly in the **caller's** context and type-coerced; var() in the body looks up locals → args → element custom props → fallback (dynamic scope via parent frame). **Not memoized**, and **no recursion**: cycle detection is keyed on the function itself (`CycleNode{kFunction, function}`), so `--f()` calling `--f()` is invalid even with different args. Output capped at `kMaxVariableBytes` = 2 MiB. Any use makes the element **MPC-uncacheable** (Q5). chromestatus 5179721933651968 |
| `if()` | **137** | Conditions: `style()`, `media()`, `supports()`. Range syntax in `style()`/`if()`: **142** (5184992749289472) [CSSContainerStyleQueriesRange: stable] |
| `sibling-index()` / `sibling-count()` | **138** | Disables MPC (`HasSiblingFunctions`) |
| typed `attr()` (`attr(data-x type(<number>), 0)`, any property) | **133** | `string`→`raw-string` rename 136; short-circuiting var()/attr() 139. Disables MPC (`HasAttrFunction`) |
| `progress()` | **138** [CSSProgressNotation: stable] | `media-progress()`/`container-progress()` only experimental (flag) |
| `random()` | **156** (chromestatus) | **Not in 153**: [CSSRandomFunction: experimental] in M153, stable on main. Element-dependent random disables MPC |
| `ident()` | not shipped | [CSSIdentFunction: test] in 153 and main |
| `@mixin` / `@apply` | not shipped | [CSSMixins: experimental] (needs Experimental Web Platform features) |
| Scroll-triggered animations | **146** (5181996801982464); `trigger-scope` 146 | Properties in M153: `timeline-trigger` (+ `-name`, `-source`, `-activation-range[-start/-end]`, `-active-range[-start/-end]`), `animation-trigger`, `trigger-scope` [AnimationTrigger, TimelineTrigger: stable; EventTrigger: experimental] |
| `scroll-state()` container queries | **133** (stuck/snapped/scrollable); `scrolled` **144** | |
| Anchored container queries `@container anchored(fallback: …)` | **143** | `container-type: anchored` |
| `calc-size()` / `interpolate-size` | **129** | |
| `inherit()` function | not shipped | [CSSInheritFunction: experimental] in 153 and main; chromestatus 5996914579472384 has no milestone |
| Style queries on custom props | 111; range syntax 142; name-only `@container name` 148 | |
| `first-valid()` | **not implemented** | keyword absent from M153 `css_value_keywords.json5`; no chromestatus entry |
| Math | trig 111; `pow/sqrt/hypot/log/exp` **120**; `round/mod/rem` 125; `abs/sign` **138**; **typed arithmetic** (`calc(10em / 1px)` → number) **140** | 140 is the one that matters: length/length yields a `<number>` |

Sources: chromestatus.com/feature/<id> (ids above; others: if() 6313805904347136, sibling 6225478530367488, attr
4680129030651904, progress 5112558941634560, random 5324559251275776, ident 6230159413477376, mixins 5108022310469632,
scroll-state 5072263730167808 / 5083137520173056, anchored 5177580990496768, calc-size 5196713071738880, exp
5118715069202432, sign 5091423843778560, typed arithmetic 4740780497043456); `CS/third_party/blink/renderer/platform/runtime_enabled_features.json5`;
`CS/third_party/blink/renderer/core/css/css_properties.json5`. Confidence: high for flags/statuses, medium-high for
milestones (chromestatus data).

## Q5. Style-engine caching. Confidence: high (code)
- **No caching of `@function` results.** `StyleCascade::ResolveFunctionInto` (`CS/.../core/css/resolver/style_cascade.cc`)
  re-parses args, flattens the body and resolves locals and result on every call, per declaration, per element.
  It also calls `state_.SetHasTreeScopedReference()`, which makes `MatchedPropertiesCache::IsCacheable` return
  false (comment: crbug.com/1473836). **Every element whose style calls a custom function skips the MPC.**
- **MPC** (`matched_properties_cache.cc`) is keyed by the matched declaration blocks (+mixin bindings) and a hash
  of the parent's inherited variables. A hit also needs `ParentStyle()->InheritedEqualIncludingInheritedVariables(entry.parent)`.
  So **per-element-different inherited custom properties defeat it.** `IsStyleCacheable` returns false for: `attr()`,
  non-initial `zoom`, container-relative units (`cqw` etc.), `anchor()`/`anchor-size()`, `sibling-index/count()`,
  functional `@media`/navigation in `if()`/`@function`, element-dependent `random()`. `IsCacheable` also bails for
  tree-scoped references (custom functions, tree-scoped names), shadow-boundary user-modify mismatch, and a
  non-empty cascade filter. `MatchResult` is uncacheable if a declaration block was mutated after hashing (inline
  style edits) or for `@position-try` / try-tactics styles.
- Things that don't bypass the MPC: registered custom properties as such (nothing in mpc.cc mentions them);
  animations, because MPC caches the base style and `ApplyAnimatedStyle` reruns the cascade with interpolations
  on top. Animations do disable the *base computed style reuse* (`StyleResolver::CanReuseBaseComputedStyle`) when
  animating custom properties, revert, font-affecting properties with em units, line-height with lh, zoom,
  `!important` animated properties, or anchor functions/position-try. `@container`-matched rules just change the
  matched set (key); `DependsOnSizeContainerQueries` is set after the MPC step.
- **Registered properties don't cost per element at initial value**: initial values live in one per-document
  `StyleInitialData` (`StyleResolver` sets `builder.SetInitialData(engine.MaybeCreateAndGetInitialData())`); a lookup
  of an unset property falls through to it (`style_cascade.cc` ~L2557). Custom properties are stored in a
  copy-on-write hash-array-mapped trie (`core/style/style_variables.h`), so inheritance is a root-pointer copy with
  an XOR hash for equality. I found no "apply every registered property's initial value on every element" path.
  The per-element cost comes when a property is *set*: parsing/typing a registered value and computing it.

## Q6. Style+layout passes per frame for scroll timelines. Confidence: high (code)
`CS/third_party/blink/renderer/core/frame/local_frame_view.cc`, `UpdateLifecyclePhasesInternal`:
```cpp
// RunPostLayoutSnapshotClientSteps must not run more than once.
bool should_run_post_layout_snapshot_client_steps = true;
...
while (true) {
  bool run_more_lifecycle_phases = RunStyleAndLayoutLifecyclePhases(target_state);
  ...
  if (should_run_post_layout_snapshot_client_steps) {
    should_run_post_layout_snapshot_client_steps = false;
    bool needs_to_repeat_lifecycle = RunSnapshotPostLayoutStateSteps(target_state, reason);
    if (needs_to_repeat_lifecycle) continue;
  }
  ... RunPostLayoutIntersectionObserverSteps ... RunResizeObserverSteps ...
  if (needs_to_repeat_lifecycle) {
    if (RuntimeEnabledFeatures::RunSnapshotPostLayoutStateStepsEnabled())
      should_run_post_layout_snapshot_client_steps = true;
    continue;
  }
```
- There's no numeric constant. The cap is the **one-shot boolean**. At frame start, `ServiceScrollableAreas`
  snapshots timelines (`GetFrame().UpdatePostLayoutSnapshotClientsForServiceAnimations()`, used because
  `SnapshotScrollTimelinesPostLayout` is off in 153 and main; `RunSnapshotPostLayoutStateSteps` is stable). Then:
  style+layout **pass 1** → post-layout snapshot (`LocalFrame::UpdatePostLayoutSnapshotClients`: `valid &= !client->UpdateSnapshot()`)
  → if any timeline changed, **pass 2** → no more re-snapshots. A third change uses stale state until the next
  frame. That matches the repo's "two per frame, a third on stale state".
- **Re-arm path** (code-backed lead, not tested): `should_run_post_layout_snapshot_client_steps` is set back to
  true whenever `RunResizeObserverSteps` returns true. That function returns true for
  `StyleEngine::UpdateLastSuccessfulPositionFallbacksAndAnchorScrollShift()` (anchor positioning "last successful
  position option") or `NotifyResizeObservers()`. The RO controller also exists for the internal
  `Document::intrinsic_size_observer_` used by `contain-intrinsic-size: auto`. RO loops are bounded by the
  increasing-depth rule (`GatherObservations` min_depth, loop-limit error). So pure-CSS anchor fallback changes, or
  `contain-intrinsic-size:auto` elements resizing at increasing depth, may buy extra snapshot+style+layout
  rounds in one frame.

## Q7. Container-query and anchor restyles inside layout. Confidence: high (code)
- `BlockNode::Layout` (`CS/.../core/layout/block_node.cc`) calls
  `StyleEngine::UpdateStyleAndLayoutTreeForSizeContainer(*element, available_size, ContainedAxes())` **on every
  layout-cache miss of a size container** (first fragment). `ContainerQueryEvaluator::SizeContainerChanged` returns
  `kNone` if size and axes are unchanged, else recomputes. Any change, or any change at all if the container is
  referenced by cq units (`referenced_by_unit_ → kDescendantContainers`), runs `RecalcStyleForSizeContainer`, an
  interleaved style recalc of the subtree, then layout-tree rebuild and layout continue. **No counter or limit.**
- Chained containers: the outer recalc skips descendant containers' subtrees (`SkippedStyleRecalc`). Each inner
  container resumes recalc when *it* is laid out, **in the same layout pass**. So N nested size containers give N
  interleaved recalcs per pass, plus extra recalcs whenever a container is laid out again at a different size
  within the pass (flex/grid measure passes).
- Anchor positioning: `out_of_flow_layout_part.cc`: `constexpr unsigned kMaxTryAttempts = 5 + 1;` per
  out-of-flow element. Each attempt calls `UpdateStyleAndLayoutTreeForOutOfFlow` (a style recalc) and
  `TryCalculateOffset`. The loop can run twice when the last-successful option no longer fits.
  `anchor()`/`anchor-size()` are evaluated during that offset/size computation, with no iteration. Anchor
  functions make the style MPC-uncacheable.

## Q8. Cloudflare `_headers`, Early Hints, Chrome's Link-header dictionary fetch
- **Cloudflare docs** (developers.cloudflare.com/workers/static-assets/headers/): arbitrary `name: value` headers,
  `!` removes, ≤ 100 rules, ≤ 2,000 chars per line, repeated headers joined with `, `, `_headers` not applied to
  Worker-generated responses. **No list of forbidden headers; `Link` and `Set-Cookie` aren't mentioned.** `Link`
  works in practice (the repo's paint deploy already relies on it, `deploy/README.md`). Set-Cookie: **unknown**
  (not documented; would need a test deploy).
- **103 Early Hints** (developers.cloudflare.com/cache/advanced-configuration/early-hints/): a per-**zone** setting;
  caches only `Link` with `rel=preload`/`preconnect` from 200/301/302 responses for `.html/.htm/.php`/extensionless
  URIs, HTTP/2 and HTTP/3 only. Whether it applies on `*.workers.dev`: **unknown** (zone setting; docs silent).
  Either way **Chrome ignores `rel=compression-dictionary` in a 103**: `CS/content/browser/loader/navigation_early_hints_manager.cc`
  handles only `kPreconnect`, `kPreload`, `kModulePreload` (`// TODO(crbug.com/40496584): Support other rel attributes`). Confidence: medium-high.
- **Chrome and the `Link: <…>; rel=compression-dictionary` header on a document**: yes, it fetches a dictionary.
  `Document::CheckCompletedInternal` → after load completes → `FetchDictionaryFromLinkHeader()` →
  `DispatchLinkHeaderPreloads(..., kDocumentAfterLoadCompleted)`. `IsCompressionDictionaryLoadAllowed` is false for
  every pre-load mode and true only for `kDocumentAfterLoadCompleted` (and for subresource headers not served from
  the memory cache; `kRestrictLinkHeaderOnSubresource` is disabled by default). `PreloadHelper::FetchCompressionDictionaryIfNeeded`
  queues a `LoadDictionaryWhenIdleTask` (requestIdleCallback-style) that calls `LinkDictionaryResource::Fetch`,
  destination `compression-dictionary`, CORS anonymous (`CDTNewCrossOriginHandling`).
  - **bfcache restore**: no new load → no `CheckCompletedInternal` → **no fetch** (inferred from the code path).
  - **History navigation without bfcache**: the document's response headers are processed again after load. The
    fetch then uses the **default cache mode**, because `frame_fetch_context.cc` `DetermineFrameCacheMode` says
    "Does not propagate cache policy for subresources after the load event":
    `if (local_frame->GetDocument()->LoadEventFinished()) return mojom::FetchCacheMode::kDefault;`, while before the
    load event `kBackForward`/`kRestore` → `kForceCache`. That explains the repo's finding that CSS fetches on
    Back/Forward come from cache but the link dictionary goes to the network. **General corollary: any fetch a
    back/forward-loaded document starts after its load event (lazy images, late `mask-image`, etc.) gets normal
    HTTP-cache semantics, not force-cache.**

## Q9. `<img>` fallback, pending size, `content:url()`. Confidence: high (code); visual result not run here
- **Failure** (network error such as `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER`, or a decode error, both of which
  set `ImageResourceContent::ErrorOccurred()`): `HTMLImageLoader::ImageNotifyFinished` →
  `HTMLImageElement::OnImageLoadComplete` → `ResetLayoutDisposition` → (not potentially available) →
  `EnsureCollapsedOrFallbackContent` → `kFallbackContent`, unless `error->ShouldCollapseInitiator()` (blocked
  loads) → `kCollapsed` (`display:none`). Fallback creates a **`LayoutBlockFlow`** (not `LayoutImage`) with a UA
  shadow tree (`html_image_fallback_helper.cc`): `span#alttext-container` > `img#alttext-image` (16×16 broken
  icon, floated left in a flow-root) + `span#alttext` holding the alt text. With no width/height and a non-empty
  alt, `AdjustHostStyle` resets width/height/aspect-ratio to auto (for display:inline). So the box is an atomic
  inline whose **width ≈ 16 px icon + alt-text width**: real text layout, measurable. With `src` set and `alt=""`
  it "represents nothing" (icon hidden, empty, 0 width). With width+height set and no alt (or quirks mode) it's
  treated as replaced (`TreatImageAsReplaced`); the icon shows only if both sides are ≥ 18 px.
- **Pending**: `ImageIsPotentiallyAvailable()` is true while loading, so `kPrimaryContent` → `LayoutImage`.
  `LayoutImage::UpdateNaturalSizeIfNeeded`: "If the image resource has no image or image dimensions then we set
  natural dimensions of 0x0". **Without width/height a pending `<img>` is 0×0**, and no alt text is shown while
  loading. Exceptions: `sizes="auto"` gets UA `contain: size; contain-intrinsic-size: 300px 150px`; with no
  src/empty URL and non-empty alt, `NoImageResourceToLoad` → immediate fallback.
- **`content: url()` on a non-replaced element**: `LayoutObject::CreateObject` makes a `LayoutImage` with
  `LayoutImageResourceStyleImage`. On error, `UpdateNaturalSizeIfNeeded` doesn't update (`if (!ErrorOccurred())`),
  so it **stays 0×0 for both pending and failed**. The fallback-to-alt switch (`EnsureFallbackForGeneratedContent`)
  exists only for `HTMLImageElement`. **I found no CSS-observable layout difference between pending and failed**
  for non-img elements (paint may differ). For `<img>` with `content:url()`: `CreateLayoutObject` uses the content
  image only `if (!content_image->GetImage()->ErrorOccurred())`, else the img's own disposition. No
  `:broken`-style pseudo-class exists. Confidence: medium-high.

## Q10. MathML stretchy operators — **yes, OpenType MATH glyph assembly, observable in layout.** Confidence: high
- MathML Core shipped in Chrome 109. OTS **sanitizes** MATH (it's in `supported_tables`, not passthrough).
  `CS/third_party/blink/renderer/platform/fonts/shaping/stretchy_operator_shaper.cc`: first tries MathVariants
  glyph variants (first variant whose ink extent ≥ target), else a GlyphAssembly via HarfBuzz
  (`hb_ot_math_get_min_connector_overlap`, assembly parts):
```cpp
unsigned repetition_count = base::saturated_cast<unsigned>(std::max<float>(
    std::ceil((target_size - non_extender_advance_sum +
               min_connector_overlap * (non_extender_count - 1)) /
              extender_non_overlapping_advance_sum), 0));
repetition_count = std::min<unsigned>(repetition_count,
    (HarfBuzzRunGlyphData::kMaxGlyphs - non_extender_count) / extender_count);   // kMaxGlyphs = 1<<15 = 32768
...
connector_overlap = max(min_connector_overlap, min(max_connector_overlap, (sum - target)/(glyph_count-1)));
stretch_size = non_extender_advance_sum + r*extender_advance_sum - connector_overlap*(glyph_count-1);
```
- The size feeds `MathOperatorLayoutAlgorithm` (target from the mrow's stretch ascent/descent or munderover inline
  size, clamped by `minsize`/`maxsize`, `symmetric`). It's a real layout size. **To expose `ceil()`, make the overlap
  non-adjustable** (MathConstants `minConnectorOverlap` = the parts' connector lengths), so the size becomes a step
  function of the target: `nonExt + r·(ext − o) − o·(nNonExt − 1)` with `r = ceil(...)`, capped at 32,768 glyphs.
  (Design inference; not run.)

---
### Source URLs
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/platform/fonts/web_font_decoder.cc
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/harfbuzz/BUILD.gn , …/README.chromium
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/ots/BUILD.gn
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/platform/fonts/shaping/harfbuzz_shaper.cc , …/stretchy_operator_shaper.cc , …/glyph_data.h
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/platform/runtime_enabled_features.json5
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/css/resolver/{style_cascade.cc,style_cascade.h,matched_properties_cache.cc,.h,style_resolver.cc,match_result.cc}
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/style/style_variables.h
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/frame/{local_frame_view.cc,local_frame.cc}
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/css/{style_engine.cc,container_query_evaluator.cc} , …/core/layout/{block_node.cc,out_of_flow_layout_part.cc,layout_image.cc,layout_object.cc}
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/html/{html_image_element.cc,html_image_fallback_helper.cc,html_image_loader.cc}
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/third_party/blink/renderer/core/loader/{preload_helper.cc,frame_fetch_context.cc,image_loader.cc} , …/core/dom/document.cc
- https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/content/browser/loader/navigation_early_hints_manager.cc
- https://github.com/harfbuzz/harfbuzz (src/hb-limits.hh, hb-sanitize.hh, hb-ot-shape.cc, hb-aat-layout-common.hh, hb-ot-layout-gsubgpos.hh, hb-ot-layout-common.hh, hb-ot-map.cc, hb-config.hh)
- https://github.com/khaledhosny/ots (src/ots.cc)
- https://github.com/harfbuzz/harfrust (README.md, harfrust/src/buffer.rs, ot/layout.rs, aat/)
- https://chromiumdash.appspot.com/fetch_milestones?mstone=153 ; https://chromestatus.com/feature/<ids in Q4>
- https://developers.cloudflare.com/workers/static-assets/headers/ ; https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
