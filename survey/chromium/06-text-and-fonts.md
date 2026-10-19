# 06. Text and fonts: Blink from CSS to HarfBuzz and back

*Source read at Chromium main `22b3b159` (M158) and the M153 branch (8010); 155 (8059) and 157 (8103) single files
from gitiles. HarfBuzz at 14.5.1-141 (`12ee77ee`, what 157 and main bundle; 153 bundles 14.3.1-10, 155 14.4.0-86).
Skia (`src/ports/SkTypeface_fontations.cpp`, `src/core/SkStrikeSpec.cpp`, `src/ports/fontations/src/*.rs`) and
Fontations/HarfRust from their repos. Experiments in headless Chromium 153.0.8010.12 on the shared mini PC (load
average 5–7 from other agents throughout: read ratios, not absolutes), files in
`exp/06/exp/` (relative to `survey/chromium/`).* Paths: `F/` = `third_party/blink/renderer/platform/fonts/`,
`L/` = `third_party/blink/renderer/core/layout/`, `C/` = `third_party/blink/renderer/core/`, `hb:` = HarfBuzz.

HarfBuzz internals (lookup application, sanitizer, buffer limits, mask bits) are chapter
[07-harfbuzz.md](07-harfbuzz.md); inline layout and line breaking [05-layout.md](05-layout.md); counter-style
algorithms and the counter walk's general cost [03-values-and-properties.md](03-values-and-properties.md).

## Findings

1. **A CPU shaping in Chrome is ~99% HarfBuzz.** The same 1,274-glyph line shaped with `"cv01" 0` (no CPU lookups)
   costs 0.15–0.33 ms in `InlineNode::ShapeTextIncludingFirstLine` against 21.9–28.7 ms with the lookups on. Blink's
   wrapper (segmentation, buffer fill, Skia advance callbacks, `ShapeResult` construction, the split into ~1,300
   item results) is under 0.3 ms. *(measured)*
2. **Counter-driven text can't be chained inside one layout pass; `content: if()` text can.** `LayoutCounter` text
   changes only in `StyleEngine::UpdateCounters()`, which runs before layout and once after it, never inside the
   size-container recalcs that happen during layout. The prior survey's "K shapings in one layout pass" (PRIMITIVES
   finding 3) was measured with counters and a checker whose `getBoundingClientRect()` calls forced extra passes:
   watched with a ResizeObserver, a counter chain advances one level per lifecycle iteration (K = 8: 48, 40, …, 0
   bad values over 7 iterations). The same chain with `content: if(style(--d: n): "…")` is exact at every frame in a
   single `Layout`. *(code + measured)*
3. **ENGINE_NOTES 43's cause:** one glyph's advance is an `int32` 16.16 number of pixels twice over:
   `SkiaScalarToHarfBuzzPosition` = `ClampTo<int>(px × 65536)` (`F/skia/skia_text_metrics.h:61`) and
   `HarfBuzzRunGlyphData::advance` is a `TextRunLayoutUnit` = `FixedPoint<16, int32_t>`
   (`platform/geometry/layout_unit.h:474`). Measured at 1 unit = 1 px: 32,767 → 32,767; 32,768, 40,000 and 65,535
   all → 32,768 (saturation, not wrap); two 32,767-unit glyphs in one span → 65,534 (the cap is per glyph).
   *(code + measured)*
4. **ENGINE_NOTES 29's mechanism is configuration-dependent.** Blink rounds advances and offsets to whole pixels
   only when Skia's subpixel flag is off; on Linux it is forced on unless hinting is `full`
   (`F/web_font_render_style.cc:108`), on Windows it follows anti-aliasing. Headless 153 keeps fractional advances
   exactly (a 1003-unit glyph at 16 px: 15.671875 px each, 100 of them 1,567.1875 px). The integer rule is still
   right for portability; it isn't how this test browser works. *(code + measured)*
5. **Web fonts on Linux go through Fontations (Skia `SkTypeface_Fontations`), not FreeType, since M133**
   (`FontationsFontBackend` experimental in 132, stable in 133, flag removed by 138; chromestatus "Secure Rust Font
   Stack", 133). HarfBuzz still shapes and maps characters through its own cmap; Skia/Fontations supply advances,
   extents, ascent, x-height and cap-height. *(code + docs)*
6. **Every new variation instance is a new `SkTypeface`, a new `hb_face_t` and a new strike.** Blink keys HarfBuzz
   data by typeface id (`HarfBuzzFontCache`, weak), and a Fontations clone with different coordinates is a new
   typeface, so GSUB/GPOS are re-sanitized and shape plans recompiled per instance; the coordinates are normalized
   three times (Skia twice, HarfBuzz once). Measured: ~15 µs per new instance at 2 axes, ~30–35 µs at 8 axes
   (tiny font, `1ch` + `1ex`); `text-rendering: geometricPrecision` (no hinting) didn't change it. Instances are
   cached in weak maps keyed by exact values: repeats are ~2–4 µs. *(code + measured)*
7. **HarfRust in Chrome 153 costs 1.65× HarfBuzz per CPU shaping** (36.1–37.9 vs 21.9–22.8 ms, interleaved, same
   page). It is `status: "test"` from 155 on (on in content_shell, so in Blink's web tests; no Finch feature, no
   chromestatus entry), main bundles HarfRust 0.14 against 153's 0.12, and 0.12 → HEAD carries a long run of
   performance work (cached lookups, mark-filtering-set bitmaps, context-rule caches) relevant to the CPU font.
   No 16,384-subtable cap: HarfRust reads the raw tables through `hb_face_reference_table`. *(measured + code)*
8. **The CPU line costs ~3–4 ms per pass outside HarfBuzz:** counters (`UpdateLayoutTree` self time 1.25–1.8 ms on
   counter-changing passes on the real page, ~0.08 ms otherwise) and inline layout of ~2,000 items (~1.1–1.7 ms for
   the page's 173-span structure). Hidden text is never painted; its ink bounds are still computed. *(measured)*
9. **Shaping results are never memoized for web fonts.** `NGShapeCache` (≤ 30 UTF-16 units, 2,048 entries) is off
   whenever the font list has a custom font (`F/font_fallback_list.cc:253`). Within a paragraph, a shaping range is
   skipped only if none of its items changed and its text is identical. *(code)*
10. **Feature values pass through Blink untouched** (`static_cast<uint32_t>`, `F/shaping/font_features.cc:215`) and
    switch lookup sets without a new font instance; axes (FeatureVariations) cost an instance per value. HarfBuzz
    keeps 8 bits of a feature value (`hb:src/hb-ot-map.hh:35`; chapter 07). *(code)*
11. **Exact advances at sizes > 256 px need a power-of-two upem.** Skia measures such glyphs on a canonical 64 px
    path strike and scales back (`SkStrikeSpec::MakeCanonicalized`). Measured, upem 1000 at 1,000 px: a 12,288-unit
    glyph reads 12,287.984375 and 64 of them drift −1.31 px; the same font at 250 px is exact; upem 1024 at 1,024 px
    is exact. This answers chapter 03's open question about the 1000-upem drift. *(measured + code)*

---

## 1. How it works

### 1.1 The pipeline at a glance

```
@font-face src ──► FontResource (fetch; data: URLs too) ──► DecodeWebFont: WOFF2 → sfnt (≤128 MB) → OTS
                                                              (GSUB/GPOS/GDEF/variation tables passed through)
      ──► WebFontTypefaceFactory → SkTypeface_Fontations (Linux/Android/ChromeOS)  = FontCustomPlatformData
style: font-* properties ──► FontDescription ──► Font ──► FontFallbackList ──► CSSFontSelector
      ──► CSSSegmentedFontFace / CSSFontFaceSource tables (weak, keyed by FontCacheKey)
      ──► GetFontPlatformData: makeClone(variations, palette) ──► FontPlatformData ──► SimpleFontData
              (metrics: ascent, x-height, cap-height, '0' advance; HarfBuzzFace → hb_face/hb_font per typeface)
DOM text / ::before content / counters ──► LayoutText ──► InlineNode::PrepareLayout
      CollectInlines → SegmentText → ShapeText: one HarfBuzzShaper::Shape per shaping range
            RunSegmenter → ShapeSegment (fallback queue) → hb_buffer_add_utf16 → hb_shape_full(features,
            {"ot"} or {"harfrust"}) ⇄ font funcs → Skia strike (advances, extents) → ShapeResult (runs)
      → CopyRanges into per-item ShapeResults → LineBreaker (ShapeResultView, SnappedWidth) → FragmentItems
paint (visible items only) ──► ShapeResultBloberizer → SkTextBlob
```

### 1.2 Loading and decoding

- `FontResource::GetCustomFontData` decodes on first use (or takes a background-decoded result:
  `kBackgroundFontResponseProcessor`, a parameter of `kBackgroundResourceFetch`, both on by default) →
  `DecodeWebFont` (`F/web_font_decoder.cc`). Caps: input and output ≤ `kMaxDecompressedSizeMb = 128` (`:65`); WOFF2
  is expanded with `woff2::ConvertWOFF2ToTTF`, then OTS sanitizes. `BlinkOTSContext::GetTableAction` passes
  through CBDT, CBLC, COLR, CPAL, CFF2, sbix, STAT, avar, BASE, cvar, fvar, gvar, HVAR, MVAR, VVAR, GDEF, GPOS, GSUB
  unsanitized (`:160-186`); everything else follows OTS's default (drop unknown tables: no morx/kerx/trak, no
  Graphite; prior survey Q1). Unchanged 153 → main except the IFT branch (`DecodeFontWithIft`,
  `IncrementalFontTransfer`, test only). *(code)*
- `WebFontTypefaceFactory::CreateTypeface` (`F/web_font_typeface_factory.cc`): on Linux every web font, plain or
  variable or color, becomes `SkTypeface_Make_Fontations(data)` (`:57`). History: `FontationsFontBackend` experimental
  in M132 (branch 6834), stable in 133 (6943), still a flag in 137, removed and unconditional by 138 (7204; checked
  at each branch head). The OTS-sanitized bytes are shared, not copied, by every later clone. *(code)*
- `font-display` timers: 100 ms short, 3 s long (`C/loader/resource/font_resource.cc:79-80`). A `data:` font is
  never "low priority" (`:416`). js-minus-js checks readiness with its `fok` sentinel instead, which is right: the
  first shaping also pays the HarfBuzz face setup (GSUB sanitize, shape-plan compile). *(code)*

### 1.3 Instances, caches and what a new axis value costs

`FontDescription::CacheKey` (`F/font_description.cc:308`) builds a `FontCacheKey` from: the effective size floored
to 1/100 px (`floorf(size × 100) / 100`, `:279`; `kFontSizePrecisionMultiplier = 100`, `F/font_cache_key.h:54`), a
bitfield (emoji variant, synthesis, optical sizing, synthetic bold/italic, `text-rendering`, orientation, subpixel
flag), the selection request, the device scale factor (Linux/ChromeOS), `size-adjust`, **`font-variation-settings`
(exact float values)**, the palette and `font-variant-alternates`. **Not in it:** `font-feature-settings`,
`font-kerning`, `font-variant-*` other than alternates, `letter-spacing`. Those change the `Font` (and break shaping
ranges, §1.5) but reuse the same `SimpleFontData`. *(code)*

Lookup chain for a web font: `Font` → `FontFallbackList` (one per distinct `FontDescription`, shared through
`FontFallbackMap`) → `CSSFontSelector` → `CSSSegmentedFontFace::GetFontData` (table
`HeapHashMap<FontCacheKey, WeakMember<SegmentedFontData>>`, `C/css/css_segmented_font_face.h:120`) →
`CSSFontFaceSource::GetFontData` (table `HeapHashMap<FontCacheKey, WeakMember<SimpleFontData>>`,
`C/css/css_font_face_source.h:120`). **No size limit, no LRU: entries live while some `Font` holds them and die at
the next Oilpan GC after that.** The source's comment says it outright: "in variable font animations, this number
grows rapidly" (`css_segmented_font_face.cc:92-102`). *(code)*

On a miss, per instance *(code)*:

| Step | Where | Cost driver |
|---|---|---|
| probe fvar/CFF2, four `RetrieveVariationDesignParametersByTag` (wght, wdth, ital, slnt), each copying all axes | `F/font_custom_platform_data.cc:132-230` | O(axes) × 4 |
| coordinate list: wght, wdth, slnt (+ital), every `font-variation-settings` entry, `opsz` = specified size if `font-optical-sizing: auto` and no explicit opsz (`:244`) | same | O(settings) |
| `makeClone` (`:263`) → Fontations `onMakeClone`: fuse with current position (nested loop axes × args), normalize, and if the coordinates differ `MakeFromData`: parse table directory, cmap mapping index, **normalize again**, font style, outline collection, palette | Skia `SkTypeface_fontations.cpp:1003-1050, 162-232` | O(axes × args) + 2 normalizations (fvar + avar/avar2) |
| `FontPlatformData` (render style query) | `F/font_platform_data.cc:90` | small |
| `SimpleFontData`: `font_.getMetrics` → new strike/scaler context (Fontations hinting instance unless `kNone`; MVAR deltas for x-height, cap-height) | `F/simple_font_data.cc:128` | regions × axes |
| `OpenTypeBaselineMetrics m(GetHarfBuzzFace())` → **new `hb_face_t` over the shared bytes, `hb_font_create`, `hb_font_set_variations` (third normalization, avar2 included)**, three BASE lookups | `:219`, `F/shaping/harfbuzz_face.cc:622-671` | O(axes) |
| space and `'0'` glyphs through HarfBuzz cmap, their advances through Skia (HVAR deltas) → `ZeroWidth` (`1ch`) | `:240-245` | regions × axes per glyph |
| first shaping with this instance: GSUB/GPOS/GDEF sanitize + accelerators + shape plan, all per `hb_face_t` | HarfBuzz | ∝ table size (chapter 07) |

`HarfBuzzFontCache::GetOrCreate` (`F/shaping/harfbuzz_face.cc:673`) is keyed by `FontPlatformData::UniqueID()` =
the typeface's id, so every clone gets its own face, its own lazily sanitized tables and its own shape-plan cache
(`hb_shape_plan_create_cached2` keys plans by face, segment properties, user features and coordinates). Fontations'
`onMakeClone` returns the same typeface when the normalized coordinates are equal, so two CSS values that normalize
to the same F2DOT14 share HarfBuzz data. *(code)*

Measured (`exp/06/exp/vf/`, 400 elements each with its own `font-variation-settings` per frame, `width: 1ch;
height: 1ex`, glyf font with HVAR+MVAR built by `mkvf.py`; medians of `Document::recalcStyle`):

| Font | Fixed coordinates (cache hits) | New coordinates every frame | Per new instance |
|---|---|---|---|
| 2 axes | 0.9 ms | 6.7–7.2 ms | ~15 µs |
| 8 axes | 2.3 ms | 14.3–16.4 ms (two runs 22.8–23.1) | ~30–35 µs |
| 8 axes, `text-rendering: geometricPrecision` | | 15.6–23.1 ms | no consistent difference |

css-physics BENCHMARKS §3 has 47 µs at 8 axes/4 regions and 106 µs at 64 axes/200 regions on a different font set;
consistent. Two Fontations fixes landed after 153's read-fonts (0.41, rev `cd4aaef`, 2026-07-03): avar application
went from O(n²) to O(n) (`73fd5ce`, 2026-08-11) and fvar normalization from O(axes × coords) to sorted search past 64
axes (`78aa50d`, 2026-08-12). 155 ships read-fonts 0.43.3 with both; 157/main 0.45. This is the likely substance of
the "Fontations avar2 cost ~axes³" note (ENGINE_NOTES 33, bugs/README.md), each instance normalizing three times.
*(code; the link to the note is inference)*

### 1.4 Metrics as values: `ch`, `ex`, `cap`, `ic`, `font-size-adjust`

- `1ch` = `FontMetrics::ZeroWidth()` (`C/css/css_to_length_conversion_data.cc:125`) = advance of the cmap glyph for
  `'0'` (`SimpleFontData::PlatformGlyphInit`), via `SkFontGetWidthForGlyph` (rounded only if not subpixel). `1ex` =
  Skia `fXHeight` (OS/2 sxHeight + MVAR `xhgt`), fallback 0.56 × ascent; `1cap` = `fCapHeight` (+ MVAR `cpht`);
  `1ic` = advance of U+6C34. All floats, no rounding on Linux with subpixel on. *(code)*
- `font-size-adjust` is a division primitive *(code)*: `FontBuilder::UpdateAdjustedSize` builds a temporary `Font`
  at the computed size (`C/css/resolver/font_builder.cc:395`), reads one metric of its primary font, and sets
  `adjusted = value / (metric / size) × computed` (`C/css/font_size_functions.cc:296`). The element's `1ex`/`1cap`/
  `1ch` then come from the adjusted instance, so with `font-size-adjust: cap-height k`, `1ex` = k × size ×
  xh(axes) / cap(axes): **a ratio of two axis-dependent metrics at style time**, at the price of two instances per
  new value. `em` stays the computed size. Missing metric → aspect 1.0.
- `font-size` is clamped at `kMaximumAllowedFontSize = 10000` px after zoom (`C/style/computed_style_constants.h:487`)
  and floored to 1/100 px for the instance (above). `font-optical-sizing: auto` sets `opsz` to the specified size
  in CSS px, a free second input when the font has an opsz axis. *(code)*

### 1.5 From text to shaping ranges, and when Blink reshapes

`InlineNode::PrepareLayoutIfNeeded` (`L/inline/inline_node.cc:622`) re-collects the whole inline formatting context
when the block `NeedsCollectInlines` (any text change, any font change on any item): `CollectInlines` → `SegmentText`
→ `ShapeTextIncludingFirstLine(data, previous_text)` (`:648-660`). `InlineNode::SetTextWithOffset` (`:991`) has an
incremental path that reuses glyphs outside an edit using HarfBuzz's unsafe-to-break flags, but it bails out when a
`LayoutText`'s whole text changes (`:999`), which is always the case for a one-character counter or `content`
string. *(code)*

`ShapeText` (`:1541`) walks the items and grows a **shaping range** while it sees text items with the same `Font`
(`*font != start_font` breaks, `:472-491`), the same direction and run segment, and open/close tags without inline
padding, margin, border or non-baseline `vertical-align` (`:494-527`). It breaks at control items (`\n`, `\t` in
`pre`, `:1628`), a ZWNJ at an item's start, symbol markers, and any other item type (atomic inlines, floats,
out-of-flow boxes, **bidi controls**: ENGINE_NOTES 49's `unicode-bidi: isolate` div). One range = one
`HarfBuzzShaper::Shape` over the paragraph's text with offsets, so HarfBuzz sees glyphs across span boundaries
(ENGINE_NOTES 30), and the result is split per item with `ShapeResult::CopyRanges` (`:1769`). *(code)*

A range is skipped only if `previous_text` exists, no item in it `NeedsShaping`, and its text equals the previous
text at the same offsets (`:1677-1700`). So in a block with several ranges, unchanged ranges keep their results;
a changed range is reshaped whole. `ReusingTextShaper` (`:151`) can splice old results at safe-to-break points
only on the `SetTextWithOffset` path. `IsNGShapeCacheAllowed` (`:1453`) requires a single text-only context and
`Font::HasSimpleFontFeatures()`, which is false for any custom font (`F/font_fallback_list.cc:253`): the per-font
`NGShapeCache` (`F/shaping/ng_shape_cache.h:133`, ≤ 30 units, ≤ 2,048 entries) never serves web fonts. *(code)*

### 1.6 `HarfBuzzShaper`: segmentation, buffer, features

- 8-bit text skips segmentation (Latin, horizontal, `kText`); 16-bit text runs `RunSegmenter` (script runs, emoji
  presentation; orientation only for `vertical-mixed`) over the whole string (`F/shaping/harfbuzz_shaper.cc:1087`).
  Inline layout pre-segments in `SegmentText` and calls the overload taking a `RunSegmenterRange`. Supplementary
  PUA characters (js-minus-js uses U+F0001–U+F16A8) make the line 16-bit and two code units per glyph. *(code)*
- `ShapeSegment` (`:889`) runs a reshape queue over the fallback list: shape with font k, commit clusters with
  non-zero glyphs, queue `.notdef` clusters for font k+1 (`ExtractShapeResults`). A font that covers everything
  costs one `hb_shape_full`. A character missing from the web font starts a system-font search through
  `FontFallbackIterator` on every shaping. *(code)*
- Buffer: `CaseMappingHarfBuzzBufferFiller` → `hb_buffer_add_utf16(whole text, start, length)` so HarfBuzz gets up
  to five code points of pre/post context; clusters are UTF-16 offsets. Language = `font-language-override` or the
  locale; script from the segment; direction LTR/RTL/TTB (`:311-347`). **No buffer flags** (no BOT/EOT, no
  `PRODUCE_UNSAFE_TO_CONCAT`), default cluster level. Buffers come from a per-thread pool (`kInlineCapacity` 2 in
  153, 8 from 157). *(code)*
- Features (`F/shaping/font_features.cc`): `font-kerning: none` → `kern`/`vkrn` 0; `letter-spacing` ≠ 0 or
  `optimizeSpeed` with `normal` ligatures → `liga` 0, `clig` 0, `calt` 0; `font-variant-*` → their tags;
  `font-feature-settings` appended in order with the CSS integer cast to `uint32_t` (`:215`); `chws` by default
  under `text-spacing-trim`; resolved `font-variant-alternates` prepended (`harfbuzz_shaper.cc:328-338`). All global
  (`start 0, end −1`). `text-rendering: optimizeSpeed` does **not** turn off GSUB in general, only those three
  features. *(code)*
- `hb_shape_full(hb_font, buffer, features, n, ShapingBackend())` (`:353`), the backend being `{"harfrust"}` if
  `HarfRustShaping` else `{"ot"}` (`:78`). **The return value is ignored.** If the face isn't subpixel, every
  position is rounded to whole pixels in 16.16 (`RoundHarfBuzzBufferPositions`, `:289-307`). *(code)*

### 1.7 Font funcs: what HarfBuzz asks Skia, per glyph

`CreateHarfBuzzFontData` (`F/shaping/harfbuzz_face.cc:644`) makes an `hb_ot` font (HarfBuzz's own cmap, GDEF,
variations) and a sub-font whose funcs override (`CreateFontFunctions`, `:555-580`): nominal glyph(s) and variation
glyph (Blink logic for `unicode-range`, emoji presentation and U+2028/2029, then the parent's cmap), **horizontal
advances**, vertical advance/origin, and **glyph extents**. Per shaping on the CPU line *(code)*:

- nominal glyphs: one batched call (`HarfBuzzGetNominalGlyphs`, new in 157; in 153 HarfBuzz falls back to one
  callback per character);
- advances: one batched call (`hb_ot_position_default` → `get_glyph_h_advances`, `hb:src/hb-ot-shape.cc:1011`) →
  `SkStrikeRef::getWidthsStrided` (one strike, held by `HarfBuzzFontData::strike_ref_` and reset only when the
  `SkFont` changes, `F/shaping/harfbuzz_font_data.h:58,85`) → per glyph a digest lookup in the strike;
- extents: only for fallback mark positioning on multi-glyph clusters (the CPU font has no GPOS, so HarfBuzz zeroes
  GDEF marks' widths and runs fallback positioning, `hb:src/hb-ot-shape.cc:189, 206, 1089`; single-glyph clusters
  return early). Kerning callbacks: none set, so HarfBuzz's fallback kern returns at once.

`GetScaledFont` (`:705`) calls `hb_font_set_scale(size × 65536)` and `hb_font_set_ptem` on every range; HarfBuzz
returns early when unchanged (`hb:src/hb-font.cc:2779, 2876`). Because the hb_font is per typeface, alternating
two sizes of one typeface would bump its serial every call (and rebuild HarfRust's per-font data). *(code)*

Where Skia's numbers come from *(code, Skia main)*:

- **Sizes > 256 px** (text-matrix scale over 256): `SkStrikeSpec::ShouldDrawAsPath` → `MakeCanonicalized` measures at
  `kCanonicalTextSizeForPaths = 64` px with hinting off and subpixel on, then multiplies by size/64. The CPU font at
  1,024 px is in this regime: advance = units × 64/1024 × 16, exact.
- **Sizes ≤ 256 px:** a strike at the real size with the page's hinting. Fontations (`SkFontationsScalerContext`):
  `kNone` and `kSlight` → linear (unhinted) advances; `kNormal`/`kFull` → the glyph is hinted (autohinter for glyf
  fonts without fpgm/prep, `Engine::AutoFallback`) and an adjusted advance is rounded to whole pixels "to match
  FreeType" (`SkTypeface_fontations.cpp:587-610`).
- Blink's own rounding: `SkFontGetGlyphWidthForHarfBuzz` rounds advances when `!font.isSubpixel()`
  (`F/skia/skia_text_metrics.cc:80,87`), and `ShapeRange` rounds positions. `ApplyToSkFont` forces subpixel unless
  hinting is `kFull` or a web test runs (`F/web_font_render_style.cc:108-113`); `text-rendering:
  geometricPrecision` forces subpixel positioning and hinting none on Linux/ChromeOS (`F/font_platform_data.cc:246`);
  Windows sets subpixel iff anti-aliasing (`F/win/font_platform_data_win.cc:60-70`).

### 1.8 `ShapeResult`: runs, packing, widths

- A `ShapeResultRun` per (font, script, direction) slice of the buffer: `HarfBuzzRunGlyphData` packs a 16-bit glyph
  id, a 15-bit character index, an unsafe-to-break bit and a `TextRunLayoutUnit` advance in 8 bytes
  (`F/shaping/glyph_data.h:31-77`); offsets live in a side vector only when non-zero. `kMaxCharacters = kMaxGlyphs =
  32,768` per run: `LimitNumGlyphs` (`shape_result.cc:1569`) splits longer slices into more runs (bookkeeping only;
  HarfBuzz shaped them in one buffer). 65,535 glyphs per font (`HB_NO_BEYOND_64K`). *(code)*
- `ComputeGlyphPositions` (`:1691`) copies each 16.16 advance exactly (`HarfBuzzPositionToTextLayoutUnit`), sums in
  `InlineLayoutUnit` (int64 16.16), then stores `run->width_ = total.ClampNegativeToZero().ToFloat()` (`:1750`);
  `ShapeResult::width_` is a float sum of runs. **A run or item whose advances sum negative (a big GPOS kern) has
  width 0 while its glyphs still move left.** *(code)*
- Line breaking uses `SnappedWidth()` = `LayoutUnit::FromFloatCeil(width_)` (`shape_result.h:170`;
  `L/inline/line_breaker.cc:1587, 1724`): span boxes are ceil-to-1/64-px of a float. A width a hair above an integer
  reads +1/64. *(code)*
- New on main, test only: `MonospaceGlyphCompaction` stores runs of equal advances as one advance plus 16-bit ids
  (`shape_result_run.h:577-640`). Memory, not speed, and irrelevant to varied advances. *(code)*

### 1.9 Precision chain

```
font units ─(Skia/Fontations, float px)─► advance px ─(×65536, ClampTo<int>: truncate, saturate)─►
  hb_position_t 16.16 int32 ─(GPOS adds, HarfBuzz)─► buffer positions ─(round to px if !subpixel)─►
  TextRunLayoutUnit 16.16 int32 ─(sum, int64)─► InlineLayoutUnit ─► float run width ─(ceil to 1/64)─►
  LayoutUnit 26.6 int32 (±2^25 px): the span's box
```

Consequences *(code, measured in `exp/06/exp/adv/`)*:

| Probe (headless 153, DSF 1) | Result |
|---|---|
| upem 1024, 1,024 px: advances 32,767 / 32,768 / 40,000 / 65,535 | 32,767 / 32,768 / 32,768 / 32,768 |
| two 32,767 glyphs in one span | 65,534 |
| upem 1024, 256 px, 104 × 1,001 units | 26,026 (250.25 each, exact) |
| upem 1024, 300 px (path strike), 104 × 1,001 units | 30,499.21875 (exact) |
| upem 1024, 16 px, outline glyphs of 1,003 and 13 units | 15.671875 and 0.203125 each (fractional kept) |
| upem 1000, 1,000 px, one 12,288 / 30,000 glyph | 12,287.984375 / 29,999.953125 |
| upem 1000, 1,000 px, 64 × 12,288 | 786,430.6875 (−1.3125) |
| upem 1000, 250 px | exact for every advance tried |

Two limits follow. The per-glyph cap is 32,768 px minus 1/65536 (saturating). And outside 1 unit = 2^k px, the float
products and the truncating `ClampTo` (a `static_cast` for in-range values) leave per-glyph errors that the
1/64 ceil can expose; with a power-of-two upem and sizes that make units-per-pixel dyadic, every step is exact.

In the non-subpixel configuration there is an overflow (§5): `RoundHarfBuzzPosition` computes
`round(v / 65536) << 16` in `int32`, and a saturated `0x7FFFFFFF` (32,767.99998 px) rounds to 32,768, whose shift
overflows. *(code)*

### 1.10 Counters into text, and when that text changes

`counter()` in `content` creates a `LayoutCounter` (a `LayoutText`) under the pseudo-element. Its text changes in
exactly one place, `LayoutCounter::UpdateCounter` → `SetTextIfNeeded`, called from `StyleEngine::UpdateCounters()`
(`C/css/style_engine.cc:928`; also at attach time when the attach context is rooted at the document). That function
runs when `counters_changed_` is set (any element whose counter directives changed, `C/dom/element.cc:5978`) and
walks **the whole flat tree from the document element** (`display: none` subtrees included), entering every element
with a layout object and regenerating every `LayoutCounter` under elements with non-`normal` content (chapter 03
§1.8 measured 15–25 ns per element; here: one changing `counter-set` beside 75,000 empty elements, `UpdateLayoutTree`
2.0–2.7 ms against 0.1 ms with a width change instead, ~25–35 ns per element; `exp/06/exp/mkctr.py`).

It is called from `StyleEngine::UpdateStyleAndLayoutTree` (`:4322`) and once more after layout in
`LocalFrameView::UpdateStyleAndLayout` (`C/frame/local_frame_view.cc:3622-3624`), whose "third pass" then relayouts
if that made layout dirty. **It is not called inside `UpdateStyleAndLayoutTreeForSizeContainer`**, the style
recalc that runs during layout for size containers (`style_engine.cc:4034`). A `counter-set` computed there
(js-minus-js's readers, the console) changes the counter tree but not the text until the next `UpdateCounters`.
*(code)*

`content: if(style(--d: n): "…"; …)` behaves differently: the pseudo-element's computed `content` changes inside
the container recalc, `RebuildLayoutTree(&container)` replaces its text fragments there, and the block is dirty for
the layout that follows in the same pass. *(code; measured below)*

The chain experiment (prior survey's `survey/exp/chain/mkchain.py`, `CB=contain`, R = 8 values per level, and my
`mkchain_if.py` variant with `IFC=1`: three `if()`s of 16 branches per span instead of three counters; checker
`rocheck.js` reads every level's readers inside a ResizeObserver callback, which forces nothing):

| Chain | Bad values per RO delivery | Per frame (trace) |
|---|---|---|
| counters, K = 4 | 16, 8, 0, 16, 8, 0, … | 2 `Layout`s × 2 shapings |
| counters, K = 8 | 48, 40, 32, 24, 16, 8, 0, 48, … | 2 `Layout`s × 4 shapings |
| `content: if()`, K = 4 and 8 | 0 at every delivery, one delivery per frame | 1 `Layout`, 2–6 shapings in it |

With counters, each RO delivery is one more lifecycle iteration and fixes one level. The prior survey's checker read
`getBoundingClientRect()` level by level; each read forced another update, which is how K = 16 looked exact.
Without extra iterations a rendered frame shows levels up to two counter updates deep. *(measured)*

Cost of the switch, measured on the CPU line's real structure (`mkpage2.py`: 173 spans, 498 input cells, 776 static
cells, every input changing every frame, cv01 0): counters `UpdateLayoutTree` 2.0–3.1 ms (recalc 1.6) + `Layout`
1.0–1.6 ms; `if()` (16 equality branches per cell, registered `<integer>` per cell) `UpdateLayoutTree` 5.4–10.6 ms
(recalc 5.2, rebuild 0.2) + `Layout` 0.65–1.1 ms. About 3× the style cost per changed cell, no document walk, and
in-layout chaining. *(measured)*

### 1.11 Paint and ink

`BoxFragmentPainter::PaintTextItem` skips items that aren't `visibility: visible` (`IsVisibleToPaint`,
`C/paint/box_fragment_painter.cc:145`): the hidden CPU line never reaches `ShapeResultBloberizer`. Ink overflow is
still computed for every text item: `InkOverflow::ComputeTextInkOverflow` (`C/layout/ink_overflow.cc:441`) →
`ShapeResultView::ComputeInkBounds` → `SkFont::getBounds` batched per run (`shape_result.cc:2722`), with no
visibility check. The CPU font's glyphs are empty, so the bounds are cheap. *(code)*

### 1.12 HarfRust inside Blink

There is no Blink-side FFI: `ShapingBackend()` passes `{"harfrust"}` as HarfBuzz's shaper list, and HarfBuzz's own
`harfrust` shaper (`hb:src/hb-harfrust.cc`, `hb:src/rust/shape.rs`, built as `harfbuzz_rust` in
`third_party/harfbuzz/BUILD.gn:45-68` against `harfrust v0_14`, `read_fonts v0_45`, `skrifa v0_48`) does the rest
*(code)*:

- face data: a HarfRust `Font` over a table closure that returns `hb_face_reference_table` blobs (`shape.rs:74`):
  **raw tables, no HarfBuzz sanitizer**, so no `HB_SANITIZE_MAX_SUBTABLES` cap (prior survey measured 18,000
  aliased subtables working);
- font data: an instance from HarfBuzz's normalized coordinates (`font_to_instance`, `:204`), x/y scale and ptem,
  rebuilt when the hb_font changes;
- metrics: `HBHarfBuzzFontFuncs` (`:120`) calls back into the hb_font (`hb_font_get_glyph_h_advances`, …), i.e.
  into Blink's Skia callbacks: same advances, one more FFI hop;
- plan: built once per HarfBuzz shape plan and cached on it (`hb-harfrust.cc:160`); buffer: a HarfRust buffer
  cached as user data on the hb_buffer, glyph infos/positions copied back;
- failure: `harfrust::shape(...).is_err()` → `false` (`shape.rs:430-446`), and if HarfRust can't build a face,
  the plan has no shaper and `hb_shape_full` returns false (`hb:src/hb-shape-plan.cc:431-447`). Blink ignores the
  result (§5).

Limits that remain in HarfRust 0.14 (`harfrust/src/`): nesting 64, context 64, syllable 64, buffer `MAX_LEN_FACTOR
256` / `MAX_OPS_FACTOR 4096` (minimum 65,536), `MAX_LIGATURE_CACHE_WORK 16,384` (a cache budget), feature values 8
bits (`ot/map.rs:77`), class-pair matrices that overrun their subtable now rejected (`e118fd7`). OTS is unchanged:
it runs before any shaper and still passes GSUB/GPOS/GDEF through.

Measured in 153 (HarfRust 0.12), real page, FizzBuzz mid-run, interleaved (`exp/06/exp/hr.js`):

| Backend | CPU shapings (median) | `cv01 0` shapings |
|---|---|---|
| HarfBuzz 14.3.1-10 | 21.92, 22.84 ms | 0.17 ms |
| `--enable-blink-features=HarfRustShaping` | 36.10, 37.94 ms | 0.19 ms |

1.65× per shaping; the prior survey's end-to-end 24% included the non-shaping time.

### 1.13 Other glyph machinery, briefly

- MathML stretchy operators (prior survey Q10): the glyph assembly is capped at `HarfBuzzRunGlyphData::kMaxGlyphs`
  (32,768), the same constant as the run limit above. *(code)*
- `font-palette` / `@font-palette-values`: `GetFontPlatformData` makes a second clone with palette overrides
  (`F/font_custom_platform_data.cc:276-316`), so an animated `palette-mix()` is a new typeface per frame, like an
  axis. COLRv0/v1 glyphs are drawn by Fontations. Colors can't be read back by CSS; no use found. *(code)*
- `@counter-style` → text: chapter 03. `symbols()` became stable in 155. *(code)*

---

## 2. What it means for the projects

### js-minus-js

**The shaping is HarfBuzz; Blink's wrapper is noise.** The page's `cv01 0` shapings of the same 1,274-glyph line take
0.15–0.33 ms against 21.9–28.7 ms with the CPU running (`exp/06/exp/trace.json`). The difference from
uharfbuzz's 20.6 ms (BENCHMARKS §3) is HarfBuzz itself: uharfbuzz 0.56.3 bundles HarfBuzz 14.6.0, Chrome 153
14.3.1-10. → Don't spend effort on Blink-side shaping overhead; per-shaping savings come from the font (chapter 07)
or from fewer shapings. *(measured)*

**What a CPU pass costs around HarfBuzz.** From the page trace and the structure probes *(measured)*:

| Item | Per pass |
|---|---|
| `UpdateCounters` + 498 counter texts (`UpdateLayoutTree` self time, counter-changing passes) | 1.25–1.8 ms |
| line layout of 173 spans, ~1,274 text items + ~700 tags (`P_sep_0.html`) | 1.1–1.7 ms |
| same text as one text node (`L_one_0.html`) | 0.35 ms |
| 1,274 `::before` items (`L_pseudo_0.html`) | 5.5 ms |
| Blink shaping wrapper | ≤ 0.3 ms |

Merging adjacent static cells into one string (683 parts instead of 1,274) changed nothing measurable. The real
costs per frame are elsewhere (`performLayout` self time ~42 ms per frame in the same trace: readers, RAM, anchors;
chapter 05). → The CPU line's own overhead is ~3–4 ms per shaping pass: worth a small win at most.

**Chaining shapings within a pass needs `content: if()`, not counters** (finding 2). PRIMITIVES recommendation 1
("chain shapings inside one layout pass … 8 levels per frame") would not work with today's counter-driven lines:
each level waits for a lifecycle iteration (the RO pass pump gives D + 2 per frame, so chaining through counters is
the pump, at a full style+layout per level and ~1.5 ms of document walk each). With `if()` text every level reshapes in
the same `Layout`. → If the chain design is pursued, render each chained line's cells as
`content: if(style(--cP: 0): "\XXXX "; …)`, with `--cP` registered `inherits: true` (the pseudo-element must
inherit it; `inherits: false` reads the initial value, which is how my first attempt stalled at 1 everywhere).
Mitigate the ~3× style cost: fewer branches per cell (two 2-bit props and nested `if()`, ≤ 8 equality tests;
range tests cost 1.7 µs against 0.8 µs, ENGINE_NOTES 7), and only cells that change restyle. *(code + measured;
mitigation: inference)*

**ENGINE_NOTES 43 and 29, corrected.** 43's cap is the 16.16 `int32` of `hb_position_t` and `TextRunLayoutUnit`,
per glyph and saturating at 32,768 px (finding 3). 29 says HarfBuzz is 16.16 and Chrome positions in whole device
pixels: in Blink HarfBuzz positions are 16.16 *pixels* (Blink sets the scale to size × 65536), and whole-pixel
rounding happens only without subpixel positioning (finding 4). 1 unit = 1 device px remains the safe choice: exact
in every representation, unaffected by rounding where it does happen, and it keeps per-glyph values under the cap.
→ Reword 29 to the mechanism; keep the rule. *(code + measured)*

**A 16-bit span is possible, with a caveat.** With font-size 512 px / R (0.5 device px per unit), hmtx's full
uint16 range (65,535 units = 32,767.5 px) fits under the cap and every value is a multiple of 0.5 px, exact in
16.16, LayoutUnit and float. It relies on subpixel positioning: under `kFull` hinting (some Linux desktops) or
Windows without anti-aliasing, Blink rounds advances to whole pixels and odd values break. `text-rendering:
geometricPrecision` forces subpixel positioning on Linux/ChromeOS only. → Possible for a headless/Chrome-OS-like
target, not portable. GPOS deltas stay int16 units. *(code; untested at 512 px)*

**Shaping ranges are the unit of reshaping.** Anything in the line that breaks a range (a different `font-*` on a
span, inline padding/margin/border, `vertical-align`, a control character, a bidi control) splits HarfBuzz's buffer
and the contexts across it; anything in the same range is reshaped when any cell changes. Two independent machines
in one block share `CollectInlines` but reshape separately; in separate blocks they share nothing. → A small
coprocessor (EXT arithmetic as a second GSUB line in its own block) would reshape only when its inputs change. The
CPU line itself can't be split: its lookups need the whole state in one buffer. *(code; coprocessor:
speculation)*

**`--go` flips cost a cheap reshape plus the line's layout.** `font-feature-settings: "cv01" var(--go)` changes the
`Font`, so a flip re-collects and reshapes (0.2 ms with cv01 0) and relays out the line (~1.5 ms). Gating with
`cv01 0` is the right design: an idle control glyph would still run every lookup over the buffer. *(code +
measured)*

**Readback font.** Each `SCAN` value is a new instance: clone, three normalizations, a new `hb_face_t` (GSUB/GPOS
sanitized again) and a new shape plan, kept only until the next GC. 64 features (`cv01`–`cv64`) selecting the
column's lookups would keep one instance and cache 64 plans on one face; feature values alone can't select lookup
sets (a value is an AlternateSubst index or a mask, 8 bits). Small gain against ~18 ms per column. → Low priority.
*(code; magnitude: inference)*

**HarfRust.** At 1.65× per shaping (153), raising S to 64 (−24% shapings in the model, BENCHMARKS §1) doesn't pay:
per step ≈ 0.76 × (2 × 1.65 × 21 + 53) ≈ 93 ms against 74 ms today, assuming HarfBuzz time doubles with S
*(derived)*. It stays a watch item: test status since 155 means content_shell, and so Blink's web tests, shape with
it by default, and 0.12 → 0.14+ has the optimizations the CPU font exercises (mark-filtering-set bitmaps, cached
lookups and coverage tests, context-rule caches). Re-measure on Canary
with `--enable-blink-features=HarfRustShaping` before any S-related decision. *(measured + code)*

**Feature values.** `"cv01" N` reaches HarfBuzz as N; global features keep `N & 0xFF` after the map's 8-bit mask
(chapter 07). A table lookup by feature value (AlternateSubst index = N − 1) costs one shaping of the span that
carries it, no new instance, and splits the shaping range at that span (different `Font`). *(code)*

**Smaller notes.** BMP PUA code points (838 needed, 6,400 available) would halve the line's UTF-16 length; the saving
is microseconds. A code point missing from the CPU font would trigger system-font fallback on every shaping; the
`fok` sentinel would not notice. `letter-spacing` on the line would disable ligatures and change every advance after
shaping. *(code)*

### css-physics

**Variable-font compute (BENCHMARKS §3, HISTORY "Variable-font metrics").** The per-instance cost is structural:
three normalizations, a new strike (metrics, `'0'` advance) and a new `hb_face_t` per coordinate set (§1.3).
Levers *(code; magnitudes measured where stated)*:
- **Reuse**: exact repeats hit two weak tables (~2–4 µs per element). Quantizing inputs to a small set makes most
  frames hits until the next GC; a hidden element per value pins it.
- **Fewer axes**: hashing, the clone's axes × args loop and the four axis-parameter lookups are O(axes) to
  O(axes²) per instance; the 2 → 8 axis step doubled the cost (15 → 30–35 µs).
- **155+**: the read-fonts normalization fixes (O(n²) avar → O(n), >64-axis fvar path) should shrink the large-axis
  rows (256 axes: 398 µs). Re-measure on 155 before closing the HISTORY entry.
- **No gain from hinting off**: `text-rendering: geometricPrecision` measured the same.
- **`font-size-adjust` as a divider**: `1ex` under `font-size-adjust: cap-height k` gives k × size × xh(axes) /
  cap(axes) in one style pass. Two instances per value. *(code; untested)*

**Precision**: the instance size is floored to 1/100 px, so a computed font-size input carries ~0.01 px.

### paint

Its only text dependence is the `<img alt>` probe's alt-text box (PRIMITIVES finding 6). The width comes from
whatever font renders the alt text, including system fallback. → Pin a web font with known advances on the probe
(PRIMITIVES already suggests pinning). *(inference)*

---

## 3. What's changing

| Area | 153 (tested) | 155 (stable) | 157 (beta) | main (158) |
|---|---|---|---|---|
| HarfBuzz | 14.3.1-10 | 14.4.0-86 | 14.5.1-141 | 14.5.1-141 |
| HarfRust / read-fonts / skrifa | 0.12 / 0.41 / 0.44 | 0.13 / 0.43.3 / 0.46 | 0.14 / 0.45 / 0.48 | 0.14 / 0.45 / 0.48 |
| `HarfRustShaping` | no status (off) | `test` | `test` | `test` |
| `MonospaceGlyphCompaction` | absent | absent | no status | `test` |
| Batched nominal-glyph callback, buffer pool 8 | no | no | yes | yes |
| `FontVariableItalicAxis` (`ital` axis from `font-style: italic`) | absent | absent | stable | stable |
| `CSSCounterStyleSymbolsFunction` (`symbols()`) | experimental | stable | stable | stable |
| `LineBreakerClearShapeResultOnOverflow` | absent | absent | stable | stable |
| `FontUniqueNameTypefaceCache` (`local()` lookups) | absent | absent | stable | stable |
| `IncrementalFontTransfer` | test | test | test | test |

*(code: `$SP/src/versions/*/…/runtime_enabled_features.json5`, `third_party/rust/*/README.chromium` via gitiles;
`exp/06/flags.py` prints the full font/text flag diff)*

Other observations *(code)*:

- `platform/fonts` 153 → main is mostly refactoring (`unsigned` → `wtf_size_t`, `Character::` → `unicode::`, span
  safety). Substantive: monospace compaction, IFT plumbing in the shaper and decoder, the batched nominal-glyph
  callback, the split advance loop in `skia_text_metrics.cc`, `raw_ptr` "UnprotectedInReleaseForPerformance" on the
  font funcs (Speedometer-driven). No change to `ShapeText`'s reuse rules or the counter walk.
- HarfRust upstream after 0.14 (`$SP/src/harfrust`, to 2026-10-17): cached lookups borrowing parsed GSUB/GPOS/GDEF
  from a shared layout cache (`9550595`, `0c6e0aa`, `8d8ce09`, 2026-10-15), coverage tests before dispatch
  (`510828d`), backed by new read-fonts hooks (`1c3d0af` table cache host, `9e6067b` caching whether a font has
  lookup variations). A 0.15 roll into Chromium is the likely next step *(inference)*.
- `HB_NO_BORING_EXPANSION` in `third_party/harfbuzz/BUILD.gn:517` is dead: HarfBuzz removed it in July 2025
  (`64b50ec4d`). avar2 (`HB_NO_AVAR2` not defined) is live in HarfBuzz as well as Fontations. The prior survey
  copied the define into its list; it disables nothing.
- No HarfRust ship signal beyond test status: no `base::Feature`, no chromestatus entry, no virtual test suite.
  Fontations shipped (133); avar2 is listed for 148 on chromestatus.
- TODOs on the paths used here: `harfbuzz_face.cc` crbug.com/899718 (replace vertical callbacks with HarfBuzz's
  VORG/vmtx); `font_features.cc` crbug.com/450619 (feature resolution instead of appending); the IFT TODO about
  `unicode-range` filtering in `ShapeSegment`.

---

## 4. Ideas

Ranked by expected value × confidence.

1. **Switch chained readback lines from counters to `content: if()`** *(code-backed + measured)*: the only way found
   to get several dependent shapings into one layout pass. It also drops the document-wide counter walk for those
   lines. Cheapest test: build the real `f4cc_16` font into `mkchain_if.py`'s structure (2 levels, no trap service)
   and confirm with `rocheck.js` (0 bad values at every delivery) and `frames.js` (both shapings in one `Layout`).
   Then decide between this and the pass pump.
2. **Correct the prior survey and the notes** *(code-backed + measured)*: PRIMITIVES finding 3 and recommendation 1
   (counter chains lag a lifecycle iteration per level; the checker forced the extra passes); ENGINE_NOTES 43 (cause:
   int32 16.16 per glyph, saturating); ENGINE_NOTES 29 (mechanism: rounding only without subpixel positioning);
   ENGINE_NOTES 33 / bugs/README (Fontations normalization fixes in 155). No experiment needed beyond those
   recorded here.
3. **Keep HarfRust on the watch list with a concrete trigger** *(code-backed + measured)*: re-run `hr.js` on Canary
   with the flag. If HarfRust reaches ≤ 1.2× HarfBuzz there, S = 64 (which only HarfRust allows) becomes worth
   modelling again.
4. **css-physics: re-measure variable-font compute on 155** *(inference)*: the normalization fixes target exactly
   the large-axis rows. Cheapest test: BENCHMARKS §3's width-scaling page on Chrome 155 against 153.
5. **css-physics: quantize and pin axis values** *(inference)*: if a solver quantity can live on a grid of a few
   hundred values, instances become cache hits (2–4 µs vs 15–35 µs) as long as something pins them. Test: the vf
   probe with `mod(…, 16)` coordinates.
6. **Reduce the cost of `if()` cells** *(speculation)*: two-level nested `if()` over 2-bit registered digits;
   restyle only changed spans (state spans grouped by update rate). Test: `mkpage2.py` variants, `UpdateLayoutTree`
   median.
7. **A 16-bit span via 0.5 px units** *(code-backed, environment-limited)*: font-size 512 px / R doubles the span's
   range on subpixel-positioning configurations; it removes ENGINE_NOTES 43's second span for 16-bit addresses
   where the target allows. Test: `adv.js` at 512 px with a 65,535-unit glyph (expect 32,767.5).
8. **`font-size-adjust` as a style-time divider for css-physics** *(speculation)*: k × size × xh/cap from two MVAR
   metrics. Test: a 2-axis font, 400 elements, compare against calc.
9. **Feature tags instead of an axis for the readback scan** *(code-backed, low value)*: `cv01`…`cv64` per column
   keeps one font instance and one `hb_face_t`. Test: `rbsweep.js` before/after.
10. **A GSUB coprocessor line in its own block** *(speculation)*: EXT operations (1,104 suite traps, BENCHMARKS §1)
    served by a second font line that reshapes only when its operands change, read like the state line. Test: one
    multiply line, 4-bit operands via counters or `if()`, per-pass cost in a trace.

Dead ends from the source: shape-result memoization for web fonts (NGShapeCache is off for custom fonts);
`text-rendering: optimizeSpeed` to skip GSUB (it only turns off three features); feature values ≥ 256 (masked);
splitting the CPU line into independently reshaped ranges (its contexts span the whole buffer).

---

## 5. Possible bugs and open questions

### Possible bugs

1. **Blink ignores `hb_shape_full`'s result** (`F/shaping/harfbuzz_shaper.cc:353`). With `HarfRustShaping` on, a font
   HarfRust can't parse, or a `harfrust::shape` error (`hb:src/rust/shape.rs:430-446`), makes HarfBuzz return false
   with the buffer still holding Unicode code points (`hb:src/hb-shape-plan.cc:431-447, 474`); `ExtractShapeResults`
   then commits code points (truncated to 16 bits) as glyph ids with zero advances. Under the shipping `ot` shaper the
   path is practically unreachable. Only matters if HarfRust ships; worth a guard before then. *(code; not run)*
2. **Overflow when subpixel positioning is off**: `SkFontGetGlyphWidthForHarfBuzz` rounds, then
   `SkiaScalarToHarfBuzzPosition` saturates any advance ≥ 32,768 px to `0x7FFFFFFF`; `RoundHarfBuzzPosition`
   (`F/shaping/harfbuzz_shaper.cc:289-296`) computes `static_cast<hb_position_t>(round(v / 65536.f)) << 16` =
   `32768 << 16`, a signed overflow (UB; in practice −32,768 px). Reachable with full hinting on Linux or Windows
   without font smoothing. Same for offsets. *(code; can't select full hinting from a headless run)*
3. **Counter text lags counter values set during layout** *(code + measured)*: `UpdateCounters()` isn't run inside
   `UpdateStyleAndLayoutTreeForSizeContainer`, so a `counter-set` that a size-container query changes shows its old
   text until the post-layout `UpdateCounters()` and its "third pass"; with two dependent levels the painted frame is
   stale (§1.10). `content: if()` in the same position updates at once. css-lists doesn't define frames, so this is an
   inconsistency rather than a clear spec violation; an MRE would be a two-level counter chain under size containers,
   showing pass/fail with a colour.

### Open questions

- The exact source of the ~1.7 × 10⁻⁶ relative error at sizes > 256 px with upem 1000 (§1.9): the 64-px canonical
  strike plus truncation explains the sign and the power-of-two fix, not the magnitude. A Skia/skrifa read would.
- Whether Fontations' autohinter setup (`GlyphStyles::new`, computed once per typeface, so per instance) is a large
  share of the instance cost for real text fonts with many glyphs; my probe font had six.
- HarfRust 0.14+ speed on the CPU font inside Chrome: unmeasured here. Chapter 07 built a Rust toolchain and measured
  it standalone: 1.34× HarfBuzz at 0.14.0 (what Chromium links), 1.21× at HEAD.
- What else the `ifchain` structure costs at js-minus-js scale (498 cells, 76 readers per level).
- An unreproduced renderer crash ("Target crashed") on the first run of a broken `if()` chain page under a
  ResizeObserver; three reruns didn't crash. Recorded, not reported.

### Reproducing

```bash
cd exp/06/exp
python3 mkctr.py ctr 75000 c.html && node run.js c.html 3            # counter walk vs document size
python3 mkpage2.py ctr S_ctr.html && python3 mkpage2.py if S_if.html  # counters vs content: if() on the CPU line
node run2.js S_ctr.html 3 && node run2.js S_if.html 3
CB=contain python3 <repo>/survey/exp/chain/mkchain.py 8 8 10 chain8.xhtml
IFC=1 CB=contain python3 mkchain_if.py 8 8 10 ifchain8.xhtml
node rocheck.js chain8.xhtml ifchain8.xhtml && node frames.js ifchain8.xhtml
node hr.js /workspaces/css-energy/js-minus-js/build/js_in_css.xhtml [--enable-blink-features=HarfRustShaping]
cd adv && python3 mkadv.py && node adv.js && python3 mkadv2.py && node adv2.js     # advance caps and precision
cd ../vf && python3 mkvf.py 8 vf8.ttf && python3 mkpage.py vf8.ttf 8 anim auto p.html && node run.js p.html
```
