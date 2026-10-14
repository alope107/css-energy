// ab.js — A/B comparison by interleaved repeats of an existing measurement command (harness only; no browser of its own).
//
//   node ../shared/js/ab.js [-r rounds=5] [-p name] 'command with {}' a.html b.html [c.html …]
//
// Each round runs the command once per variant, every run in a fresh process, with `{}` replaced by the variant (a page
// path, or any other word: a flag value, an environment setting). The order rotates every round (round r starts at
// variant r) and the rounds are rounded up to a multiple of the variant count, so every variant runs in every position
// equally often and drift in machine load hits every variant alike. From each run's output it takes one number, `-p name`:
//   - the field `name` of the first JSON object line that has it (js-minus-js harnesses print JSON lines), else
//   - the first number after the word `name` ("bigmed 6.98", "haltMs: 8512", "fps=60").
// Prints, per variant: the median, min and max of the values, and the median and interquartile range of the per-round
// ratio to the first variant. The ratios are what to read: a run-to-run swing on a busy machine cancels out of a ratio
// from the same round. Give the same page twice to see the noise (an A-vs-A ratio should straddle 1.00).
// Examples (from a project directory):
//   css-physics:  node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' out/a.html out/b.html
//   js-minus-js:  node ../shared/js/ab.js -r 3 -p haltMs 'IMG=img.json node machine/halttime.js {}' a.html b.html
// Options: -r rounds (default 5, rounded up as above), -p field, --json (print the raw values as JSON too), -v (print every run's number as it comes).
const { execSync } = require('child_process');
const { median, quantile } = require('./trace.js');

// the number called `name` in a command's output (see above); NaN if there is none
function pick(out, name) {
  for (const line of out.split('\n')) {
    const t = line.trim(); if (!t.startsWith('{')) continue;
    try { const o = JSON.parse(t); if (o && typeof o === 'object' && name in o) return +o[name]; } catch (e) { /* not JSON */ }
  }
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const m = out.match(new RegExp(`(?:^|[^\\w-])${esc}["']?\\s*[:=]?\\s*(-?\\d+(?:\\.\\d+)?(?:e-?\\d+)?)`));
  return m ? +m[1] : NaN;
}

// rows of the result table for values[k] = the numbers of variant k, ratios[k] = per-round ratios to variant 0
function summarize(names, values, ratios) {
  return names.map((n, k) => ({
    variant: n, runs: values[k].length, median: median(values[k]), min: Math.min(...values[k]), max: Math.max(...values[k]),
    ratio: median(ratios[k]), q25: quantile(ratios[k], 0.25), q75: quantile(ratios[k], 0.75),
  }));
}

async function main(argv) {
  let rounds = 5, field = null, json = false, verbose = false; const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-r') rounds = +argv[++i]; else if (a === '-p') field = argv[++i]; else if (a === '--json') json = true; else if (a === '-v') verbose = true;
    else pos.push(a);
  }
  const [cmd, ...variants] = pos;
  if (!cmd || !cmd.includes('{}') || variants.length < 2 || !field) {
    console.error("usage: ab.js [-r rounds] -p field 'command with {}' variantA variantB [...]"); process.exit(2);
  }
  rounds = Math.ceil(rounds / variants.length) * variants.length;
  const values = variants.map(() => []), ratios = variants.map(() => []);
  for (let r = 0; r < rounds; r++) {
    const got = new Array(variants.length).fill(NaN);
    for (let j = 0; j < variants.length; j++) {
      const k = (r + j) % variants.length;
      const c = cmd.split('{}').join(variants[k]);
      let out;
      try { out = execSync(c, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], shell: '/bin/bash', maxBuffer: 1 << 28 }); }
      catch (e) { console.error(`round ${r + 1}: command failed: ${c}\n${(e.stdout || '') + (e.stderr || '')}`.trim()); out = e.stdout || ''; }
      const v = pick(out, field);
      if (Number.isNaN(v)) console.error(`round ${r + 1}: no number "${field}" in the output of: ${c}`);
      got[k] = v; if (!Number.isNaN(v)) values[k].push(v);
      if (verbose) console.error(`round ${r + 1} ${variants[k]}: ${v}`);
    }
    for (let k = 0; k < variants.length; k++) if (got[0] > 0 && !Number.isNaN(got[k])) ratios[k].push(got[k] / got[0]);
  }
  const rows = summarize(variants, values, ratios);
  const w = Math.max(8, ...variants.map(v => v.length));
  console.log(`${'variant'.padEnd(w)}  runs  ${field.padStart(9)} (median, min-max)      ratio to ${variants[0]} (median, IQR)`);
  for (const x of rows) console.log(`${x.variant.padEnd(w)}  ${String(x.runs).padStart(4)}  ${x.median.toPrecision(4).padStart(9)} (${x.min.toPrecision(4)}-${x.max.toPrecision(4)})`.padEnd(w + 45) +
    `  ${x.ratio.toFixed(3)} (${x.q25.toFixed(3)}-${x.q75.toFixed(3)})`);
  if (json) console.log(JSON.stringify({ field, rounds, variants, values, ratios }));
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { pick, summarize, main };
