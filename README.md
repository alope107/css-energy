# css-energy

Three experiments in computing inside Chrome's rendering pipeline, with no script on the page.

| Project | What it is |
|---|---|
| [css-physics/](css-physics/) | rigid3d.css: a 3D rigid-body physics engine run by the style engine (custom properties gated by `@container` queries) |
| [js-minus-js/](js-minus-js/) | JavaScript compiled by a stylesheet and executed by a GSUB "CPU" font while Chrome shapes text |
| [paint/](paint/) | Dictionary Paint: a 16-colour canvas whose pixels persist across reloads and restarts in Chrome's compression-dictionary store, written and read by CSS-initiated loads |

[COMPARISON.md](COMPARISON.md) compares their techniques and lists what each could borrow from the others.

[shared/](shared/) holds the test and profiling harness code the projects use (browser profiles, tracing, A/B timing,
motion checks, freezing, ablation). [engine/](engine/) re-checks the Chrome behaviour css-physics and js-minus-js
depend on (`make engine-check`, `make engine-costs`).
