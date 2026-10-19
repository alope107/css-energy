# 02. Blink's style engine: from invalidation to computed style

Scope: how a stylesheet becomes a `RuleSet`, how one element's rules are matched (container queries included), how
the cascade computes its style, how a change propagates to descendants, and what the caches skip. Neighbours:
[01](01-lifecycle.md) (when recalcs run), [03](03-values-and-properties.md) (custom-property values, `var()`
substitution, calc, the per-declaration cost decomposition, precision), [04](04-animations-and-scroll.md) (how
animations feed the cascade; ENGINE_NOTES 4), [05](05-layout.md) (size-container recalc inside layout),
[09](09-roadmap.md).

Source: Chromium main `22b3b159` (M158) unless marked 153 (branch 8010), 155 (8059), 157 (8103). Paths are from the
src root with `third_party/blink/renderer/` shortened to nothing: `core/css/…` means
`third_party/blink/renderer/core/css/…`. Experiments: headless Chromium 153.0.8010.12 on the mini PC while other
agents ran, so absolute times are inflated and noisy; read ratios. Pages, scripts and commands: Appendix.
Labels: *(code)*, *(measured)* (run for this chapter), *(docs)*, *(inference)*.

## Findings in brief

1. **A `style()` gate is evaluated once per `@container` block per pass in which the container's custom properties
   changed, not once per rule.** The result cache (`ContainerQueryEvaluator::results_`) is keyed by the
   `ContainerQuery` object, and every style change of the container re-evaluates every cached query
   (`ComputeStyleChange`). Measured: 5,000 false gates as 5,000 blocks cost 1.0–2.0 µs each per pass; the same 5,000
   rules inside **one** block cost 0.1 µs each; 5,000 blocks whose container doesn't change cost 0.1 µs each.
   *(code + measured)*
2. **Stale gates keep costing.** A query evaluated once stays in the container's cache, and is re-evaluated on every
   later style change of the container, even after its rules stop being tested (owner name gone), until some cached
   result on that container flips. Measured: 5,000 gates whose name vanished after 0.3 s still cost 4.8–9.9 ms per
   pass against 0.5 ms; one flip brought it back to 0.54 ms. In css-physics this is every pair gate of every body
   that was awake earlier, at every level where nothing has flipped since. *(code + measured)*
3. **Absent-name rejection is cheap only when the name repeats.** `FindContainer` walks every flat-tree ancestor and
   scans each one's name list (`TODO(crbug.com/1213888): Cache results`); the walk result is cached per element
   per distinct name. BENCHMARKS §2's "0.2 µs + 0.6–0.9 ns × depth × names" used a different name per rule. With
   one name repeated: 0.07 µs per rejected rule. *(code + measured)*
4. **Container queries come after selector matching; nothing pre-filters them.** Order per rule: bucket (id, class,
   attribute, tag, universal) → subject Bloom filter → ancestor Bloom filter → selector → `@container`, innermost
   query first, `and`/`or` short-circuiting. A rule in another bucket costs nothing; a rejected `@container` rule
   also scans its whole declaration block (`AffectsAnimations`), forcing a lazy block to parse. *(code)*
5. **A changing inherited custom property fully restyles every element below that declares or references any custom
   property.** The children of an element with custom declarations or `var()` get `kRecalcChildren` (full
   `ResolveStyle`, ~2–3 µs plus their declarations); below an element with neither, children with neither get a
   ~0.9 µs copy instead. A constant, even non-inherited, declaration is enough to lose the copy. Propagation stops
   below an element only if its **entire** inherited custom-property set comes out equal. ENGINE_NOTES 41 is right for its
   case and the reason is now known: redeclaring one property stops nothing while another changing property (the
   driver) still flows; redeclaring all of them stops it (301 → 2 restyles per pass). `content-visibility: hidden`
   is a firewall (301 → 2). *(code + measured)*
6. **ENGINE_NOTES 6's sharing is the matched-properties cache, and 153 disables it for any element with
   `container-name`.** Any tree-scoped name (`anchor-name`, `animation-name`, `view-timeline-name`,
   `scroll-timeline-name`, `timeline-scope`, `animation-timeline` names, `view-transition-name`, a counter-style
   `list-style-type`, `url(#…)`, any `@function` call) makes an element uncacheable; in 153 `container-name` too
   (fixed in 155). Measured, 1,000 identical siblings × 50 registered declarations: 1.3–1.7 ms shared, 62–133 ms with
   `anchor-name` or (153) `container-name`. *(code + measured)*
7. **An element that both declares many properties and runs an animation pays ~1.6× for its declarations.** The
   animated pass re-applies the whole cascade (`map_.ClearAppliedFlags()`), and base-style reuse is off whenever a
   custom property animates (unchanged on main). Measured, 8,000 declarations: 17.4–18.6 ms on the animated element,
   10.0–11.7 ms on its child. css-physics `#LS` carries 830 declarations and 630 animations at 48 bodies. *(code +
   measured)*
8. **`if()` costs ~0.5 µs per condition tried plus the tokenization of its whole text, every evaluation.** The
   condition is re-parsed each time (`CSSIfParser` per branch) and skipped branches are still tokenized. Measured,
   1,000 declarations with a 32-branch `if()`: +4.8 µs each when the first branch matches, +22.6 µs when the last
   does. *(code + measured)*
9. **Matched-properties cache hit rate on the projects' chains is ~0%** (unique levels, parent state in the key);
   in 155+ the levels become cacheable and add one entry per level per pass for nothing. *(code; inference for
   the rate)*
10. **Load: parsing ~80–95 MB/s, everything else small.** 20.5 MB of inline CSS (48 bodies): parse 267 ms, RuleSet
    1.0 ms, active-sheet update incl. 24,917 `@property` 17 ms. Inline sheets parse declarations eagerly; lazy parsing
    for inline sheets is a new flag (157+, off) that wouldn't help: nearly every rule gets visited. The same trace
    shows a **1.4 s first Layout** (0.45 s at 32 bodies): not style. *(measured)*
11. **Limits:** 2^18 = 262,144 selectors per stylesheet's `RuleSet` (rules past it are silently dropped), 8,192
    selectors per selector list, 65,535 declarations per block and 65,535 matched blocks per element (more and the
    block or the rest are ignored). *(code)*
12. **css-physics depends on a taint deviation.** Animation taint survives inheritance (measured) and is dropped by
    a registered property (04 finding 5). `container-name: var(--AN)` works only because `--AN` is derived through
    registered properties; if Blink made taint "infectious" as the spec says, every owner name would go invalid.
    *(code + measured)*

---

## 1. How it works

### 1.1 The pipeline

```
 <style>/<link> text
   │ CSSParserImpl::ParseStyleSheet ─ StyleRule{selectors, CSSPropertyValueSet (or lazy offset)}
   ▼
 RuleSet per StyleSheetContents ── RuleData per selector, bucketed: id / class / attr / tag / universal / …
   │                                intervals: rule position → ContainerQuerySet, CascadeLayer, StyleScope
   ▼  (style dirty: StyleRecalcRoot; Element::RecalcStyle walks down with a StyleRecalcChange)
 Element::RecalcOwnStyle
   ├─ PropagateInheritedProperties  (cheap path: clone old style, copy parent's independent inherited fields)
   └─ StyleResolver::ResolveStyle
        ApplyBaseStyle ── CanReuseBaseComputedStyle? (animations only) ── MISU incremental? (inline style only)
          ApplyBaseStyleNoCache
            ElementRuleCollector: buckets → Bloom → selector → @container → MatchResult (blocks + flags)
            MatchedPropertiesCache: hit → clone cached style, done
            miss → StyleCascade::Apply: CascadeMap → resolve (var(), if(), @function) → StyleBuilder
        ApplyAnimatedStyle (if animations/transitions) → second StyleCascade::Apply with interpolations
   ComputedStyle::ComputeDifference(old, new) → child StyleRecalcChange
   ContainerQueryEvaluator::ApplyScrollStateAndStyleChanges → re-evaluate cached queries → more child flags
```

### 1.2 Stylesheet → `RuleSet`

- **Parse.** `CSSParserImpl::ParseStyleSheet` (`core/css/parser/css_parser_impl.cc:492`) builds `StyleRule`s. With
  `CSSDeferPropertyParsing::kYes` a rule keeps only an offset into the sheet text and parses its block on first
  `StyleRule::Properties()` (`core/css/style_rule.cc:526`). Network sheets use it; **inline `<style>` sheets don't**:
  `StyleEngine::CreateSheet` passes `kNo` unless `LazyParseInlineStyleSheets` (new in 157, no status, so off) is set
  (`core/css/style_engine.cc:1254`). Custom-property values are stored as text whether registered or not (03 §1.1).
  No off-thread stylesheet parsing exists (`core/css/threaded/` is a test of thread-safe value parsing). *(code)*
- **Bucket.** `RuleSet::AddRule` (`core/css/rule_set.cc:836`) makes one `RuleData` per complex selector
  (20 bytes, `rule_set.h:194`: rule pointer, selector index, position, specificity, flags, a slice of a shared
  Bloom-hash array, a "subject filter") and files it under the rightmost compound's most selective key: id, else
  class, else attribute, else tag, else universal (plus special buckets for `:link`, `:focus`, `::part`, `:host`…).
  `#L5{…}` lands in `id_rules_["L5"]` and is never visited by any other element. Rules are flagged `IsEntirelyCoveredByBucketing` when the bucket key is
  the whole selector, so matching skips the selector check entirely. *(code)*
- **Conditions are not on the `RuleData`.** `@container`, `@layer` and `@scope` are recorded as intervals over rule
  positions (`RuleSet::Interval<T>`, `core/css/rule_set.h:598`), one interval per change of the enclosing
  `ContainerQuerySet` pointer. A `ContainerQuerySet` holds the comma-separated queries of one `@container` prelude
  and a `parent_` pointer for nesting (`core/css/container_query_set.h`). Each `@container` block in the text is a
  distinct set object, even if two blocks are textually identical. *(code)*
- **Limits** *(code)*: positions are 18 bits; `if (rule_count_ >= (1 << RuleData::kPositionBits)) return;`
  (`rule_set.cc:848`) silently drops rules past 262,144 selectors in one stylesheet's `RuleSet`. Selector index is 13
  bits (8,192 selectors per list). `ExpandCascade` emits nothing for a block over 65,535 declarations or past the
  65,535th matched block (`core/css/resolver/cascade_expansion.h:27`). css-physics at 96 bodies has ~10k `@container`
  blocks, far under the limit; a generator that splits per declaration would not be.
- **Mixins** (`@mixin`/`@apply`, `CSSMixins` experimental in 153–main, chromestatus "Proposed") are expanded at
  `RuleSet` build: `RuleSet::ApplyMixin` (`rule_set.cc:1193`) re-adds the mixin's child rules under the applying
  rule, with a `MixinParameterBindings` object that the cascade resolves per element like `@function` arguments.
  They shrink the text, not the rule count or the per-element work, and parameters can't name properties.
  *(code)*

### 1.3 Matching one element

`ElementRuleCollector::CollectMatchingRulesInternal` (`core/css/element_rule_collector.cc:810`) visits, in order,
UA shadow-pseudo, id, each class, each attribute name, `input[type]`, link, focus, root, tag and universal buckets of
every active `RuleSet`. For each `RuleData` in a bucket, `CollectMatchingRulesForListInternal` (`:576`):

1. `RejectElement` (subject Bloom filter of the element's classes/attributes) or `FastRejectSelector` (the parent
   stack's Bloom filter of ancestor ids/classes/tags, for descendant combinators) → next rule (`:606`).
2. Selector: skipped if covered by bucketing (`:634`), `EasySelectorChecker` for simple compounds (`:644`),
   else the full `SelectorChecker`.
3. Only now `container_query_seeker.Seek(position)` (`:677`) and `EvaluateAndAddContainerQueries` (`:299`): for
   the innermost `ContainerQuerySet` first, then each `Parent()`, each set true if any of its comma-separated queries
   is true. A false set ends the rule; then `AffectsAnimations(rule_data)` (`:692`) scans **every declaration of the
   rejected rule** for `animation-*`/`all`, which also forces a lazy block to parse.
4. `DidMatchRule` (`:716`) appends the rule with its layer order; later sorted by specificity and position and
   turned into `MatchResult` blocks (`AddMatchedProperties`, which records each block's cached content hash).

`Seeker` is a forward linear scan (`core/css/seeker.h:31`) created per bucket list, so each element walks the
container-query intervals from the start of the sheet up to its last matching rule: O(blocks in the sheet) per
element per pass. At 48 bodies that is ~4,000 steps per level; at 96 bodies ~10k blocks × 99 levels ≈ 1M steps,
on the order of 1 ms per pass. Minor, but it grows like N³. *(code; cost: inference)*

There is **no pre-filter for container queries**: no Bloom filter or index over container names, and the query is
not consulted before the selector. The selector is the only cheap gate. *(code)*

### 1.4 Container queries

**Finding the container.** `ContainerQueryEvaluator::EvalAndAdd` (static, `core/css/container_query_evaluator.cc:160`)
gets a starting element (`DetermineStartingElement`: the flat-tree parent for style/name queries; the nearest size
container, tracked in `StyleRecalcContext`, for size queries, so size lookups don't walk) and calls
`CachedContainer`: a per-`ElementRuleCollector` hash map from `ContainerSelector` (name + required type flags) to the
found element (`:68`). On a miss, `FindContainer` (`:120`):

```cpp
// TODO(crbug.com/1213888): Cache results.
for (Element* element = starting_element; element;
     element = FlatTreeTraversal::ParentElement(*element)) {
  if (const ComputedStyle* style = element->GetComputedStyle())
    if (style->StyleType() == kPseudoIdNone && Matches(*style, container_selector))   // type, then
      return element;                                                                 // name list .Contains()
}
```

`NameMatches` is `style.ContainerName().Contains(name)` (`:49`): a linear scan of the ancestor's names. A present
name stops at the first ancestor that has it; an **absent name walks to the document root**, costing
depth × (1 + names per ancestor) comparisons, once per distinct name per element per style resolution. In 153 the
cache key was a garbage-collected `ScopedContainerSelector` allocated per insert and the names a vector of
`ScopedCSSName` pointers; 155 made `container-name` a plain `Vector<AtomicString>` (§3). *(code)*

**Name-only queries** (`@container b5 { … }`) return true as soon as the container is found (`if
(!query.Query()) return true;`, `:173`): no evaluator, no cache entry. *(code)*

**Evaluation and its cache.** Otherwise the container's own `ContainerQueryEvaluator` runs
`EvalAndAdd(query, change, match_result)` (`:234`): `results_.insert(&query, Result())` keyed by the **query
object**; a cached entry is reused unless it depends on viewport/root/container units, else `Eval` runs
`MediaQueryEvaluator::Eval` over the query's expression tree. `change` records whether the container was the
starting element (`kNearestContainer`) or further up (`kDescendantContainers`). *(code)*

**What a `style()` test costs.** `MediaQueryEvaluator::EvalStyleFeature` (`core/css/media_query_evaluator.cc:1785`):

- Equality `style(--g: 1)`: `StyleResolver::ComputeValue(container, name, value)` (`style_resolver.cc:3212`)
  builds a `StyleResolverState`, a `StyleCascade`, clones the container's `ComputedStyle`, allocates a
  `MutableCSSPropertyValueSet` with the one declaration, runs a full `cascade.Apply()` (for a registered property:
  parse, compute, serialize), takes the new style and reads the property back, then compares `CSSValue`s. 03 §1.5
  covers the comparison; this is the throwaway mini-cascade that makes a present-name false gate ~0.6 µs dearer than
  an absent one.
- Boolean `style(--g)`: the same with `initial` as the value (cheaper: no literal to parse; 0.50 vs 0.80 µs in
  BENCHMARKS §2).
- Range `style(--h > 9)`: another `StyleResolverState` with a cloned container style, **a new
  `CSSParserContext` per evaluation** (`:1807`), and `CoerceIntoNumericValue` (a parse) for the reference and each
  bound: two to three parses, hence 1.7–2.3 µs.
- `and`/`or`/`not` short-circuit left to right (`core/css/conditional_exp_node.cc:76`, `:95`); each `style()` leaf
  in an `or` is its own `ComputeValue`. The cache stores only the whole query's result.

**Invalidation: re-evaluating everything, every time.** When the container itself restyles,
`Element::RecalcOwnStyle` calls `ApplyScrollStateAndStyleChanges` (`element.cc:6142` →
`container_query_evaluator.cc:920`). If the style changed and the inherited or non-inherited custom-property sets
differ (`:998`), `StyleContainerChanged` → `ComputeStyleChange` (`:778`) runs `Eval` on **every cached style query**
to see whether any result flipped. If none did, nothing is cleared and the children's matching hits the cache. If any
did, `ClearResults` (`:720`) rebuilds `results_` without the style entries (all of them: they share the same
`change`), the children get `kRecalcStyleContainerChildren` (or `…Descendants` for a non-parent container, which
traverses the whole subtree), and the children's matching evaluates every query again. *(code)*

So per container per pass in which its custom properties changed: one `ComputeValue` per distinct query object ever
evaluated there, two in a pass where any of them flips. Nothing removes an entry whose rules stopped being evaluated
(name gone, element moved, rule now rejected earlier) except such a flip, or the evaluator being dropped (the element
stops being a container or gets no style). Measured (E2, E8, E10) *(measured)*:

| 5,000 rules on one element, `@container pres style(--g: 7)` false | per pass | per rule |
|---|---|---|
| no rules (baseline) | 0.08–0.16 ms | — |
| one block per rule, container's custom properties change every pass | 5.0–10.6 ms | 1.0–2.0 µs |
| the same 5,000 rules inside **one** `@container` block | 0.59–0.62 ms | 0.1 µs |
| one block per rule, container's custom properties never change | 0.57–0.59 ms | 0.1 µs |
| name present for 0.3 s, then absent (rules no longer reach the evaluator) | 4.8–9.9 ms | 1.0–2.0 µs |
| same, never present | 0.45–0.52 ms | 0.07 µs |
| present then absent, then one result flip | 0.54 ms | 0.07 µs |
| absent name (the same name on every rule), 1 declaration per rule | 0.49–0.51 ms | 0.07 µs |
| same, 60 declarations per rule | 0.61–0.69 ms | 0.10 µs |

The last two rows are the `AffectsAnimations` scan: ~0.5 ns per declaration of a rejected rule.

### 1.5 `ResolveStyle`, base-style reuse and the matched-properties cache

`StyleResolver::ResolveStyle` (`style_resolver.cc:1420`) builds a `StyleResolverState` and a `StyleCascade` on the
stack, then `ApplyBaseStyle` (`:2123`) chooses:

1. **Base computed style reuse** (`CanReuseBaseComputedStyle`, `:3106`): only when the recalc was caused by the
   element's own animations (`IsAnimationStyleChange`) and none of these hold: animating any custom property,
   `revert`, a font-affecting property with `em` units, `line-height` with `lh`, zoom, an `!important` animated
   property, `position-try`/anchor functions, `display: none` base with `display` animated. Then the cached base is
   cloned and only interpolations are applied. Unchanged 153 → main. *(code)*
2. **MISU** (incremental inline style, `CanApplyStyleIncrementally`): only for `style=""` changes from script.
3. **`ApplyBaseStyleNoCache`**: rule matching, then the MPC, then the cascade.

**The MPC** (`core/css/resolver/matched_properties_cache.cc`). Key: a hash over the matched blocks' content hashes
(each block's hash computed once and cached on the `CSSPropertyValueSet`), mixed with the parent's inherited-variables
hash, a few inherited bit fields, the parent font size and the layout parent's `display` (`style_resolver.cc:2975`).
A hit needs the same blocks (content-equal), a parent that is the same pointer or
`InheritedEqualIncludingInheritedVariables` (value equality, `matched_properties_cache.cc:180`), and a compatible
StyleAdjuster type; it clones the cached style and **skips the entire cascade**. Not stored when
(`IsStyleCacheable`, `:352`; `IsCacheable`, `:391`): `attr()`, zoom ≠ 1, container-relative units, `anchor()`/
`anchor-size()`, `sibling-index()`/`sibling-count()`, `if(media())`/navigation queries, element-dependent `random()`,
a cascade filter, a shadow-boundary `user-modify` mismatch, or **any tree-scoped reference**. The latter is set by
`StyleBuilderConverter::ConvertCustomIdent` (`style_builder_converter.cc:2304`) and friends, i.e. by `anchor-name`,
`position-anchor`, `animation-name`, named `animation-timeline`, `scroll-/view-timeline-name`, `timeline-scope`,
`view-transition-name`, counter-style `list-style-type`, `url(#id)`, and every `@function` call. In 153 also
`container-name` (`ConvertContainerName` returned a `ScopedCSSNameList`); 155+ stores it unscoped. Entries are kept
until GC, which prunes to 300 LRU entries when over 500 (`:477`). *(code)*

E5 (1,000 identical siblings, 50 registered declarations each, parent animates `--t`) *(measured)*:

| Sibling rule | style per pass |
|---|---|
| plain | 1.3–1.7 ms |
| + `anchor-name: --q` | 62–133 ms |
| + `container-name: foo` (153) | 62–82 ms |
| gated by a true `@container pa style(--t)` instead | 2.1–2.5 ms |

### 1.6 The cascade

`StyleCascade::Apply` (`core/css/resolver/style_cascade.cc:294`):

- **Collect.** `ExpandCascade` (`cascade_expansion-inl.h`) walks each matched block's declarations and adds a
  `CascadePriority` (two 64-bit words: origin, importance, tree order, layer order, block index:16, declaration
  index:16) to the `CascadeMap`: a fixed array indexed by `CSSPropertyID` for standard properties, a
  `HashMap<AtomicString, CascadePriorityList>` for custom ones (`cascade_map.h:203`). Each custom declaration
  constructs a `CustomProperty`, which looks its name up in the `PropertyRegistry` hash map (`:50`).
- **Apply.** `ApplyCascadeAffecting` (direction, writing-mode…), `ApplyHighPriority` (font, zoom, color-scheme…),
  `line-height`, then `ApplyMatchResult` (`:840`): all remaining standard properties, then **every custom property
  in the map, referenced or not** (`:876`, another registry lookup each). Custom properties are not applied first:
  they are resolved **lazily** when a `var()` needs them (`LookupAndApply` from inside substitution) and otherwise in
  that final loop.
- **Cycles.** `CascadeResolver` keeps a stack of `CycleNode`s; `IsLocked` is a linear `Find` over it
  (`cascade_resolver.h:94`: "TODO(crbug.com/985047): Probably use a HashMap"), so a long chain of first-time
  references resolved recursively costs O(chain depth) per lock. A `@function` cycle node is the function itself:
  no recursion (prior survey).
- **A custom declaration's path**, decomposed and measured in 03 §1.2–1.3: substitution tokenizes the text and looks
  each `var()` up (map, then builder trie, parent, `StyleInitialData`), a registered property is parsed against its
  syntax, computed (`ComputeRegisteredPropertyValue`), serialized with `CssText` into a new `CSSVariableData`
  (`style_builder_converter.cc:3717`) and stored twice (data and value tries). Nothing is cached between elements or
  passes.
- **Animated elements apply twice.** After the base cascade, `ApplyAnimatedStyle` (`style_resolver.cc:2760`) adds
  the interpolations and calls `cascade.Apply(filter)` again (`:2836`), which starts with `map_.ClearAppliedFlags()`
  (`style_cascade.cc:299`): every declaration is resolved again, not only the animated ones. Only the MPC (when the
  base is cacheable) or base-style reuse avoid the first application. E7, 8,000 registered `calc(var(--t) * j)`
  declarations *(measured)*:

  | Where the 8,000 declarations sit | style per pass |
  |---|---|
  | on the child of the animated element | 10.0–11.7 ms |
  | on the animated element itself (MPC-cacheable or not) | 17.4–18.6 ms |

- **Taint.** `CascadeResolver::AllowSubstitution` (`cascade_resolver.cc:20`) refuses an animation-tainted
  `CSSVariableData` in 45 "animation-affecting" properties (`animation-*`, `transition-*`, `timeline-scope`,
  `*-timeline-name`, `container-name`, `container-type`, `contain`, `writing-mode`, `direction`, `will-change`…),
  making them invalid at computed-value time. The tainted data object is inherited unchanged, so the taint follows
  it down the tree (E8b: `container-name: if(style(--on: 1): …)` on a child of the animated element never matched);
  a declared **registered** property re-serializes the value untainted (`custom_property.cc:194`, 04 finding 5;
  E8c: `--on2: var(--on)` registered, then `container-name` from `--on2` worked). *(code + measured)*

### 1.7 `ComputedStyle` and custom-property storage

`ComputedStyle` is generated from `css_properties.json5` and `computed_style_extra_fields.json5`: bit-packed hot
fields inline, the rest in copy-on-write groups (`DataRef<…>`; `field_group: "*"` lets the generator bucket by usage).
A builder clones the old or parent style by copying group pointers and copies a group only when it writes into it.
`InheritedVariables` lives in an inherited group, `NonInheritedVariables` in a non-inherited one
(`computed_style_extra_fields.json5:569`, `:739`). *(code)*

Both are a `StyleVariables`: two hash-array-mapped tries (data = substitution text, values = typed computed values),
fan-out 16, keyed by `AtomicString` pointer bits (`core/style/style_variables.h:69`, `:281`). Inheritance copies the
root pointers and marks the tree shared (`MakeShared`, `:230`, a one-time walk over an unshared tree); a `Set` on a
shared path clones the path. Each tree keeps an XOR of `hash(key, value)`; `operator==` (`style_variables.cc:11`)
compares the hashes first, then nodes with a `memcmp` fast path, and unifies equal roots. So equality is O(1) when
anything changed, O(n) only when everything is equal. Registered properties never set fall through to one
per-document `StyleInitialData` (`core/style/style_initial_data.cc:12`), built once per registry change by computing
every registered initial value. Inheritance cost is therefore independent of how many properties are inherited.
*(code)*

### 1.8 Recalc propagation

`Element::RecalcOwnStyle` (`core/dom/element.cc:5839`) computes the new style, then
`ComputedStyle::ComputeDifference` (`core/style/computed_style.cc:413`):

```cpp
bool variables_independent = !old_style.HasVariableReference() && !old_style.HasVariableDeclaration();
bool inherited_variables_equal = old_style.InheritedVariablesEqual(new_style);
if (!inherited_variables_equal && !variables_independent) return Difference::kInherited;          // :485
if (!old_style.IndependentInheritedEqual(new_style) || !inherited_variables_equal)
  return Difference::kIndependentInherited;                                                       // :490
```

`ApplyComputedStyleDiff` (`element.cc:5785`) maps `kInherited` → children `kRecalcChildren` (each child gets a
full `ResolveStyle`), `kIndependentInherited` → `kIndependentInherit`, `kDescendantAffecting` →
`kRecalcDescendants` (the whole subtree; e.g. timeline-name changes). A child under `kIndependentInherit` uses
`PropagateInheritedProperties` (`element.cc:5725`): clone its old style, copy the parent's independent inherited
fields and inherited-variables pointer, no matching, no cascade. That path is refused (`:5742`) if the child has
animations, transitions, **any `var()` reference or any custom-property declaration**, a link, text decorations,
or a color derived from the parent. Non-inherited custom-property changes give `kNonInherited` (children untouched)
unless a child uses explicit `inherit`/`inherit()` (`ChildHasExplicitInheritance` → `kInherited`). Container-query
flags ride along separately: `kRecalcStyleContainerChildren`/`…Descendants` force recalc of
`DependsOnStyleContainerQueries` elements and make the traversal visit every node below. A changed `container-name`
or `container-type` (`DiffAffectsContainerQueries`, `computed_style.cc:259`) sets all container flags. *(code)*

Firewalls *(code)*: `display: none` (descendants have no style to compute); a locked display lock,
i.e. `content-visibility: hidden` or off-screen `auto` (`DisplayLockContext::ShouldStyleChildren`, recalc of the
children is deferred and stored, `element.cc:5502`); a size container whose subtree recalc can be resumed in layout
(`SkipStyleRecalcForContainer`, `:5340`: deferred, not avoided). Not firewalls: `all: initial` (`all` never touches
custom properties), any `contain` value, `display: contents`, shadow boundaries (inheritance follows the flat tree).

E1: a 300-deep chain under an element whose animation changes inherited `--t` (and `--x: calc(var(--t) * 2)`);
`StyleResolver::ResolveStyle` trace instants per pass *(measured)*:

| Levels | ResolveStyle per pass | style per pass |
|---|---|---|
| each declares a constant non-inherited registered `--k: 1` | 301 | 1.20 ms |
| each declares `--o: var(--x)` | 301 | 1.22 ms |
| as row 1, level 1 redeclares `--x: 0` (the driver `--t` still flows) | 301.8 | 1.24 ms |
| as row 1, level 1 redeclares `--x: 0; --t: 0` | 2.0 | 0.12 ms |
| no declarations at all (cheap independent path below level 1) | 2.0 | 0.38 ms |
| as row 1, level 1 `content-visibility: hidden` | 2.0 | 0.15 ms |

So a full per-element restyle with one declaration costs ~3.6 µs here, the cheap path ~0.9 µs.

### 1.9 `if()`, `@function`, tree-counting, `:nth-child(of)`, `:has()`

- **`if()`** (`StyleCascade::ResolveIfInto`, `style_cascade.cc:2954`): for each branch, `EvalIfCondition` builds a
  `CSSIfParser` and parses the condition into a fresh expression tree (`:2893`), evaluates `style()` with
  `ResolveLikeVar` (resolves the property, builds a `CSSVariableData`) and, for an explicit value, a typed parse of
  the query value, then compares text (03 §1.5). A false branch's value is skipped with
  `SkipUntilPeekedTypeIs<kSemicolonToken>` (`:2965`): not resolved, but tokenized. Only the chosen branch is
  resolved. Nothing is cached. E9, 1,000 registered declarations each `if()` over 32 `style(--s: b)` branches
  (~1 KB of text) *(measured)*:

  | | style per pass | per declaration over no-`if()` |
  |---|---|---|
  | `calc(var(--t) * j)`, no `if()` | 2.2–2.5 ms | — |
  | first branch matches | 6.9–8.2 ms | +4.8 µs |
  | last branch matches / none | 21.8–25.5 ms | +20–23 µs |
  | same, the tested property unregistered: first / last | 6.4–8.0 / 20.5–22.5 ms | +4.7 / +18.7 µs |

  ≈ 0.57 µs per failed registered condition (0.45 unregistered) plus ~4.8 µs to tokenize and set up 1 KB of
  branches. *(measured)*
- **`@function`** (`ResolveFunctionInto`, `:1892`): main adds only an invocation counter for `random()` and
  navigation queries in bodies. Still: arguments resolved and typed per call, body flattened per call, locals applied
  per call, no memoization, no recursion, `SetHasTreeScopedReference()` (MPC off). *(code; prior survey)*
- **`inherit(--x)`** (`ResolveInheritInto`, `:1859`, `CSSInheritFunction` experimental, no milestone) reads the
  parent's value without a cycle, so `--x: calc(inherit(--x) + 1)` replaces parity copies (03 finding 10 measured it
  in 153 behind the flag). *(code)*
- **`sibling-index()`/`sibling-count()`**: `NthIndexCache` (per-parent index map during recalc for parents with
  many children, else a sibling walk); MPC off (`HasSiblingFunctions`); inside a container query it makes the
  evaluator re-evaluate on every recalc even without a style change (`DependsOnTreeCounting`, `:938`). *(code)*
- **`:nth-child(… of S)`**: `NthIndexCache` with the filter list as part of the key; on a static DOM no invalidation
  cost. *(code)*
- **`:has()`** (ENGINE_NOTES 24): a state change (`:checked`) of an element walks its ancestors and earlier siblings
  that carry `AncestorsOrAncestorSiblingsAffectedByHas`/sibling flags
  (`StyleEngine::InvalidateAncestorsOrSiblingsAffectedByHas`, `style_engine.cc:1776`); a subject `:has()` marks that element `kLocalStyleChange`, a non-subject one schedules the
  descendant invalidation sets of the rule (`:1579`), with a TODO noting no filtering by argument. Matching
  `body:has(#run:checked)` searches body's subtree (cached per recalc). `#run:checked ~ X` uses a sibling invalidation
  set: no ancestor walk, no subtree search. The sibling form is the right choice. *(code; the 10k-element cost:
  inference)*

### 1.10 Loading: parse, `RuleSet`, registration

Measured on the PLAIN css-physics pages (inline `<style>`, so eager declaration parsing), trace from navigation
*(measured)*:

| Page | CSS | `@property` | parse | active sheets (+registration) | `RuleSet` build | first Layout |
|---|---|---|---|---|---|---|
| 32 bodies | 9.4 MB | 13,655 | 99 ms | 8.4 ms | 0.6 ms | 452 ms |
| 48 bodies | 20.5 MB | 24,917 | 267 ms | 16.8 ms | 1.0 ms | 1,413 ms |

Parsing runs at 77–95 MB/s (80 MB at 96 bodies ≈ 1 s). A registration costs ~0.7 µs (syntax string parse, initial
value parse, interpolation-type list; `PropertyRegistration::MaybeCreateForDeclaredProperty`). `StyleInitialData` is
built once at the first style resolution after a registry change. The 1.4 s first Layout is outside style (handed to
05); it grows faster than the CSS.

### 1.11 One element with ~2,500 gated declarations

A css-physics round level at 48 bodies (`#L5`: 50 gated blocks, 2,548 declarations if every gate were true; per pass
in a live scene it is the active subset). Per pass, in order:

| Step | Code | Cost |
|---|---|---|
| recalc entry, `StyleResolverState`/collector setup, UA + author buckets, sort, MPC key, adjust, diff, layout-object update | `element.cc:5839`, `style_resolver.cc:1420` | ~2–3 µs per element *(measured E1: 3.6 µs incl. one declaration)* |
| 50 `RuleData` visits in `id_rules_["L5"]`, covered by bucketing; seek over the sheet's ~4,000 intervals | `element_rule_collector.cc:576`, `seeker.h:31` | ~0.07–0.1 µs per rule + ~2–4 µs of seeking *(measured / inference)* |
| per gate: flat-tree parent, `CachedContainer` (absent owner: one walk per distinct owner name) | `container_query_evaluator.cc:160` | absent: done here |
| per present-owner gate: `results_` lookup; the evaluation itself happened in **`#L4`'s** recalc (`ComputeStyleChange`), twice if anything flipped there | `:234`, `:778` | 0.6–2 µs per gate per pass, plus stale ones |
| per declaration of each matched block: expand into `CascadeMap`, resolve, substitute, parse, compute, serialize, two trie writes | `style_cascade.cc:840`, 03 §1.2 | 1.3–2.9 µs *(measured BENCHMARKS §2)* |
| `#L5`'s own evaluator: re-evaluate the ~50 queries `#L6`'s gates cached on it | `:920` | charged here, same as row 4 |

With 10% of the gates true, ~250 declarations × ~2 µs ≈ 0.5 ms against ~0.05 ms of rule and gate overhead plus the
stale re-evaluations. The declarations dominate wherever gates are true; the evaluations dominate a sparse scene.

---

## 2. What it means for the projects

### 2.1 BENCHMARKS §2, row by row

| css-physics BENCHMARKS §2 row | Root cause in the code |
|---|---|
| present name + false `style()` 0.80–1.07 µs vs absent 0.18 µs | present: one `ComputeValue` mini-cascade per query per pass, done in the container's `ComputeStyleChange` (§1.4); absent: `FindContainer` fails before the evaluator |
| absent name ≈ 0.2 µs + 0.6–0.9 ns × depth × names | the microbenchmark gave every rule its own name, so every rule walked every ancestor's name list; a repeated name walks once per element (0.07 µs per rule, E3); in 153 each walk also allocated a GC cache key |
| present name, no `style()` 0.21 µs | name-only queries return true without an evaluator |
| unnamed `style()` 0.78–0.81 µs | type `normal` matches the parent, so it is the present-name case |
| `style(--g)` 0.50 µs | the mini-cascade applies `initial` instead of parsing and computing a literal |
| range 1.68–2.28 µs | cloned container style + new `CSSParserContext` + 2–3 numeric parses per evaluation |
| `or` of 9: 0.82 µs per disjunct | each leaf is a separate `ComputeValue`; only the whole query is cached |
| nested: inner first; `and`: left to right | `EvaluateAndAddContainerQueries` starts at the innermost set; `ConditionalExpNodeAnd/Or` short-circuit |
| "absent-name rejection is not linear in the rule count" (0.49 µs at 10k, 0.17 at 50k) | not explained by the code; a cache-size or warm-up effect (open question) |
| 2,000 inherited props over 50 levels = non-inherited | inheritance is a root-pointer copy, inequality an O(1) XOR-hash test (§1.7); every level restyled anyway because each declares a `var()` |
| an empty level ~3–11 µs | a full `ResolveStyle`: E1 measured 3.6 µs for a level with one declaration, 0.9 µs for one with none |

### 2.2 css-physics

- **Stale gates (finding 2) likely inflate the sparse regime after activity.** Each level's evaluator keeps every
  pair/body/plane query its child's rules ever evaluated, and re-evaluates all of them on each pass that changes the
  level's custom properties (every pass while anything is awake) until one cached result on that level flips. After a
  tower settles and one body is dragged, levels whose gates don't flip pay ~0.6–2 µs per historical gate per pass:
  up to ~3,400 (48) or ~6,000 (64) gates. A scene that loaded asleep (`SCENE=field`) never filled those caches, so
  its numbers (BENCHMARKS §1 "sparse regime") understate a settled pile's drag. Fix in CSS: one rule per level whose
  result flips whenever the awake set changes, e.g. `--anp: mod(var(--nawake), 2)` at L0 and
  `@container style(--anp: 1) { #Lk { --zz: 0 } }` per level: any flip clears the level's whole style cache
  (`ClearResults`), at a cost of one extra gate per level. *(code + measured mechanism; the size in the engine:
  inference)*
- **Owner-name gating is already the right shape**, and E2/E10 say why it can't get much cheaper: an absent owner
  costs 0.07 µs per rule plus one walk per owner; a present owner pays one evaluation per block per pass because
  the container (the parent level) changes every pass. Sharing an evaluation needs rules with the same condition in
  the same block and the same container, and 374 of 475 queries at 16 bodies are used at a single level. Hoisting the
  flags to a container that changes rarely doesn't work: every ancestor of a level carries the per-pass state, and
  any change of the container's custom properties (inherited or not) re-evaluates its cache. *(code + inference)*
- **Rejection shapes, from the matching order** *(code + measured)*: rule order changes nothing but the `Seeker`
  walk; more declarations per gated rule cost a rejected rule ~0.5 ns each (the `AffectsAnimations` scan) and
  nothing else; nesting evaluates the innermost `@container` first and gives every block its own query objects,
  so an outer shared block is consulted only after the inner one passes and is never shared across different inner
  blocks; a name in the query is checked before any evaluation, so `@container b5 style(…)` is already the cheapest
  form of "owner, then flag"; a different selector bucket is free. The generator's current shape is the cheapest
  Blink offers for this workload.
- **`BOOLQ=1` saves the literal's parse and compute** (0.3 µs per present-owner gate per pass: ~1 ms at 48 bodies
  all awake), which is why BENCHMARKS saw a per-rule gain but noise in the engine. Firefox's boolean bug keeps it off.
  *(code)*
- **Move `#LS`'s 830 declarations (and `#LT`'s 158) to a plain child.** They are applied twice per pass because
  `#LS` animates (E7: ~0.85 µs extra per declaration), ~0.7 ms per pass at 48 bodies. The child inherits the animated
  registers; the taint is laundered the same way as now (registered declarations). *(measured mechanism; saving:
  inference)*
- **OWNLEV=1 was slower** (HISTORY) because unnamed gates on round levels are present-name gates: one evaluation per
  gate per pass instead of a 0.07 µs absent-name rejection. **Unnamed gates in 141 (2.5–3.5 µs)** are the same
  mechanism; why 141 was 3–4× dearer than 153 wasn't investigated. *(code)*
- **The owner names depend on taint laundering.** `#LS` animates the registers; every level inherits tainted data;
  `--ac{i}` (registered, declared) launders it; `--A{i}` and `--AN` (unregistered) carry the clean result into
  `container-name`. If Blink makes taint survive registered properties (the spec's "infectious" rule), `--AN` becomes
  invalid in `container-name` and every owner-named rule stops matching. Add an `engine/` probe for it. *(code +
  measured, E8b/E8c)*
- **`@function` and `if()` in hot properties stay dead** (HISTORY): `@function` disables the MPC and is uncached;
  `if()` is ~0.5 µs per condition tried plus its text (E9), which also explains the 141 measurement (4.2 µs).
- **MPC:** levels never hit (unique blocks, parent state in the key). On 153 they aren't even stored (container-name);
  on 155+ each level adds a dead entry per pass (a style clone and a copy of up to ~900 matched-block entries for L1).
  *(code; cost: inference)*
- **Registers and the render tree** use timeline and animation names: never MPC-cached, irrelevant since each is
  unique. *(code)*
- **Load:** parse ≈ 10–13 ms per MB; registration ≈ 0.7 µs per `@property`; lazy parsing would only move the parse
  into the first recalc (every `#Lk` rule is visited, and a rejected gate parses its block). The 1.4 s first layout at
  48 bodies is the bigger load-time item (05). *(measured + code)*

### 2.3 js-minus-js

- **ENGINE_NOTES 5 and 41, explained.** A changed inherited custom property makes every child with any custom
  declaration or `var()` reference do a full restyle (§1.8), and the child's own inherited set then differs, so it
  continues. Redeclaring one property stops nothing while another changing inherited property still reaches the
  element (E1 row 3); redeclaring **all** of them makes the set equal and stops it one level down (row 4). The
  ~2.4 µs per element measured for the 38,000-element case matches E1's 3.6 µs per level. Corrected wording for
  note 41: "restyles every element below that declares or references a custom property, until an element whose whole
  inherited custom-property set is unchanged". *(code + measured)*
- **Pass-through elements should declare nothing.** A `display: contents` wrapper or decode node with no custom
  declarations and no `var()` costs ~0.9 µs under a changing parent instead of a full restyle. `.d{x} { --dg: x }`
  makes every RAM decode node a full restyle; where a node needs `--dg` only to compute, that's unavoidable, but any
  wrapper that merely carries the constant could drop it (put `--dg` on the node that uses it). *(code + measured)*
- **`content-visibility: hidden` stops style propagation** (E1 row 6), not just layout. Anything under the page's
  per-pass inherited state that need not be current while running (editor, idle parts of the console) could sit
  under a cv:hidden ancestor during Run. *(measured mechanism; application: inference)*
- **The parser dispatch** (`@container style(--vh: m) and (style(--tcq: …) or …)` on `.tpA, .tpB`, ~188 rules per
  token level): every rule is a separate query object, so each token level's container re-evaluates ~188 queries on
  each pass that changes it (`--vh` false: one `ComputeValue` each; true: plus the `or` list up to the match), ~0.8 µs
  each: ~150 µs per level per pass, plus 0.1 µs per rule visit. Identical-condition merging (done) is the only
  sharing Blink offers. ENGINE_NOTES 7's "put the most selective test first" holds (`and` short-circuits); both tests
  are equality tests, so there is nothing cheaper to put first. Name-based dispatch would be cheaper per present name
  but an absent name walks the whole chain (~2,000 ancestors), as COMPARISON.md says. *(code)*
- **Muxes:** an `if()` mux costs its full text plus ~0.5 µs per condition tried, every evaluation (E9). A 64-way
  linear mux averages ~32 conditions; a nested binary `if()` tests 6 but still tokenizes all 64 leaves. PRIMITIVES'
  grid-placement ports (15 µs) avoid both. *(measured + code)*
- **ENGINE_NOTES 6** is the MPC: siblings with content-equal matched blocks and the same parent share a cloned style.
  It breaks for any sibling with a tree-scoped name (E5: 40–80× slower), so `anchor-name`, animations and timeline
  names on replicated hardware defeat it; in 153 `container-name` does too. RAM leaves carry a unique inline style
  and an `anchor-name`, so they never share; off-path decode nodes with identical matched rules and equal parent
  variables can. *(code + measured)*
- **ENGINE_NOTES 24:** use sibling selectors (as done); `:has()` adds an ancestor walk on every relevant state change
  and a subtree search per evaluation. *(code)*
- **Animated elements:** line sources and `#mem` should carry only their animations and the few properties derived
  from them; heavy derived declarations belong on a child (E7). Check `#cpu` (~900 custom properties) for an
  animation on the same element. *(measured mechanism; whether `#cpu` animates: unchecked)*

### 2.4 paint

Little style work. One fact: `anchor-name` on probe-row elements makes them MPC-uncacheable (§1.5); the row reader's
size container restyles inside layout (05). *(code)*

---

## 3. What's changing (153 → 155 → 157 → main)

Diffed `core/css/{resolver,container_query*,rule_set*,element_rule_collector*,selector_checker*,style_engine*,
media_query_evaluator*}`, `core/style` and `core/dom/element.cc` between `$SP/src/chromium-153`, gitiles trees of
8059 and 8103, and main. *(code)*

| Change | First in | Effect here |
|---|---|---|
| `container-name` stored as `Vector<AtomicString>`, not a tree-scoped `ScopedCSSNameList` | 155 | elements with `container-name` become MPC-cacheable; `ContainerSelectorCache` no longer allocates a GC key per insert; name scans compare atoms instead of dereferencing pointers. Absent-name rejections and identical named siblings get cheaper; levels start adding dead MPC entries |
| MPC parent pointer-equality fast path before `InheritedEqualIncludingInheritedVariables` | 155 | cheaper hits for siblings (ENGINE_NOTES 6) |
| `CanStartTransitions`: elements whose transitions all have zero duration+delay skip `ApplyAnimatedStyle` | 157 | `transition: none`/`0s 0s` elements stop paying the animation path; latches with a delay unaffected |
| `random()` stable (`CSSRandomFunction`) | 156/157 (03) | element-dependent `random()` disables the MPC |
| `LazyParseInlineStyleSheets` (no status) | 157 | defers inline declaration parsing; little gain for these pages (§2.2) |
| `CompositeHoverStyle` (no status): precomputes `:hover` styles for color/text-decoration only | main | none |
| comma-separated `@container` lists, `@function` with `@container`/navigation in bodies, mixins as `RuleSet` expansion | 153 already / main refinements | no perf change |
| `CSSMixins` experimental; `CSSInheritFunction` experimental; `CSSIdentFunction` test; `CSSCustomMedia` test | unchanged 153 → main | `inherit()` would remove parity copies (§1.9) |
| `CanReuseBaseComputedStyle`, `ComputeValue`, `EvalStyleFeature`, `FindContainer`, the `Seeker`, `HashTrieNode`, `ComputeDifference` (except display-contents canvas and timeline-name checks) | unchanged | every cost in §1 holds on main |

Open TODOs on the hot paths: `crbug.com/1213888` (cache `FindContainer` results), `crbug.com/985047` (cycle stack as
a hash map), `TODO(sesse)` in `ResolveVariableReference` ("we tokenize everything involving variable references
twice"), `TODO(andruud)` in `ConvertRegisteredPropertyVariableData` ("Produce tokens directly from CSSValue"), and
mixin CQ-dependent locals marking the MPC uncacheable. None has a CL visible in the tree.

---

## 4. Ideas, ranked by expected value × confidence

1. **Flush stale gate caches when the awake set changes** (css-physics). One flip-on-change rule per level (§2.2).
   Value: up to ~0.6–2 µs × (historical gates) per pass in post-activity sparse scenes. *(code + measured
   mechanism)* Cheapest test: `sparse.js` on a tower page after it settles vs the field scene with the same awake
   count; then the same tower with the flush rule.
2. **Keep heavy declarations off animated elements** (both). Move `#LS`/`#LT` derived properties to a plain child;
   check js-minus-js sources, `#mem`, `#cpu`. ~0.85 µs per moved declaration per pass. *(measured mechanism)* Test:
   `ab.js` frozen 48 pile with and without the move.
3. **Group by condition, never split** (generators). Rules with the same condition for the same container must share
   one `@container` block (17× per extra rule, E2). Both projects already do; make it a generator assertion
   (`ccpage5.py`, `gen3d.py`). *(measured)*
4. **Probe the taint dependency** (`engine/`): a registered property laundering an animated value into
   `container-name`; and E1's propagation rules (counts of `ResolveStyle` per pass), so a Chrome change shows up in
   `make engine-check`. *(code + measured)*
5. **Strip custom declarations from pass-through elements** (js-minus-js decode/wrapper levels): ~2.7 µs saved per
   element per pass that is restyled by inheritance. *(measured mechanism)* Test: count `ResolveStyle` per pass with
   the invalidation trace before/after.
6. **`content-visibility: hidden` as a style firewall** for subtrees that inherit per-pass state but needn't be
   current during Run (js-minus-js editor). *(measured mechanism; speculation on where it applies)*
7. **`inherit()` when it ships** (both): `--K: calc(inherit(--K) + x)` instead of K/J aliases and A/B parity
   copies: one declaration and one name less per update. No milestone (09). *(code)*
8. **Boolean gates in Chrome only** (css-physics): `style(--flag)` inside `@supports not (-moz-appearance: none)` and
   `style(--flag: 1)` for Firefox: ~1 ms per pass at 48 all-awake for twice the gate CSS. Low value. *(code)*
9. **Upstream asks** (for the user to file, highest value first): cache the computed query value in
   `EvalStyleFeature` when it has no `var()` or relative units (makes every `style()` gate ~0.1 µs); drop
   `results_` entries not used since the last recalc; cache `FindContainer` per selector across siblings
   (crbug.com/1213888); skip the full re-apply in `ApplyAnimatedStyle` for declarations that don't depend on animated
   properties; binary-search the `Seeker`. *(code; speculation on acceptance)*
10. **Dead ends, with the reason** *(code)*: a "stable flag container" (any ancestor of a level carries per-pass
    state, and any custom-property change of a container re-evaluates its cache); name-only dispatch in deep chains
    (absent names walk to the root); mixins (expansion, no per-element saving, can't parameterize names); lazy
    parsing for these pages (every rule is visited); one-big-element vs many-small (per-element overhead is only
    ~2–3 µs; choose by invalidation, not size).
11. **Custom state without script** *(code + docs)*: `:state()` needs `ElementInternals` (script). What CSS alone
    can hold is a computed value (transition latch, 04) or a user-driven DOM state (`:checked`, `:target`,
    `:open`/`:popover-open` through declarative `commandfor`/`popovertarget` buttons, scroll-state). Only the DOM
    states give selector-level, bucketed (free) rejection, and they change only on input. As a dispatch mechanism
    for computed state, nothing beats a name-only `@container` (0.07–0.2 µs, no evaluation) or a `style()` gate.

---

## 5. Possible bugs

- **Animation taint is dropped by registered custom properties** (`core/css/properties/longhands/custom_property.cc:194`:
  `is_animation_tainted = value_mode & kAnimated`, ignoring the declaration's tainted data, while `is_attr_tainted`
  on the next lines does propagate). css-variables-2: "Animation-tainted is 'infectious': custom properties which
  reference animation-tainted properties also become animation-tainted." Found independently by 04 (finding 5);
  measured here for `container-name` (E8b/E8c). css-physics relies on the deviation. Separately, Blink's refusal list
  is "animation-affecting" properties (45), while the spec says "a property that is not animatable": a wider set.
  *(code + measured)*
- **Stale container-query results are re-evaluated forever** (`ContainerQueryEvaluator::ComputeStyleChange`,
  `container_query_evaluator.cc:778`, entries only removed by `ClearResults` on a flip). A performance bug, not a
  correctness one: cost proportional to every query ever evaluated against the container. Measured 10–20× on E8.
  *(code + measured)*
- **`EvalStyleFeature` allocates a `CSSParserContext` and clones the container style per range evaluation**
  (`media_query_evaluator.cc:1805–1807`): avoidable per-evaluation garbage. Performance only. *(code)*

## Open questions

- Why absent-name rejection in BENCHMARKS §2 got cheaper per rule from 10k to 50k rules (0.49 → 0.17 µs).
- How large the stale-gate cost is in the real engine after a settled pile (idea 1's test).
- Whether 155+'s MPC adds for levels (dead entries, GC pressure) are measurable at 64–96 bodies.
- What the 1.4 s first Layout at 48 bodies is (05).
- ENGINE_NOTES 4 is not in the style engine: no per-element loop over registrations exists in matching or the
  cascade (only `StyleInitialData`, once). 04 found it in the keyframe snapshot loop. The registry is consulted 2+
  times per custom declaration (hash lookups in a 25k–300k table), a per-declaration cost that may grow with registry
  size: unmeasured.

---

## Appendix: experiments

Scripts in `exp/02/scripts/` (`gen.py` writes the pages, `run.js` measures, `load.js` traces a load), pages in
`exp/02/exp/` and `exp/02/load/`; `$SP/src` = the source checkouts (README, Reproducing).
`run.js dir pages rounds`: one page per fresh tab in one browser, 0.7 s (or `WAIT`) settle, 1.2 s trace, median
`UpdateLayoutTree`; `INV=1` adds the invalidation-tracking category and counts `StyleResolver::ResolveStyle`
instants per `UpdateLayoutTree`. Chromium 153.0.8010.12 (`/usr/local/bin/chromium --no-sandbox`), Playwright from
`/workspaces/css-energy/css-physics/node_modules`. Load pages: `COUNTS=32|48 PLAIN=1 python3 css-physics/src/build3d.py`.

```
python3 -I scripts/gen.py exp
INV=1 node scripts/run.js exp e1a_decl.html,e1b_redecl.html,e1c_empty.html,e1d_cvhidden.html,e1e_redecl_x_only.html,e1f_ref.html 1
node scripts/run.js exp e2_base.html,e2_sep.html,e2_shared.html,e3_1.html,e3_60.html 3
node scripts/run.js exp e10_base.html,e10_stablecont.html,e2_sep.html 2
node scripts/run.js exp e5a_plain.html,e5b_anchorname.html,e5c_containername.html,e5d_cq.html 3
node scripts/run.js exp e7a_parent_anim.html,e7f_parent_anim_uncacheable.html,e7b_self_anim.html,e7e_self_anim_uncacheable.html,e7d_self_anim_child.html 3   # N7 = 8000
WAIT=1200 node scripts/run.js exp e8c_stale.html,e8d_stale_flip.html,e8c_never.html 2      # plus e8b_*, e8c_ifon
node scripts/run.js exp e9_noif.html,e9_first.html,e9_last.html,e9_none.html,e9_first_unreg.html,e9_last_unreg.html 3
node scripts/load.js load/p48.html 3000
```

| Id | Question | Result |
|---|---|---|
| E1 | which levels restyle under a changing inherited property | table §1.8 |
| E2, E10 | is a `style()` gate evaluated per rule or per block, and when | table §1.4 |
| E3 | rejected-rule cost, absent repeated name, 1 vs 60 declarations | 0.07 / 0.10 µs per rule |
| E5 | MPC sharing and what breaks it | table §1.5 |
| E7 | declarations on an animated element | table §1.6 |
| E8 | stale evaluator entries; taint through inheritance; laundering | table §1.4; §1.6 |
| E9 | `if()` cost per branch | table §1.9 |
| load | parse, `RuleSet`, registration, first layout | table §1.10 |
