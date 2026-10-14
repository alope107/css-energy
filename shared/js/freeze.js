// freeze.js — bake a running page's state into a static copy, to profile one step without the state moving (harness only).
//
// A frozen copy declares each state property as a constant, but with a tiny wobble driven by a clock, so every property
// that depends on it is recomputed every frame (the work being measured) while its value, and every gate tested on it,
// stays put. Profile frozen variants against each other only: the wobble itself costs time (css-physics
// docs/BENCHMARKS.md: a frozen page's base is 2–3× the live base).
//   CLOCK_CSS            the @property and @keyframes of the clock --now2 (insert it into the page's stylesheet)
//   CLOCK_ANIMATION      the declaration that runs it, on an element that is an ancestor of every reader
//   wobble(name, v)      --name: v plus 1e-7 × sin(clock), as one declaration
//   constant(name, v)    --name: v, as one declaration (for values that gate rules and must not move at all)
// css-physics: tools/freeze3.js and tools/freezegrab.js (tools/lib/physics.js bakeRegisters).
const CLOCK_CSS = "@property --now2{syntax:'<number>';inherits:false;initial-value:0}@keyframes clk2{from{--now2:0}to{--now2:100}}";
const CLOCK_ANIMATION = 'animation:clk2 100s linear infinite';
const wobble = (name, v) => `--${name}:calc(${v} + 0.0000001 * sin(var(--now2) * 50));`;
const constant = (name, v) => `--${name}:${v};`;
module.exports = { CLOCK_CSS, CLOCK_ANIMATION, wobble, constant };
