# css-energy

Two experiments in computing inside Chrome's rendering pipeline, with no script on the page.

| Project | What it is |
|---|---|
| [css-physics/](css-physics/) | rigid3d.css: a 3D rigid-body physics engine run by the style engine (custom properties gated by `@container` queries) |
| [js-minus-js/](js-minus-js/) | JavaScript compiled by a stylesheet and executed by a GSUB "CPU" font while Chrome shapes text |

[COMPARISON.md](COMPARISON.md) compares their techniques and lists what each could borrow from the other.

[shared/](shared/) holds the test and profiling harness code both use (browser profiles, tracing, A/B timing, motion
checks, freezing, ablation). [engine/](engine/) re-checks the Chrome behaviour both depend on (`make engine-check`,
`make engine-costs`).
