# 03. Values and properties: custom properties, var(), calc(), precision, value functions, counters

Source: Chromium main `22b3b159` (2026-10-18, M158) unless a line says 153 (branch 8010), 155 (8059), 156 (8078) or
157 (8103). Paths are from the src root; `core/` = `third_party/blink/renderer/core/`, `platform/` =
`third_party/blink/renderer/platform/`. Probes ran in the repo's headless Chromium 153.0.8010.12 on a shared machine
(load average 5–6: other agents), so timings are ratios between pages run in the same session, not absolute costs;
pass/fail probes are exact. Probe files: `exp/03/` (`probe/` precision and style() matrices, `cost/`
microbenchmarks, `adder/` the counter adder and its font). Labels: *(code)*, *(measured)*, *(docs)*, *(inference)*.

Neighbours: cascade, matched-properties cache (MPC), container-query lookup and invalidation in
[02-style-engine.md](02-style-engine.md); interpolation, keyframes, timelines and the O(registered properties)
animation loop in [04-animations-and-scroll.md](04-animations-and-scroll.md); layout and size containers in
[05-layout.md](05-layout.md); how counter text is shaped in [06-text-and-fonts.md](06-text-and-fonts.md); roadmap in
[09-roadmap.md](09-roadmap.md).

## Findings in brief

1. **Nothing caches a parsed value.** A custom property's declared value is stored as text (`CSSVariableData`) and
   a registered property is parsed against its syntax **on every element, every pass, even when it is a constant**
   (`core/css/properties/longhands/custom_property.cc:181`). A registered `calc(var(--t) * k)` tokenizes 5 times
   per element per pass and makes 6–10 garbage-collected allocations; its computed value is then serialized back to
   text so `var()` can use it (`core/css/resolver/style_builder_converter.cc:3717`). *(code)*
2. **The per-property cost decomposes cleanly** (ratios measured here, 2,000 props on one element): unregistered
   declaration = 1 unit (cascade map + registry lookups + one trie insert); registered constant ≈ 3 units (parse,
   compute, serialize, re-tokenize, second trie insert); `calc()` with literals +3 units (parse = evaluate); one
   `var()` substitution +2.5 units; each math function +1–2 units; a non-integer result +0.6 unit (`%.6g`
   formatting). *(code + measured)*
3. **The 6-digit limit is exactly `absl::StrFormat("%.6g")` in `CSSNumericLiteralValue::CustomCSSText`**
   (`core/css/css_numeric_literal_value.cc:198`), with a fast path that prints integers with |v| ≤ 999,999 exactly
   (`:299`). Main only swapped `String::Format` for `absl::StrFormat`; the format is the same. Values are doubles
   everywhere else: ENGINE_NOTES 3 ("registered integers are stored as floats") is wrong for the calc/var path
   (2^24 + 1 and 2^31 − 1 cross `var()` exactly as literal `<integer>`s). *(code + measured)*
4. **Full precision through `var()` today:** a literal `<integer>` (int32), an **animated `<integer>`** (keyframes
   or view timeline: int32), typed `attr(… type(<integer>))`, and anything carried as text (unregistered, or
   registered `syntax: '*'`). Everything numeric that is computed (`<number>`, calc-computed `<integer>`,
   `<length>`, `<percentage>`, `<time>`, cq readbacks) is cut to 6 significant digits. *(measured)*
5. **ENGINE_NOTES 1 root cause:** a calc-computed `<integer>` is stored with unit type `kNumber`
   (`style_builder_converter.cc:3606`), a literal with `kInteger`, and `CSSNumericLiteralValue::Equals` requires
   equal unit types (`css_numeric_literal_value.cc:326`). The value pool caches 0..255 as `kInteger` objects for both
   types (`:38–76`), so both sides are the same pointer there. The bug is wider than the note: **negative values
   never match either**, `style(--v: var(--w))` fails, and `style(--g)` is true at a calc-computed initial value ≥ 256.
   **Workaround that also survives the fix: query `style(--v: calc(N))`** (matched a calc-computed 300). Fix CL
   8559024 is open, not on main. It computes calc integers as `kInteger`, which also gives them full int32 through
   `var()`. *(code + measured)*
6. **`@container style(--x: v)` runs a miniature cascade per evaluation** (`StyleResolver::ComputeValue`,
   `core/css/resolver/style_resolver.cc:3212`: a `StyleResolverState`, a `StyleCascade`, a property set, a new
   `ComputedStyle`), which is why a false `style(--g: 1)` costs 0.8 µs against 0.2 µs for a name-only query.
   `if(style())` instead compares serialized text and builds no style: cheaper, but it has its own bugs (below).
   *(code)*
7. **`if(style(--x))` (no value) is true for every registered property, even at its initial value**
   (`core/css/resolver/style_cascade.cc:2841`); `@container style(--x)` is false there. Spec: true iff the computed
   value differs from the initial value. And `if(style(--n: 1048580))` matches `--n: 1048575` (6-digit text
   compare). Two possible bugs, measured. *(code + measured)*
8. **A CSS counter is an exact int32 adder across elements in document order**, and it can be read back as a number
   without the 6-digit cut: an additive `@counter-style` over a font whose glyph k has advance 2^k units turns the
   counter into a text width. Built and measured in 153: Σ i·123457 over 64 elements = 256,790,560 read back exactly
   through `anchor-size()` + `cqw` as two 15-bit halves. Requires a power-of-two `unitsPerEm` (1000 upem drifts by
   1/64 px past 8,192 px). Cost: about 1.3 µs per incrementing element per pass, plus a **whole-document walk** of
   ~15–25 ns per element whenever any counter value changes, plus a relayout of the reader text. *(code + measured)*
9. **js-minus-js pays that whole-document walk every pass**: its state line is rendered with `counter-set`
   (PRIMITIVES P10, `gen_fvm4.py:322`), so every pass with a new state walks all ~20K elements (+0.3–0.5 ms per
   pass measured on a 20K-element page), `display: none` subtrees included. Counters set inside layout (the
   console's `cqi` readers) trigger one more in-lifecycle layout (`core/frame/local_frame_view.cc:3624`, "Third
   pass"). *(code + measured; the 20K figure for js-minus-js: inference)*
10. **Value functions:** `random()` ships in **156** (stable in the 8078 branch; experimental in 155) and is stable
    per element and property across frames (cache keyed by name × element in `StyleEngine`), so it is no per-frame
    PRNG. `ident()` is still `test` on main, and even with the flag `var(ident("--m" var(--k)))` fails: the name is
    computed before the inner `var()` is substituted. Static and tree-counting arguments work (`var(ident("--m"
    sibling-index()))`). `inherit()` works in 153 behind `CSSInheritFunction` (`--acc: calc(inherit(--acc) + 1)`
    accumulates down a chain without parity copies) but has no milestone. `first-valid()` doesn't exist. New on
    main: `@private` (experimental). *(code + measured + docs)*
11. **`progress()` is 31% cheaper than the `clamp()` form here** (2.05 against 2.97 µs; PRIMITIVES measured 23%),
    and a digit extraction `sign(mod(round(down, x / 10^k), 10))` costs 3.2 µs against 1.6 µs for `calc(var(--t) *
    k)`: each math function adds 0.3–0.5 µs. *(measured)*
12. **Word capacity is set by the 999,999 fast path, not by "6 significant digits":** a base-B digest word holds
    ⌊log_B 10^6⌋ digits exactly: 6 in base 10, 9 in base 4, 19 in base 2. css-physics's digests use base 10; their
    summed digits are small counts, so base 4 would give 9 bodies per word if counts stay ≤ 3.
    *(code + measured; applicability: inference)*

---

## 1. How it works

### 1.1 Storage: text, two tries, and one registry

```
 stylesheet parse (once)          per element, per style pass               ComputedStyle.StyleVariables
 ───────────────────────          ───────────────────────────               ─────────────────────────────
 "--b: calc(var(--t) * 3)"        1. Resolve: var() → new text              data trie:  name → CSSVariableData
  → CSSUnparsedDeclarationValue   2. Parse(text, registered syntax)                     (text that var() substitutes)
    { CSSVariableData = text +    3. Compute (fold, round, clamp)           value trie: name → CSSValue
      6 feature bits,             4. Serialize: CssText() → text again                  (registered properties only)
      parser context }            5. two trie inserts ──────────────────►   unset: StyleInitialData (one per document)
```

- **`CSSVariableData`** (`core/css/css_variable_data.h:35`) is a 4-byte header (22-bit length, 6 feature bits:
  font units, root font units, `lh`, dashed functions, references, `random()`; taint bits) followed by the
  characters. **It stores no tokens and no parsed value**: "The tokens are not used apart from that; only the
  original string is stored" (`:72`). `Create(String…)` tokenizes the string once just to set the feature bits
  (`css_variable_data.cc:99`). Hash = `HashMemory32` over the text, recomputed on every call (`:94`). Equality is
  text equality. Maximum 2,097,152 bytes, including substituted text (`kMaxVariableBytes`, `:163`).
- **`CSSUnparsedDeclarationValue`** wraps a `CSSVariableData` plus the `CSSParserContext` (for relative URLs). Every
  custom-property declaration, registered or not, is stored this way at stylesheet-parse time, because the
  registration can change after parsing (`custom_property.cc:151–182`).
- **`PropertyRegistry`** holds two `HashMap<AtomicString, PropertyRegistration>`: `CSS.registerProperty()` names and
  `@property` names (`core/css/property_registry.cc:97`). A **`PropertyRegistration`** owns the
  `CSSSyntaxDefinition`, `inherits`, the initial `CSSValue` and the **interpolation types, built once at
  registration** (`property_registration.cc:52`). Nothing about interpolation is per element.
- **`StyleVariables`** (`core/style/style_variables.h:369`) is two copy-on-write hash-array-mapped tries:
  `data_root_` (name → `CSSVariableData`, the text `var()` substitutes) and `values_root_` (name → computed
  `CSSValue`, registered properties only). Each `HashTrieNode` has 16 slots (keys, values, children: about 260 bytes)
  indexed by 4 bits of the `AtomicString` pointer at a time (`:97`). Inheriting is a root-pointer copy plus
  `MakeShared()` (`:230`), which walks the whole parent tree the first time and is O(1) after that. A `Set()` on a
  shared node copies the path (log16 n nodes) and XORs `HashInts(key.Hash(), value->Hash())` into a running hash
  (`:297`), hashing the old value too when overwriting. Inherited and non-inherited variables use the same
  structure. A property an element never declares costs it nothing: unset registered properties read
  `StyleInitialData`, one per document (prior survey Q5; confirmed).
- **The cascade map** keeps custom properties in a `HashMap<AtomicString, CascadePriorityList>`
  (`core/css/resolver/cascade_map.h:203`), filled from the matched declaration blocks on every cascade
  (`style_cascade.cc` `CollectFromMatchResult`).

### 1.2 The apply path, step by step

`StyleCascade::ApplyMatchResult` (`style_cascade.cc:840`) iterates the custom map and, per name, constructs
`CustomProperty(&name, GetDocument())` (`:876`), which calls `PropertyRegistration::From` → two hash lookups in the
registry (`property_registry.cc:103,107`). Then `LookupAndApplyDeclaration` → `Resolve` → `ResolveCustomProperty`
(`:1392`) → `StyleBuilder::ApplyPhysicalProperty` → `CustomProperty::ApplyValue` (`custom_property.cc:107`).

**(a) Unregistered `--x: 5`.** No `var()`: `ResolveCustomProperty` returns the declaration itself (`data ==
decl.VariableDataValue()`). `ApplyValue` stores the declaration's own `CSSVariableData` pointer in the data trie
(`custom_property.cc:146`). No parse, no allocation except trie nodes.

**(b) Registered `--x: 5`** (`<number>`). As (a), then for registered properties `ApplyValue`:

1. `Parse(data.OriginalText())` → `CSSSyntaxDefinition::Parse` (`css_syntax_definition.cc:317`): a new
   `CSSParserTokenStream` over the text **for each `|` alternative of the syntax** until one parses, then
   `ConsumeNumber` → `CSSNumericLiteralValue::Create(5, kNumber)` → a pooled object for integers 0..255, else a GC
   allocation.
2. `ConvertRegisteredPropertyValue` → `ComputeRegisteredPropertyValue` (`style_builder_converter.cc:3554`): a literal
   number or px/% is returned as is (`:3585`); `calc()` numbers are evaluated and re-created (`:3601`); lengths go
   through `Length` (float, `:3590`); angles, times and resolutions are canonicalized.
3. `ConvertRegisteredPropertyVariableData` (`:3712`): **`value.CssText()`** (a new `String`), then
   `CSSVariableData::Create(String, …)`, which **tokenizes that string again** for the feature bits and allocates.
   The comment: "TODO(andruud): Produce tokens directly from CSSValue."
4. `SetVariableData` + `SetVariableValue`: two trie inserts (text hash + `CSSValue::Hash`).

**(c) Registered `--b: calc(var(--t) * 3)`.** Before (b)'s steps, `ResolveCustomProperty` sees the references bit and
calls `ResolveVariableData` (`:1683`):

1. Tokenize the declaration text (`ResolveTokensInto`, `:1703`), copying non-`var()` tokens' text into a
   `TokenSequence` (a `StringBuilder`).
2. At `var(`: `ConsumeAndComputeVariableName` (`:101`) makes an `AtomicString` from the name token (an
   atomic-table lookup per reference), constructs `CustomProperty` (two registry lookups), `MarkIsReferenced`,
   `DetectCycle` (a **linear scan** of the resolver stack, `cascade_resolver.cc:45`), `LookupAndApply` (applies
   `--t` first if this element declares it), `GetVariableData` (trie lookup), then `TokenSequence::Append` of
   `--t`'s text, which **tokenizes the substituted text** to update features and the last token (`:1113`).
3. `BuildVariableData` → a new `CSSVariableData` (GC).
4. The CSS-wide-keyword check **tokenizes the result again** (`:1439`); a new `CSSUnparsedDeclarationValue` (GC).
5. Then (b): tokenize again in `Parse`, build the math tree, evaluate, serialize, tokenize again.

So the answer to "is a registered value with `var()` re-tokenized and re-parsed at every element and every pass":
**yes, 5 tokenizations of the value and one full calc parse per element per pass, and the constant case is parsed
too.** Every consumer that writes `var(--b)` tokenizes `--b`'s text once more. I found no cache keyed by token text
in `CSSVariableData`, `CSSSyntaxDefinition`, `CustomProperty`, `StyleCascade` or `CSSValuePool`; the only caches on
this path are the integer pool (0..255 numbers, px and %), the identifier pool, and a one-entry shorthand cache inside
one cascade (`style_cascade.cc:1503`). The MPC (chapter 02) is what avoids all of this, and only for an element whose
matched blocks and parent inherited variables are unchanged, which no element of a css-physics chain is.

**Allocations** for (c), per element per pass *(code)*: substituted `CSSVariableData`, `CSSUnparsedDeclarationValue`,
one `CSSMathExpressionNumericLiteral` per literal plus one per folded operation (with a `CSSNumericLiteralValue`
each unless pooled), the `CSSMathFunctionValue`, the computed `CSSNumericLiteralValue`, the final `CSSVariableData`,
two `String`s (`StringBuilder` buffer, `CssText`), and path copies of shared trie nodes. Roughly 6–10 Oilpan objects:
cheap bump allocations, but they are garbage by the next pass, and Oilpan's marking and sweeping show up as GC time
outside the style pass.

### 1.3 Where the microseconds go

Measured here: 2,000 declarations on one element under an animated parent, `css-physics/tools/stylebench.js`, median
style pass of 3 interleaved rounds, minus an empty page (0.075 ms). This machine's absolute numbers came out lower
than css-physics BENCHMARKS §2 (0.78 against 1.27 µs for a registered constant) and noisy (±30%), so read the ratios.

| Declaration (2,000 on one element) | µs per prop here | BENCHMARKS §2 | Extra work, from the code |
|---|---|---|---|
| unregistered `--b: 123` | 0.23–0.27 | 0.50 | cascade-map insert, `CustomProperty` + 2 registry lookups, cycle-lock push, one trie insert |
| unregistered `--b: calc(123 * 2 + 1 * 3 + 4)` | 0.24 | — | none: text length is free until someone substitutes it |
| registered `<number>` `--b: 123` | 0.78–0.82 | 1.27 | `Parse` (tokenize), `Create` (alloc ≥ 256), `CssText`, `CSSVariableData::Create` (tokenize, alloc), value-trie insert |
| same, values 0..199 (pooled) | 0.75 | — | no `CSSNumericLiteralValue` allocation |
| same, `123.25` (non-integer) | 0.97 | — | `absl::StrFormat("%.6g")` instead of the integer fast path |
| registered `<integer>` / `*` constant | 0.80 / 0.87 | — | `*` skips the typed parse but tokenizes twice (`ParseUniversalSyntaxValue`, `Serialize`) |
| registered `calc(123 * 2 + 1)` | 1.58 | 2.27 | math tree built and folded at parse time |
| registered `var(--t)` | 1.55 | — | substitution (§1.2 c) + parse of the result |
| unregistered `calc(var(--t) * k)` | 0.88 | 1.38 | substitution only |
| registered `calc(var(--t) * k)` | 1.62 | 2.61 | both |
| registered `*` `calc(var(--t) * k)` | 1.64 (0.85× `<number>` in a paired run) | — | substitution, no calc parse, two re-tokenizations |
| `sign(max(0, k - var(--t)))` | 2.16 | — | 2 math functions |
| `progress(var(--t), k, k + 500)` / `clamp(0, (var(--t) - k) / 500, 1)` | 2.05 / 2.97 | — | 1 function node against ~6 folded nodes |
| `sign(mod(round(down, var(--t) * k / 1000), 10))` | 3.16 | "≈ 5" (CLAUDE.md) | 3 functions: per function a `HeapVector`, category checks, a use-counter hit, a folded literal |
| `round(down, x / 1000) - 10 * round(down, x / 10000)` | 4.53 | — | the subtraction form is dearer than `mod` |

So the BENCHMARKS model reads, in code terms: **1 unit (≈ 0.3–0.5 µs) to declare anything; +2 units to make it a
typed value; +3 units for a `calc()`; +2.5 units per `var()` hop; +1–2 units per math function.** The "+0.09–0.13
µs per extra token" is one tokenizer step in each of the ~5 tokenizations plus a node allocation and fold per
operator. css-physics's "≈ 5 µs per digit extraction" is the extraction (3.2 µs here, ~5 µs at BENCHMARKS scale)
including its own property; it is not a slow `mod`.

What is *not* in the per-declaration cost: interpolation types (built at registration), initial values (per
document), and registrations an element doesn't declare. What is, elsewhere, per registration: the animation
snapshot loop over `GetVariableNames()` (every registered property with an `initial-value`, chapter 04 §1.4) and the
transition-restart cost (BENCHMARKS §4). Registrations without `initial-value` (allowed only for `syntax: '*'`)
are not in that loop (04).

### 1.4 Numbers: storage, serialization, precision

- **Tokenizer:** a number token keeps a `double`, clamped to ±FLT_MAX in range only
  (`core/css/parser/css_parser_token.cc:44`). Its unit type is always `kNumber`; integer-ness is a separate flag.
- **`CSSNumericLiteralValue`**: `double num_` plus a unit type (`css_numeric_literal_value.h:101`). `Create()` routes
  integral values 0..255 of type px, % and number/integer to `CSSValuePool` caches; **the number cache stores
  `kInteger` objects whatever type was asked for** (`css_numeric_literal_value.cc:68–77`).
- **`CSSMathFunctionValue::ClampToPermittedRange`** (`css_math_function_value.cc:190`) rounds half towards +∞ for
  integer ranges and clamps; it returns a double.
- **`<integer>`**: a literal is `kInteger` (`css_parsing_utils.cc:1168`); a `calc()` is computed as
  `Create(ComputeNumber(), kNumber)` (`style_builder_converter.cc:3606`): rounded, but typed number.
- **Interpolation**: `InterpolableNumber` is a double, `from·(1−p) + to·p` (`core/animation/interpolable_value.cc:105`);
  `CSSNumberInterpolationType::CreateCSSValue` rounds for `<integer>` and **creates `kInteger`**
  (`css_number_interpolation_type.cc:47`, `.h:52`).
- **`<length>`** computed values go through `Length` (a float, `platform/geometry/length.h:433`).
- **Serialization** (`CustomCSSText`, `css_numeric_literal_value.cc:221`):
  - `kInteger` → `String::Number(ClampTo<int>(num_))`: all digits, clamped to int32.
  - every other unit → integral values with |v| ≤ 999,999 print exactly; otherwise `%.6g` (round-half-even):
    `1048575` → `1.04858e+06`.

Precision through one `var()` hop, measured in 153 (`probe/prec.html`, `probe/int24.html`): each test computes
`calc(var(--x) − base)` into a registered `<number>` small enough to print exactly.

| Value of `--x` | Crosses `var()` as | Digits kept |
|---|---|---|
| any registered `<number>`, literal or `calc()` | `%.6g` unless integral and ≤ 999,999 | 6 significant (999,999 exact; 1,000,001 → 1e+06; 0.1234567 → 0.123457) |
| `<integer>` literal | `String::Number(int)` | int32 exact (2^24+1, 2^31−1 exact; 3e9 → 2147483647) |
| `<integer>` from `calc()` (incl. `calc(256)`, negatives) | `kNumber` → `%.6g` | 6 (1048575 → 1048580; −1048575 → −1048580) |
| `<integer>` **animated** (keyframes; view-timeline registers) | `kInteger` | int32 (2e9 × 0.123456789 → 246913578 exact) |
| `<number>` animated | `%.6g` | 6 |
| `<length>`, `<percentage>`, `<length-percentage>`, `<time>` | `%.6g` (+ float for `<length>`) | 6 (16777217px → 16777216 before printing) |
| `attr(x type(<integer>))` / `type(<number>)` / `type(*)` | `CssText` of the parsed value / raw text | int32 / 6 / author's text |
| `calc(100cqw / 1px)` into `<number>` or `<integer>` | `%.6g` | 6 |
| the same expression in an **unregistered** property | text, evaluated at each use | double, but against the *user's* container |
| registered `syntax: '*'`, unregistered | text | the author's digits, double when finally evaluated |
| inside one `calc()` | double | 53 bits (2^53 + 1 → 2^53; 16777217 × 3 exact) |
| a CSS counter | int32 | exact; an overflowing increment is skipped (§1.8) |

`inherit()` substitutes the parent's `CSSVariableData`, so it is the same as `var()`. The text routes have a cost:
each user re-tokenizes and re-parses the whole carried expression, and text grows with every hop (2 MiB cap, then
the value is invalid).

### 1.5 Style queries compare `CSSValue`s; `if()` compares text

**`@container style(--x: v)`** → `MediaQueryEvaluator::EvalStyleFeature` (`core/css/media_query_evaluator.cc:1785`):

1. `StyleResolver::ComputeValue(container, name, query_value)` (`:1889` → `style_resolver.cc:3212`): **a new
   `StyleResolverState`, a `StyleCascade`, `CreateNewClonedStyle(container style)`, a
   `MutableCSSPropertyValueSet` holding the query value, `cascade.Apply()`, `TakeStyle()` (a new `ComputedStyle`)**,
   then `ComputedPropertyValue`. For a registered property that applies §1.2 (b) to the query text: parse with the
   registered syntax, compute, serialize. It also calls `UpdateViewportSize()`.
2. For registered properties: `base::ValuesEquivalent(query_value, computed_value) == explicit_value` (`:1924`):
   pointer equality, else `CSSValue::operator==` → `CSSNumericLiteralValue::Equals`, which **returns false when the
   unit types differ** (`css_numeric_literal_value.cc:326`).
3. For unregistered properties the comparison is text equality of the two `CSSVariableData` (`:1909`).
4. With no value, `query_specified` is `initial` (`:1875`); the result is "computed ≠ computed initial".

The result is cached per container per query (`ContainerQueryEvaluator::results_`) until the container's style
changes, which in both projects is every pass (chapter 02). BENCHMARKS §2's costs line up with this: a present name
0.21 µs, `style(--g)` 0.50 (the mini cascade applying `initial`), `style(--g: 1)` 0.80 (plus parse, compute and
serialize of `1`), unregistered `style(--u: 1)` 0.59 (no typed parse).

**ENGINE_NOTES 1, root cause** *(code + measured)*. Literal `256` in the query → `kInteger`; container value
`calc(var(--a) * 1)` → `kNumber` (§1.4); `Equals` fails on the type. For 0..255 both `Create` calls return the
pool's single `kInteger` object, so they compare equal by pointer. The suspected mechanism (pooled small integers;
equality by pointer, else by unit type and value) is the real one; bugs/README already says so. Measured matrix
(`probe/style.html`, `probe/bool.html`):

| Container value (registered) | Query | Result | Why |
|---|---|---|---|
| `<integer>` calc 256 / 1000 | `style(--v: 256)` | false | `kNumber` vs `kInteger` |
| `<integer>` calc −1 | `style(--v: -1)` | **false** | not pooled (negative); literal −1 matches |
| `<integer>` calc 300 | `style(--v: calc(300))` | **true** | both sides computed through calc → `kNumber` |
| `<integer>` literal 300 | `style(--v: calc(300))` | false | mirror image |
| `<number>` calc 300 / 300.5 | `style(--n: 300)` / `300.5` | true | number tokens are `kNumber` too |
| `<integer>` calc 1000, `--w` calc or literal 1000 | `style(--v: var(--w))` | false | `var(--w)` substitutes text "1000" → literal |
| `<integer>` animated to 1000 | `style(--v: 1000)` | true | interpolation creates `kInteger` |
| `<integer>` calc 300 | `style(--v >= 300) and style(--v <= 300)` | true | range path compares doubles |
| `<integer>` calc 255 / 0 | `style(--v: 255)` / `0` | true | pooled |
| `<integer>` initial 300, value `calc(299 + 1)` | `style(--g)` | **true** (wrong) | "≠ initial" by type |
| `<integer>` initial 200, value `calc(199 + 1)` | `style(--g)` | false | pooled |

Spec (css-conditional-5 §6.2): "A `<style-feature-plain>` evaluates to true if the computed value of the given
property on the query container matches the given value (which is also computed with respect to the query
container)". The computed value of a registered `<integer>` is an integer (css-properties-values-api: `calc()` is
rounded), so `calc(255 + 1)` and `256` are the same computed value: a bug, reported as
[571450199](https://issues.chromium.org/issues/571450199) (bugs/README). **CL 8559024** (status NEW, last updated
2026-10-13, not in main `22b3b159`) adds, before `:3606`:

```cpp
if (primitive_value->IsInteger()) {
  return *CSSNumericLiteralValue::Create(
      math_value.ComputeInteger(css_to_length_conversion_data),
      CSSPrimitiveValue::UnitType::kInteger);
}
```

`ComputeInteger` is `ClampTo<int>`, and `kInteger` serializes with `String::Number`, so the same CL **also lifts
calc-computed `<integer>`s from 6 digits to int32 through `var()`** and clamps them to int32. With it,
`style(--v: calc(N))` still matches: the query's `calc(N)` takes the same path.

**`if(style(--x: v))`** → `StyleCascade::EvalIfStyleFeature` (`style_cascade.cc:2766`). The property side is
`ResolveLikeVar` (its substitution text); the query side is `ResolveTypedExpression` (`:2185`: parse with the
registered syntax, compute, **serialize**). The comparison is `EqualsIgnoringAttrTainting`, i.e. text (`:2880`). So:

- `if(style(--v: 256))` matches a calc-computed 256 (measured): "256" = "256". For js-minus-js's `if()` muxes,
  ENGINE_NOTES 1 does not apply.
- `<number>` 1048575 matches a query of 1048580 (both print `1.04858e+06`; measured).
- With no value: `return computed_data ? kTrue : kFalse` (`:2841`). A registered property always has data (its
  initial value), so **`if(style(--x))` is always true for a registered `--x`** (measured at initial 0 and at an
  explicit initial 7), unlike `@container style(--x)`.
- No `StyleResolverState`, no `ComputedStyle`: this path is cheaper than `@container style()`. BENCHMARKS §2: an
  `if(style(--t: 5): 1; else: calc(…))` property cost 2.70 against 2.61 µs for the bare calc.

Range queries (`style(--h > 9)`, both in `@container` and `if()`) go through `CoerceIntoNumericValue`: substitute,
parse as a numeric syntax, `EvalStyleRange` compares doubles after `TypesMatch` (`media_query_evaluator.cc:1930`).
They aren't affected by the unit-type bug, and cost 1.7 µs per rule (BENCHMARKS).

### 1.6 The calc engine

- **Parse = evaluate.** `MathFunctionParser` (`css_parsing_utils.cc:1099`) → `CSSMathExpressionNodeParser`
  (`css_math_expression_node.cc:4285`): recursive descent over additive / multiplicative / term
  (`:5100`, `:5035`, `:4989`), functions via `ParseMathFunction` (`:4627`). Every constructor tries
  `CanEagerlySimplify`: when all operands are numeric literals with canonical units, it computes the result on
  the spot and returns a new `CSSMathExpressionNumericLiteral` (e.g. `CreateSteppedValueFunction` for
  `round/mod/rem`, `:2009`; `CreateExponentialFunction`, `:2032`; `CreateSignRelatedFunction`, `:2144`). After `var()`
  substitution, **everything in css-physics is a literal**, so the whole tree folds to one literal during parsing,
  and "evaluation" is `ComputeNumber` on that literal plus `ClampToPermittedRange`. The cost is the parse: one or
  two GC nodes per token and per fold.
- **Per function**, `ParseMathFunction` first runs `IsSupportedMathFunction`, then tries `ParseAnchorQuery`,
  `ParseProgressNotation`, `ParseCalcSize` and `ParseSiblingIndexOrCount` in turn (each returns early on a
  different function id), allocates a `HeapVector` for the arguments, and counts a `WebFeature` use
  (`context_.Count(...)`, e.g. `:4855`). `round()` with one argument gets a literal `1` step appended
  (`CanonicalizeRoundArguments`). That is the 0.3–0.5 µs per function measured in §1.3.
- **Types.** `CSSMathType` (`:286` onwards) implements css-values-4 typing: `100cqw / 1px` is a `<number>`
  ("typed arithmetic", shipped 140; on main the `CSSTypedArithmetic` flag is gone and the code is unconditional).
  `kCalcIntermediate` covers `1px * 1px`-style intermediate types, which are rejected as arguments of comparison
  and exponential functions.
- **Relative units stay unfolded:** `cqw`, `em`, `vw` and anchor queries keep an operation tree, evaluated at
  compute time against `CSSToLengthConversionData`. Container units set `kContainerRelative` on the conversion
  flags, which makes the element MPC-uncacheable (`style_resolver.cc:495`, `matched_properties_cache.cc:363`) and
  marks the container `referenced_by_unit_` (chapter 02, 05).
- **`progress(v, a, b)`** with literal arguments folds to `clamp((v − a)/(b − a), 0, 1)` in one node
  (`:4535`); main adds a NaN guard. `media-progress()` and `container-progress()` are still experimental.
- **`sign()`/`abs()`** fold the same way (`:2144`). **`anchor-size()`** parses to `CSSMathExpressionAnchorQuery`,
  evaluated during layout by the anchor evaluator; it is allowed only in sizing, inset and margin properties, never
  in a registered property's syntax (`ConsumeLength` gets no anchor-query permission), which is why a layout size
  becomes a number only through `cq*` units or a view timeline. **`calc-size()`** keeps an intrinsic-size basis
  for layout to resolve (`ParseCalcSize`); it can do arithmetic on an element's own content size inside layout
  (`width: calc-size(max-content, size * 2)`), but the result is still a size, not a number.

### 1.7 Value functions

| Function | Main status | Implementation | Cost and caching | Relevance |
|---|---|---|---|---|
| `random()` | stable (153 experimental; 155 experimental; **156 stable**, chromestatus M156) | `CSSMathExpressionRandomFunction`; base value from `StyleEngine::GetCachedRandomBaseValue` (`style_engine.cc:5167`) | default key `auto` = element-scoped, name `ua-<property>-<index>` (`RandomCacheKey::Auto`, `css_math_expression_node.cc:5720`): **fixed per element and property for the element's lifetime**; `--name` without `element-scoped` = one value per document; `fixed <n>` = deterministic `min + n·(max − min)`. Element-dependent random makes the style MPC-uncacheable; a container `style()` query on a value with `random()` evaluates to unknown | no per-frame randomness without script; usable for scene initialisation (css-physics `rain`) |
| typed `attr()` | stable (133) | `ResolveAttrInto` (`style_cascade.cc:2423`): reads the attribute, parses it with the type, **appends `CssText()` of the parsed value** | precision by type (§1.4); `SetHasAttrFunction` → MPC-uncacheable | per-element constants without per-element rules |
| `sibling-index()` / `sibling-count()` | stable (138) | `CSSMathExpressionSiblingFunction::ComputeDouble` (`:5524`) → `NthIndexCache` (counts previous siblings; caches parents with > 32 children, `dom/nth_index_cache.cc:54`) | MPC-uncacheable (`HasSiblingFunctions`) | free indices (js-minus-js scan) |
| `ident()` | **test** (`runtime_enabled_features.json5:1811`) | `ConsumeIdentFunction` (`css_parsing_utils.cc:1717`): idents, strings, integers (incl. `calc()`, `sibling-index()`); in `var()` the name is computed by `ConsumeAndComputeVariableName` (`style_cascade.cc:101`) | with `--enable-blink-features=CSSIdentFunction` in 153: `var(ident("--m" 3))` and `var(ident("--m" sibling-index()))` work; **`var(ident("--m" var(--k)))` does not** (the inner `var()` is still a token when the name is computed). In normal properties `var()` is substituted first, so `anchor-name: ident("--a" var(--k))` should work; `anchor-size(ident(…) width)` **crashed the 153 renderer** | would replace `if()` muxes (js-minus-js read ports, css-physics contact slots); not shipping |
| `inherit()` | experimental (153, 155, 157, main); chromestatus: no milestone | `ResolveInheritInto` (`style_cascade.cc:1859`): parent's substitution text; for a non-inherited property sets `HasExplicitInheritance` on the element and the parent | same as `var()` | `--acc: calc(inherit(--acc) + 1)` measured working down 4 levels with the flag: removes the J/K and A/B parity copies |
| `if()` | stable (137) | `ResolveIfInto`, `EvalIfStyleFeature` (§1.5) | text comparison; cheap | already used |
| `first-valid()` | absent | no keyword in `css_value_keywords.json5` | — | — |
| `env()` | stable | UA variables only (safe areas, titlebar, keyboard, viewport segments) | — | none |
| `@function` | stable (139) | prior survey Q5: uncached, no recursion, MPC-uncacheable | +1.3–1.6 µs per call | dead end |
| `@private` | **new**, experimental (`:1970`) | `CSSParserImpl::ConsumePrivateRule`: typed custom properties renamed to `-ua-private-N`, visible only to the rule and the elements it matches; registered per sheet as `inherits: true`, no initial value | same as registered | name hygiene only |

### 1.8 Counters

**Data.** `counter-reset/-increment/-set` compute into a `CounterDirectiveMap` (`HashMap<AtomicString,
CounterDirectives>`, `core/style/counter_directives.h:159`) on the `ComputedStyle`. Per name: `reset_value_`
(int64), `increment_value_` (int, several increments of one name on one element **saturate**:
`base::ClampAdd`, `:93`), `set_value_` (int). `CombinedValue()` saturates reset + increment to int (`:113`).

**When they update.** `Element::RecalcOwnStyle` marks counters dirty whenever an element's directives change, or
style containment changes (`core/dom/element.cc:5978`); so do node removal and pseudo-element changes. Then:

```
StyleEngine::UpdateStyleAndLayoutTree   RecalcStyle → RebuildLayoutTree → quotes → UpdateCounters()
                                        (style_engine.cc:4322)
Layout                                  size-container restyles run in here and can change directives again
LocalFrameView::UpdateStyleAndLayout    UpdateCounters() again after layout (local_frame_view.cc:3624)
                                        → counter text changed: NeedsLayout → "Third pass" layout (:3656)
```

`StyleEngine::UpdateCounters()` (`style_engine.cc:928`) is a **from-scratch walk of the whole flat tree** from the
document element with a fresh `CountersAttachmentContext`: `EnterObject` per element with a layout object (one
hash-map stack per counter name), `UpdateLayoutCounters` regenerates the text of every `LayoutCounter` under elements
whose `content` isn't `normal`, `LeaveObject`. It visits elements in `display: none` subtrees too (the recursion
doesn't check for layout objects). Measured: one changing counter in a page of 20,000 other elements costs +0.30 ms
per pass when they are `display: none` or `content-visibility: hidden`, +0.45–0.6 ms when visible: **15–25 ns per
element, every pass on which any counter changes.**

**Arithmetic.** Across elements: `base::CheckAdd(current, increment).ValueOrDefault(current)`
(`counters_attachment_context.cc:110`): **an increment that would overflow int32 is skipped**, and the counter stays
(css-lists-3 allows ignoring it). Measured: Σ i·123457 for i = 1..1000 stopped at 2,147,040,047.
Elements without a box (`display: none`, `display: contents`) don't take part (css-lists-3 §4.5); an element with
`contain: style` (including `content-visibility: hidden/auto`) scopes its own increments to its subtree. `counter-reset:
reversed()` (`CSSCounterResetReversed`, experimental) computes its start value by walking the following siblings
(`CalculateInitialValueForReversed`): a suffix sum.

**Text.** `LayoutCounter::UpdateCounter` → `CounterStyle::GenerateRepresentation(int)` (`counter_style.cc:984`) →
`SetTextIfNeeded` (relayout and reshape only if the string changed). Algorithms (`:125–225`): cyclic, fixed (a
lookup table from `first_symbol_value`; any number of symbols), symbolic (repetitions), alphabetic, numeric
(logarithmic), additive (greedy over the weights). **`kCounterLengthLimit = 120`** (`:57`) caps symbolic repetitions,
additive symbol count and `pad` length; past it the fallback style is used (decimal when the fallback cycles). It
counts symbols, not code points: one symbol may be a long string. `range` bounds are int pairs; additive's default
range is ≥ 0; additive, numeric, alphabetic and symbolic get the `negative` prefix/suffix. `speak-as` is `test` only.
`symbols()` became stable on main. `extends` copies the extended style's algorithm and symbols; a cycle of
`extends` makes every member behave as `decimal` (`counter_style_map.cc:159`). `::marker` content is handled the same
way: `UpdateLayoutCounters` searches the pseudo-element's layout subtree for `LayoutCounter`s (`style_engine.cc:944`).
`counter()` is valid only in `content` (and alt text); `attr()` and custom properties can't read a counter.
A counter shown inside a size-container reader updates with the post-layout `UpdateCounters()` and the extra
layout above. Quotes are a depth counter per containment scope
(`core/css/style_containment_scope.cc:41`): `quotes[depth]`, the last pair beyond the list.

### 1.9 The counter adder (built and measured)

`exp/03/adder/`: `mkfont.py` makes "Adder" (fontTools, `unitsPerEm = 1024`): U+E000+k has advance 2^k
(k = 0..14), U+E0FF advance 0. Two additive styles split a value into 15-bit halves:

```css
@counter-style lo { system: additive; additive-symbols: 536870912 "\E0FF", …, 32768 "\E0FF",
                    16384 "\E00E", …, 1 "\E000", 0 "\E0FF"; }      /* bits 0–14 → advances 2^k */
@counter-style hi { system: additive; additive-symbols: 536870912 "\E00E", …, 32768 "\E000",
                    16384 "\E0FF", …, 1 "\E0FF", 0 "\E0FF"; }      /* bits 15–29 → advances 2^(k−15) */
.acc   { counter-reset: acc 0 }
.acc i { counter-increment: acc calc(sibling-index() * 123457) }   /* 64 siblings */
.lo::after { content: counter(acc, lo) }  .r { font: 1024px/0 Adder }   /* 1 unit = 1 px */
#res { --low: calc(100cqw / 1px) }        /* inside fixed readers sized by anchor-size(--lo width), --hi likewise */
```

Results (`adder64.html`, `adder1000.html`):

- 64 elements: lo = 20,512 px, hi = 7,836 px; 7,836 · 32,768 + 20,512 = **256,790,560 = Σ exactly**. The CSS readback
  (`anchor-size()` → size container → `cqw`) computed `--ok: 1` against the constant. *(measured)*
- `counter-increment: acc var(--v)` with a calc-computed `<integer>` `--v` ≥ 10^6 silently drops those increments
  (`1.23457e+06` is not an `<integer>` token, so the declaration is invalid at computed-value time): only the
  i ≤ 8 terms arrived. A literal `<integer>` `--v` worked. *(measured)*
- **Font scale matters:** with `unitsPerEm 1000` at 1000 px, a 16,384-unit glyph measured 16,383.984 px and a
  15,673 px string 15,672.984; with 1024 at 1024 px, 100 × 16,384 measured exactly 1,638,400. Use a power-of-two
  upem and `font-size` = upem px (ENGINE_NOTES 29 is the same constraint). *(measured; mechanism not traced)*
- Cost (`cost_*_2000.html`, noisy): 2,000 elements restyled by an animated inherited `--t`: none 2.1–2.6 ms; a
  registered calc per element 5.7–6.2; a constant `counter-increment` 4.0; a changing `counter-increment` 6.7
  (≈ +1.3 µs per element over constant); with the two readers 6.6–11.3 ms plus 0.5–0.6 ms of layout per frame.

Feasibility verdict in §4 (idea 7).

---

## 2. What it means for the projects

### css-physics

- **The cost model is the parse.** BENCHMARKS §2's 1.27 / 2.61 µs per registered property is §1.2's pipeline:
  the property is parsed, computed and printed back to text on every pass, and every `var()` of it is tokenized
  again. The arithmetic is free in comparison (it folds during parsing). So the levers are: fewer *typed*
  declarations, fewer `var()` hops, fewer math-function nodes, and fewer tokens. Property count stays the
  bottleneck, as BENCHMARKS says.
- **Constants and pass-throughs don't need to be typed.** An unregistered constant costs a third of a registered
  one (0.25 against 0.8 µs here) and keeps its digits; a consumer pays the same parse either way. Anything only
  read through `var()` in a `calc()` can be unregistered. Registration is needed only where the value is used by
  `style()`, interpolated, needs `inherits: false`, or must stop text growth. Bonus: fewer registrations with an
  `initial-value` also shrink the per-animation loop (chapter 04 §1.4). *(code + measured; the gain per page:
  inference)*
- **`style(--flag: 1)` is a miniature cascade** (§1.5). The cheaper forms are known (`style(--flag)` 0.5 µs, `BOOLQ`).
  For values ≥ 256 or negative, use `calc(N)` in the query (or `if()`), not a literal.
- **`progress()`** for every normalization (31% cheaper here, 23% in PRIMITIVES).
- **Digit extraction:** 3 functions ≈ +1.5 µs over a plain `calc(var())`. `round(down, …) − 10 · round(down, …)` is
  dearer. Where the digit is known to be 0 or 1 (`nm{j}_{m}` words, before summation), `mod(round(down, w / 2^k), 2)`
  needs no `sign()`.
- **Digest capacity** (gen3d.py:522–535, CLAUDE.md "6 bodies per decimal word"): the binding rule is "integral and
  |v| ≤ 999,999 prints exactly" (§1.4). A base-B word holds ⌊log_B 10^6⌋ digits: base 10 → 6, base 4 → 9, base 3
  → 12, base 2 → 19. The per-body `nm{j}_{m}` words hold 0/1 flags, but they are summed into `SN`/`SP`/`SB`, whose
  digits are counts, so one base must exceed the largest count: base 4 holds 9 bodies per word if counts stay ≤ 3
  (NW 11 → 8 at 64 bodies). If CL 8559024 lands and the words become `<integer>`: base 10 → 9 digits, base 4 → 15.
  *(code + measured; applicability: inference)*
- **Registers:** the view-timeline channel carries ≈ 24 bits (1/16 px over 10^6 px, chapter 04 finding 4), but a
  `<number>` register printed through `var()` keeps 6 significant digits (≈ 20 bits). A register whose keyframes
  write a **scaled `<integer>`** (`from { --R: 0 } to { --R: 16000000 }`) keeps all 24 bits through `var()`,
  because interpolation produces `kInteger` (§1.4, measured exact). Worth it only where a register's 6th digit
  matters. *(code + measured)*
- Nothing in `random()`, `sibling-index()` or typed `attr()` removes the N² pair rules. `ident()` would, but it is
  test-only and doesn't take `var()` in `var(ident(…))`. `inherit()` would remove the J/K accumulator copies (but
  not their work) if it ever ships.

### js-minus-js

- **ENGINE_NOTES 1** is wider than written: calc-computed `<integer>`s outside 0..255 (**negatives included**) never
  match a literal in `@container style()`, `style(--v: var(--w))` fails too, and `style(--g)` misfires at a
  calc-computed initial value ≥ 256. Two fixes that work today and keep working after CL 8559024: write dispatch
  queries as **`style(--v: calc(N))`** (one rule per id, same cost class as a literal), or test in `if()`, which
  compares text. Splitting ids below 256 is unnecessary. Caveat: a container value that is a literal (not calc)
  would then stop matching (row 4 of the §1.5 table); keep each dispatch property consistently computed. *(measured)*
- **ENGINE_NOTES 2**: the exact rule is "integral and |v| ≤ 999,999 → exact, else `%.6g`", which is why |v| < 2^19
  works. Literal and **animated** `<integer>`s keep int32: the registers (view-timeline keyframes) keep every bit
  the ≈ 24-bit timeline channel delivers (chapter 04); the limit bites only on calc-computed values crossing
  `var()`. If CL 8559024 lands, calc-computed
  `<integer>`s also become int32 (and clamp at 2^31 − 1): `gen_fvm4.py` could widen words; re-run `var-6-digits`.
- **ENGINE_NOTES 3 is wrong as stated.** Registered numbers are doubles (`CSSNumericLiteralValue::num_`,
  `InterpolableNumber`), `<integer>` serializes as int32; the measured exact cases include 2^24 + 1 and 2^31 − 1
  through `var()` and (2^24 + 1) × 3 inside `calc()`. Floats appear in `<length>` computed values (`Length`), scroll
  offsets and layout (LayoutUnit is 1/64 px, ±2^25 px). Keep |v| < 2^24 only for values that go through layout.
- **Counters cost a whole-document walk per pass.** The state line's `counter-set: c<pos> var(--i<pos>)` and the
  console's `counter-set: ch var(--code)` change on most passes, so `UpdateCounters()` re-walks all ~20K elements:
  ≈ 0.3–0.5 ms per pass measured on a 20K-element page, `display: none` RAM groups included. Small against 50–100 ms
  per frame, but it is per pass. The console readers' `counter-set` is computed inside layout (their `--code` comes
  from `cqi`), so a console change also re-runs layout once more inside the same `UpdateStyleAndLayout`
  (`local_frame_view.cc:3656`): a lead for ENGINE_NOTES 38 ("the full page always 3 passes") worth one trace.
  *(code + measured; ENGINE_NOTES 38 link: inference)*
- **`counter-set` with a `var()` of a calc-computed `<integer>` ≥ 10^6 is silently invalid** (§1.9); keep displayed
  values below 10^6 or literal/animated.
- **4,229 `@property` rules** (ENGINE_NOTES 4) cost nothing per element unless declared there. The "every animated
  element" cost is chapter 04's snapshot loop over every registration with an `initial-value`. Temps that are only
  read through `var()` inside `calc()` and never queried with `style()` could be unregistered or `syntax: '*'`
  without `initial-value`, which keeps them out of that loop. Unregistered properties always inherit, though, so
  `inherits: false` temps need `'*'`. *(code; gain: inference)*
- **`ident()`** would turn the read ports' 2-level `if()` mux (≤ 128 `style()` tests) into one
  `anchor-size(ident("--c" var(--a)) width)`, but it is test-only and that exact form crashed 153. Keep the
  `var-ident` watch probe; add `anchor-name: ident("--a" var(--k))` (substitution-first form) to it.

### paint

- Its row-width readback `calc(100cqw / 1px)` → registered `<integer>` is calc-computed: exact below 10^6, and
  `@container style()` on it is subject to ENGINE_NOTES 1 above 255. paint's values are colour indices < 16, so
  neither bites. Nothing else in this chapter touches paint.

---

## 3. What's changing

| Item | 153 | 155 | 156 | 157 | main (158) |
|---|---|---|---|---|---|
| `random()` (`CSSRandomFunction`) | experimental | experimental | **stable** | stable | stable; keys gain `property-scoped`/`property-index-scoped`, `@function` call counts |
| `ident()` (`CSSIdentFunction`) | test | test | test | test | test |
| `inherit()` (`CSSInheritFunction`) | experimental | experimental | experimental | experimental | experimental |
| `CSSArgumentGrammar` (resolve substitutions in function arguments first; only `attr()` uses it) | test | test | test | test | test |
| typed arithmetic (`CSSTypedArithmetic`) | stable | stable | stable | flag removed | flag removed, always on |
| `symbols()` (`CSSCounterStyleSymbolsFunction`) | experimental | stable | stable | stable | stable |
| `@private` (`CSSPrivate`) | absent | experimental | experimental | experimental | experimental |
| `CSSCalcEarlyNaNAndInfFolding` | absent | absent | — | off (no status) | off (no status) |
| `CSSCounterResetReversed`, `CSSListCounterAccounting` | experimental | experimental | experimental | experimental | experimental |
| `link-parameters` property (`CSSLinkParametersProperty`) | absent | absent | experimental | experimental | experimental |
| Number serialization | `String::Format("%.6g")` | | | | `absl::StrFormat("%.6g")` (same output, round-half-even kept) |
| calc-computed `<integer>` → `kNumber` (ENGINE_NOTES 1, 2) | yes | yes | yes | yes | **yes**; CL 8559024 open |

Diffs 153 → main of `core/css/css_variable_data*`, `css_numeric_literal_value*`, `css_value_pool*`,
`css_syntax_definition.cc`, `properties/longhands/custom_property.cc`, `counters_attachment_context.cc`,
`counter_style.cc`, `layout/layout_counter.cc`, `style/style_variables.h`: type renames (`unsigned` → `uint32_t`),
`base::Reversed` → `std::views::reverse`, `StyleRef()` → `Style()`. **No behaviour change in storage, substitution,
parsing or serialization.** `css_math_expression_node.cc` (286 changed lines): category computation moved from the
`kAddSubtractResult` table to `CSSMathType` addition, `pow`/`hypot`/`log` through shared `Evaluate*` helpers,
`progress()` NaN guard, `random()` key parsing, `ReferenceDefaultAnchor()`. `style_cascade.cc` (205): precomputed
`:hover` styles (`ApplyPrecomputedHover`), `@function` navigation queries, `random()` inside `if()`/`style()`,
`env()` fallback through `AppendDataWithFallback`. Main also dropped the `container_tree_scope` argument of
container lookup (chapter 02). Statuses for 155/157 are from `$SP/src/versions/{155,157}`, 156 from gitiles (8078).

Work in progress visible in the code: "TODO(andruud): Produce tokens directly from CSSValue"
(`style_builder_converter.cc:3716`): the one change that would remove a tokenization per registered property and the
`%.6g` cut at once. Nothing on main implements it. "TODO(sesse): It would be nice if we had some way of combining
ResolveTokensInto() and the re-tokenization" (`style_cascade.cc:1473`). "We may want to consider caching this
value" (`css_unparsed_declaration_value.cc:19`).

---

## 4. Ideas

Ranked by expected value × confidence.

1. **js-minus-js: replace "split ids below 256" by `style(--v: calc(N))`** *(code-backed, measured)*. One query
   per id, forward-compatible with the fix. Cheapest check: a `style-int-256` variant in `engine/check.js` with a
   `calc(N)` query at 256, 1000 and −1; then regenerate one parser-variant family with ids ≥ 256.
2. **Fix the documents** *(code-backed, measured)*: ENGINE_NOTES 1 (negatives; `var()` queries; `style(--g)` at a
   calc-computed initial ≥ 256; the `calc(N)` workaround; `if()` unaffected), ENGINE_NOTES 2 (the 999,999 rule;
   animated `<integer>` keeps int32), ENGINE_NOTES 3 (doubles, not floats), css-physics CLAUDE.md ("≈ 5 µs per digit
   extraction" is three functions on top of a property). Probes to add to `engine/check.js`: `style-int-neg`,
   `if-style-bool` (watch for a fix), `var-int-animated`.
3. **css-physics: unregister constants and pass-throughs** *(code-backed; gain inferred)*. Expected: ~0.5 µs per
   converted declaration per pass, plus a shorter animation snapshot loop. Experiment: a generator flag that emits
   no `@property` for names used only inside `calc(var())`, then `ab.js` on the frozen 48 pile with an A-vs-A
   control. Risk: text growth if a name was materializing a long expression; check with the 2 MiB cap in mind.
4. **css-physics: `progress()` and leaner extraction forms** *(measured)*. `progress()` wherever `clamp((v − a) /
   w, 0, 1)` appears; `mod(round(down, w / B^k), B)` without `sign()` where the digit is 0/1. Small, safe.
5. **css-physics digests in a smaller base** *(code-backed; applicability inferred)*. The word limit is the
   999,999 rule, so a base-B digest holds ⌊log_B 10^6⌋ digits; the base must exceed the largest per-digit count of
   the summed words. Base 4 (counts ≤ 3) holds 9 bodies per word instead of 6: NW 11 → 8 at 64 bodies, fewer
   `nm{j}_{m}` and `S*` properties. First check the largest count a digit reaches in a pile (a digit ≥ 10 would
   already carry into its neighbour in base 10).
6. **Wider words from animated `<integer>` registers** *(code-backed, measured)*: js-minus-js registers and
   css-physics registers that need more than 6 digits through `var()` can be `<integer>` keyframe targets (int32
   exact). For js-minus-js the 20-bit word limit comes from calc-computed temps, not registers, so this helps only
   where a register is consumed directly.
7. **Counters as exact adders** *(measured: works; value: speculation)*. Exact int32 sums over any set of elements
   in document order, including siblings (inheritance can't), read back as a width via an additive style and a
   power-of-two-upem font. Costs: ≈ 1.3 µs per incrementing element per pass, a whole-document walk (15–25 ns per
   element) on every pass any counter changes, and a layout readback hop (the value arrives inside layout, like a
   size-container reader, or next pass through a view timeline). Verdict: **not a fit for css-physics's in-step
   math** (values flow down the chain within one style pass; a counter's result only exists after layout), and
   no cheaper than `calc()` per term. It pays only where a sum must cross siblings and full int32 matters, e.g.
   a js-minus-js checksum over RAM leaves or a census of the 16K leaves. A `fixed` counter style over the same
   font is a 1-D lookup table evaluated in layout (any int → any width). Cheapest next experiment: time
   `adder64.html` scaled to 1,000 incrementing leaves inside `contain: strict` with the readers outside.
8. **`syntax: '*'; inherits: false` as a precision-keeping, non-inherited temp** *(code-backed, measured)*. It
   carries text (full digits), doesn't inherit (unlike unregistered), needs no `initial-value` (so it skips
   chapter 04's loop), and costs ≈ a typed property (0.85× in a paired run). Use where a temp must not restyle a
   subtree (ENGINE_NOTES 5, 41) yet should keep digits.
9. **Watch items** *(docs)*: CL 8559024 (re-check css-physics digests and js-minus-js word width when it lands);
   `inherit()` shipping (removes parity copies in both projects); `ident()` shipping with substitution-first
   arguments (dynamic indexing; it would retire the `if()` muxes); the "tokens directly from CSSValue" TODO (would
   remove the 6-digit cut and a tokenization per property).
10. **Precomputing `style()` query values** *(speculation, engine-side)*: a literal query value is
    computationally independent and could be computed once per rule instead of building a `ComputedStyle` per
    evaluation. Nothing the projects can do, but worth mentioning in a report if the user files one on 571450199.

---

## 5. Possible bugs

1. **`@container style()` on calc-computed `<integer>`s** (known: [571450199](https://issues.chromium.org/issues/571450199),
   CL 8559024 open). New details for the report: negative values fail too; `style(--v: var(--w))` fails;
   `style(--g)` is true when a calc-computed value equals an initial value ≥ 256 (`probe/bool.html`). Code:
   `style_builder_converter.cc:3606` (kNumber), `css_numeric_literal_value.cc:68–77` (pool stores kInteger),
   `:326` (type-strict `Equals`). Spec: css-conditional-5 §6.2, quoted in §1.5.
2. **`if(style(--x))` is true for a registered property at its initial value** (`style_cascade.cc:2841`:
   `return computed_data ? kTrue : kFalse`; a registered property always has data). Measured: `--f` initial 0 and
   `--g: 7` with initial 7 both select the true branch, while `@container style(--f)` is false. Spec:
   css-values-5 `if()` uses `<style-query>`; css-conditional-5 §6.2: "A style feature without a value evaluates to
   true if the computed value is different from the initial value for the given property." WPT has no case for a
   registered property at its initial value. Reports not searched.
3. **`if(style())` compares serialized text, so 6-digit rounding gives false positives**: `--n: 1048575`
   (`<number>`) matches `if(style(--n: 1048580))` (`style_cascade.cc:2880`). Spec: computed values must match.
   Fixing the serialization would fix this too.
4. **6 significant digits through `var()`** (known: [40266999](https://issues.chromium.org/issues/40266999)).
   Mechanism: `%.6g` at `css_numeric_literal_value.cc:198` on the substitution path
   (`style_builder_converter.cc:3717`). Corollary to add: `counter-increment`/`counter-set: c var(--x)` silently
   drops values ≥ 10^6 when `--x` is calc-computed (§1.9).
5. **Test-only features** (low priority): `anchor-size(ident("--a2") width)` crashes the 153 renderer with
   `--enable-blink-features=CSSIdentFunction` (any `ident()` argument; `probe/ia2.html`); and `var(ident("--m"
   var(--k)))` doesn't resolve the inner `var()` (`style_cascade.cc:101`), against css-values-5 §8.8 ("Substitute
   arbitrary substitution functions in arg, then parse it as `<ident-arg>+`").

## Open questions

- Why a 1000-upem font at 1000 px drifts (−1/64 px at 12,288 px, −2.75 px at 1,638,400 px) while 1024 upem at
  1024 px is exact: somewhere on the scale path from Skia/Fontations advances to HarfBuzz 16.16 positions
  (chapter 06's area).
- Whether the post-layout `UpdateCounters()` → "Third pass" layout is the cause of js-minus-js's always-3-passes
  (ENGINE_NOTES 38): one `invalidationTracking` trace with the console readers removed would tell.
- Whether CL 8559024 lands in 158 or later; nothing on main yet.
- The per-step split inside the 0.5 µs "typed" increment (parse vs. `CssText` vs. re-tokenize vs. second trie
  insert) needs a profiler (`perf` on a release build); the microbenchmarks only separate the stages coarsely.
