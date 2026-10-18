# Browser bugs

Browser behaviour found while building the projects that looks like a bug. The user reviews the MREs and files the
reports; rules for adding entries are in the root `CLAUDE.md` ("Browser bugs").

An MRE is one self-contained HTML file: no dependencies, pass/fail visible without script (red means the bug), and a
closing comment with the observed results, the spec text and the likely cause. Serve the repo root
(`python3 -m http.server 8765 --bind 127.0.0.1`) and open `bugs/<file>`.

## Reported

| Bug | Browser | Report | MRE |
|---|---|---|---|
| A subtracted `hypot()` is added: `calc(100px - hypot(30px, 40px))` is 150px, also inside a subtracted `min()`/`max()`/`clamp()`/`sign()`/sum and through `var()`. Likely `CalcNode::negate()` negating hypot's arguments. | Firefox 157–160 | [2083404](https://bugzilla.mozilla.org/show_bug.cgi?id=2083404) | [firefox-hypot-negation.html](firefox-hypot-negation.html) |
| `@container style(--v: N)` never matches a calc()-computed registered `<integer>` ≥ 256 (probe `style-int-256`). Blink computes calc() integers as `kNumber`; the value pool caches 0–255 as integers, which hides it below 256. | Chrome 153 | [571450199](https://issues.chromium.org/issues/571450199) (accepted, P2; fix [CL 8559024](https://chromium-review.googlesource.com/c/chromium/src/+/8559024) in review) | — |
| Registered numbers keep 6 significant digits through `var()` (`1048575` → `1.04858e+06`); a copied `<integer>` ≥ 10⁶ is then invalid (probe `var-6-digits`). Against cssom-1. **If the CL above lands, re-check css-physics' digests** (6 bodies per word assume the rounding). | Chrome 153 | [40266999](https://issues.chromium.org/issues/40266999) (open since 2023), dup [563689644](https://issues.chromium.org/issues/563689644) | — |

## Unreported: MREs

| Bug | Browser | Spec | MRE |
|---|---|---|---|
| `@container style()` rules aren't re-matched when the container's value changes through a CSS animation (also inherited from, or computed from, an animated ancestor); a class or inline-style change re-matches. Related, fixed: 2014403. No WPT test animates a style query. | Firefox 157–160 | css-conditional-5: evaluates against the computed value | [firefox-style-query-animation.html](firefox-style-query-animation.html) |
| `@container style(--x)` (no value) is true for a registered property at its initial value. Likely `StyleFeaturePlain::matches` testing only that a value exists. WPT `custom-property-style-queries.html` has the elements but no assertion. | Firefox 157–160 | css-conditional-5 §6.2: true "if the computed value is different from the initial value" | [firefox-style-boolean-registered.html](firefox-style-boolean-registered.html) |

## Probably known

| Bug | Browser | Reports | MRE |
|---|---|---|---|
| preserve-3d bodies composite in document order: a cube resting on another draws behind it (headless, software WebRender) | Firefox 157 | meta [1709716](https://bugzilla.mozilla.org/show_bug.cgi?id=1709716), [1025439](https://bugzilla.mozilla.org/show_bug.cgi?id=1025439), [766346](https://bugzilla.mozilla.org/show_bug.cgi?id=766346); no exact match | [firefox-preserve3d-order.html](firefox-preserve3d-order.html) |
| HTTP/2: when a server sends `GOAWAY` (`NO_ERROR`) while requests are queued on `SETTINGS_MAX_CONCURRENT_STREAMS`, a few hundred fail with `ERR_FAILED`, never sent or retried (RFC 9113 §6.8 says they can be). Cause, not in the reports: `SpdySession::ProcessPendingStreamRequests()` posts `CompleteStreamRequest`; a `GOAWAY` read before those tasks run makes `StartGoingAway()` refuse only the still-queued ones, and the posted ones get `ERR_FAILED` from `TryCreateStream()` in `STATE_GOING_AWAY`, which `HandleIOError()` doesn't retry. Seen on Cloudflare (`GOAWAY` after 10,000 streams) by paint. | Chrome 153 | [355006326](https://issues.chromium.org/issues/355006326) (open, P3, same net-log signature), [40814635](https://issues.chromium.org/issues/40814635); the code path would be new information | needs a server: `paint/serve.js --goaway N` |
| Scroll-driven animations update stale timelines only at the next frame (the spec asks for another style and layout pass in the same frame) | Firefox | [2048416](https://bugzilla.mozilla.org/show_bug.cgi?id=2048416) (patch waiting on [csswg-drafts#12120](https://github.com/w3c/csswg-drafts/issues/12120)) | — |

## Unconfirmed or not bugs

- **Style-container rules re-matched only for direct children** (css-physics, Chromium 141): not reproduced in 153; no
  report; Blink's code handles descendants. css-physics keeps names on every level anyway.
- **Transitions on `.bd` restart from the base value, not the running one** (css-physics HISTORY): against
  css-transitions-1; possibly [441221575](https://issues.chromium.org/issues/441221575). A minimal page didn't
  reproduce it; needs one before an MRE.
- **`.ts` timeline-scope wrappers inside `.rz` make the scene vanish** (css-physics): never reduced.
- **Fontations avar2 cost ~axes³** (Chrome 148, from another chat): no report found, unmeasured here.
- **`media` on `<link rel=compression-dictionary>` is ignored** (paint): spec gap; the keyword isn't in HTML yet
  ([whatwg/html#11620](https://github.com/whatwg/html/pull/11620)).
- **~7,700 in-flight requests fail without retry** (paint): `kMaxOutstandingRequestsPerProcess = 2700`, then
  `ERR_INSUFFICIENT_RESOURCES`. A limit, not a bug.
- **Stale view timelines re-run style and layout in the same frame** (Chrome): specified (scroll-animations-1 §5.1).
- **Contenteditable Enter nesting, select-all + delete emptying the host, copy inlining author styles** (js-minus-js
  editor): long-standing editing behaviour, not researched.
- Missing features, not bugs: Firefox `if()` ([1981485](https://bugzilla.mozilla.org/show_bug.cgi?id=1981485)); typed
  arithmetic before Firefox 158; scroll-driven animations default-on only from Firefox 159.
