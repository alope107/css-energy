# Browser bugs

Browser behaviour found while building the projects that looks like a bug: what it is, whether it is already
reported, and a minimal reproduction (MRE) for the ones that aren't. Nothing here has been filed; the user reviews the
MREs and files reports. The rules for adding to this list are in the root `CLAUDE.md` ("Browser bugs").

Each MRE is one self-contained HTML file: no dependencies, pass/fail visible without script (red means the bug), an
optional script readout, and a closing comment with the observed results, the spec text and the likely cause.
Serve the repo root (`python3 -m http.server 8765 --bind 127.0.0.1`) and open `bugs/<file>`.

## Now reported:
[calc and hypot issue](https://bugzilla.mozilla.org/show_bug.cgi?id=2083404)

## Previously Unreported: MREs

| Bug | Browser | Spec | MRE |
|---|---|---|---|
| A subtracted `hypot()` is added: `calc(100px - hypot(30px, 40px))` is 150px. Also inside a subtracted `min()`/`max()`/`clamp()`/`sign()`/sum and through `var()`. Likely `CalcNode::negate()` negating hypot's arguments (`servo/components/style/values/generics/calc.rs`). No WPT test subtracts `hypot()`. | Firefox 157, 158, 160 | css-values-4 math functions | [firefox-hypot-negation.html](firefox-hypot-negation.html) |
| `@container style()` rules aren't re-matched when the container's value changes through a CSS animation (also when inherited from, or computed from, an animated ancestor); a class or inline-style change re-matches. Related, fixed: bug 2014403 (style() invalidation meta). No WPT test animates a style query. | Firefox 157, 158, 160 | css-conditional-5 evaluates against the computed value | [firefox-style-query-animation.html](firefox-style-query-animation.html) |
| `@container style(--x)` (no value) is true for a registered property at its initial value. Likely `StyleFeaturePlain::matches` (`servo/components/style/queries/condition.rs`) testing only that a value exists. WPT `custom-property-style-queries.html` has the elements but no assertion. | Firefox 157, 158, 160 | css-conditional-5 §6.2: "evaluates to true if the computed value is different from the initial value" | [firefox-style-boolean-registered.html](firefox-style-boolean-registered.html) |

## Probably known

| Bug | Browser | Reports | MRE |
|---|---|---|---|
| preserve-3d bodies composite in document order: a cube resting on another draws behind it (seen headless, software WebRender) | Firefox 157 (headless) | meta [1709716](https://bugzilla.mozilla.org/show_bug.cgi?id=1709716), [1025439](https://bugzilla.mozilla.org/show_bug.cgi?id=1025439), [766346](https://bugzilla.mozilla.org/show_bug.cgi?id=766346); no exact match | [firefox-preserve3d-order.html](firefox-preserve3d-order.html) |
| HTTP/2: when a server sends `GOAWAY` (`NO_ERROR`) while requests are queued on `SETTINGS_MAX_CONCURRENT_STREAMS`, a few hundred of them fail with `ERR_FAILED`, never sent and never retried (RFC 9113 §6.8 says they can be). The rest are refused and retried. Cause, not named in the reports: `SpdySession::ProcessPendingStreamRequests()` dequeues requests and posts `CompleteStreamRequest`; a `GOAWAY` read before those tasks run makes `StartGoingAway()` refuse only the ones still queued, and the posted ones get `ERR_FAILED` from `TryCreateStream()` in `STATE_GOING_AWAY`, which `HandleIOError()` doesn't retry. Seen on Cloudflare (`GOAWAY` after 10,000 streams) by paint; reproduced with `paint/serve.js --goaway` (paint/docs/HISTORY.md §6). | Chrome 153 | [355006326](https://issues.chromium.org/issues/355006326) (open, P3; same net-log signature, last reproduced on 149), [40814635](https://issues.chromium.org/issues/40814635) (nginx `keepalive_requests`); the code path above would be new information there | — (needs a server; `paint/serve.js --goaway N`) |
| Scroll-driven animations update stale timelines only at the next frame (the spec asks for an extra style and layout pass in the same frame) | Firefox | [2048416](https://bugzilla.mozilla.org/show_bug.cgi?id=2048416) (patch waiting on [csswg-drafts#12120](https://github.com/w3c/csswg-drafts/issues/12120)) | — |

## Not bugs (missing features, now or soon shipped)

- Firefox `if()`: not implemented ([1981485](https://bugzilla.mozilla.org/show_bug.cgi?id=1981485)).
- Firefox typed arithmetic (`calc(10px / 5px)`): shipped in 158 ([2067411](https://bugzilla.mozilla.org/show_bug.cgi?id=2067411)); 157 and older reject it.
- Firefox scroll-driven animations: on by default from 159 ([1324602](https://bugzilla.mozilla.org/show_bug.cgi?id=1324602)), a pref in 158.

## Candidates from earlier notes

The notes in each project (css-physics docs, js-minus-js `docs/ENGINE_NOTES.md`, paint docs, `engine/README.md`)
record many engine behaviours as design facts. These are the ones that look like bugs, checked on 2026-10-17
(trackers searched; no browser runs beyond what is said):

| Behaviour (where recorded) | Browser | Verdict |
|---|---|---|
| `@container style(--v: N)` never matches a calc()-computed registered `<integer>` ≥ 256 (probe `style-int-256`) | Chrome 153 | Bug, reported: [crbug 571450199](https://issues.chromium.org/issues/571450199) (accepted, P2); fix [CL 8559024](https://chromium-review.googlesource.com/c/chromium/src/+/8559024) in review. Blink computes calc() integers as `kNumber` and compares types; the value pool caches 0–255 as integers, which hides it below 256. |
| Registered numbers keep 6 significant digits through `var()` (`1048575` → `1.04858e+06`); a copied `<integer>` ≥ 10⁶ is then invalid (probe `var-6-digits`; css-physics' digests rely on it) | Chrome 153 | Bug against cssom-1 (no scientific notation; integers in full), reported: [crbug 40266999](https://issues.chromium.org/issues/40266999) (open since 2023), duplicate [563689644](https://issues.chromium.org/issues/563689644). The CL above would fix the `<integer>` case. **If it lands, re-check css-physics' digests** (6 bodies per decimal word assume the rounding). |
| Style-container rules re-matched only for the container's direct children; deeper named rules went stale (css-physics HISTORY, "Container names on L0/L1 only") | Chrome | Unconfirmed: no report found, and Blink's code handles descendants. The case then had `container-name` computed with `if()` from animation-driven flags. Not reproduced in Chromium 153: a rule four levels below a named container followed it on every frame, with an animated gate and with a name read through `var()` of an `if()` (the note dates from Chromium 141). css-physics keeps names on every level anyway. |
| CSS transitions on `.bd` restarted from the base (spawn) value instead of the running one (css-physics HISTORY; a minimal page didn't reproduce it) | Chrome 153 | Against css-transitions-1 (before-change style includes animations). Related, unconfirmed: [crbug 441221575](https://issues.chromium.org/issues/441221575) "Base style incorrectly accounts for declarative animations". Needs a minimal repro before an MRE. |
| `.ts` timeline-scope wrappers inside `.rz` make the scene vanish (css-physics CLAUDE.md) | Chrome | Unexplained, never reduced. |
| Fontations avar2 cost grows about as axes³ (js-minus-js ENGINE_NOTES, from another chat) | Chrome 148 | No report found; unmeasured here. |
| `media` on `<link rel=compression-dictionary>` is ignored (paint) | Chrome | Spec gap: the keyword isn't in HTML yet ([whatwg/html#11620](https://github.com/whatwg/html/pull/11620), which doesn't check `media`), though HTML's generic rule makes `media` prescriptive for external resources. |
| About 7,700 in-flight requests fail without retry (paint) | Chrome | Known limit: `kMaxOutstandingRequestsPerProcess = 2700` per renderer process, then `ERR_INSUFFICIENT_RESOURCES`. Not a bug. |
| Stale view timelines re-run style and layout once more in the same frame (both projects get 2 steps per frame from it) | Chrome | Specified (scroll-animations-1 §5.1); Firefox is the one that differs (above). |
| Contenteditable: Enter nests later lines, select-all + delete empties the host, copy inlines author styles (js-minus-js editor) | Chrome | Long-standing editing behaviour; not researched. |
