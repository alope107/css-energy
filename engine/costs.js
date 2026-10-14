// engine/costs.js — re-measure the style-engine costs both projects design around (harness only).
//
//   node engine/costs.js [--rounds 3] [--profile physics|fontcpu] [case …]      (from the repo root; ~1.5 min)
//
// Pages are the microbenchmarks behind css-physics docs/BENCHMARKS.md §2 (same templates as experiments/costs/mk2.py,
// mk_gating.py and part_styleform.py): one element under an animated parent, so every frame restyles it. Each page's
// cost is the median style pass (UpdateLayoutTree) over 1.5 s, measured as tools/stylebench.js does, in interleaved
// rounds (median of the rounds); per unit = (page − its baseline page) / units. Prints measured against documented
// (Chromium 153, 2026-10-13) and flags DRIFT outside half the documented low to twice the high: then re-measure in
// the project and update its docs (css-physics BENCHMARKS.md §2; js-minus-js ENGINE_NOTES.md 7 cites it).
// A busy machine inflates everything: run it with no other browser jobs.
const fs = require('fs'), os = require('os'), path = require('path');
const { profile } = require('../shared/js/browser.js');
const { record, durations, median } = require('../shared/js/trace.js');
const { countFrames } = require('../shared/js/page.js');

// ---- page templates (verbatim from the experiments)
const M = 2000;   // mk2.py: props on one element
const mk2 = (decl, reg = true, syntax = '<number>') => {
  const regs = reg ? Array.from({ length: M }, (_, i) => `@property --b${i}{syntax:'${syntax}';inherits:false;initial-value:0}`).join('') : '';
  const body = Array.from({ length: M }, (_, i) => decl(i)).join(';');
  return `<!doctype html><style>${regs}@property --t{syntax:'<number>';inherits:true;initial-value:0}
@keyframes t{from{--t:0}to{--t:1000}}
#a{animation:t 1000s linear infinite}
#b{${body}}</style><div id=a><div id=b></div></div>`;
};
// mk_gating.py page('cq0.html', 0, 'absent'): the empty baseline of §2
const cq0 = () => {
  const regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}";
  const css = `${regs}@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#c1,#c2,#c3{container-name:pres q1 q2}#b{--o:var(--t)}`;
  return `<!doctype html><style>${css}</style><div id=a><div id=c1><div id=c2><div id=c3><div id=b></div></div></div></div></div>`;
};
// part_styleform.py emit(): R rules on #b under the container #c1 (name pres), whose flags change every frame
const R = 24000;
const sf = rule => {
  const REG = "@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}" +
    "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}@property --h{syntax:'<integer>';inherits:true;initial-value:7}";
  const HEAD = '@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}';
  const rules = rule ? Array.from({ length: R }, (_, k) => rule.replace(/\{k\}/g, k)).join('') : '';
  return `<!doctype html><style>${REG}${HEAD}#c1{container-name:pres q1 q2;--g0:calc(var(--t) * 0);--h:calc(var(--t) * 0 + 7);--u:0;--v:1}${rules}</style><div id=a><div id=c1><div id=b></div></div></div>`;
};

// [id, what, page, baseline id, units, documented µs per unit [lo, hi], source]
const CASES = [
  ['cq0', 'empty page (baseline)', cq0, null],
  ['sf0', 'container page with no rules (baseline)', () => sf(null), null],
  ['prop-reg-const', 'registered <number> prop, constant', () => mk2(i => `--b${i}:${i}`), 'cq0', M, [1.57, 1.57], 'BENCHMARKS §2 mk2 r_const'],
  ['prop-reg-calc', 'registered prop, calc(var(--t) * k)', () => mk2(i => `--b${i}:calc(var(--t) * ${i})`), 'cq0', M, [2.15, 2.15], 'BENCHMARKS §2 mk2 r_var1'],
  ['prop-unreg-const', 'unregistered prop, constant', () => mk2(i => `--b${i}:${i}`, false), 'cq0', M, [0.49, 0.49], 'BENCHMARKS §2 mk2 u_const'],
  ['rule-name', 'rule gated by a present container name, no style()', () => sf('@container pres{#b{--o:calc(var(--t) * {k})}}'), 'sf0', R, [0.07, 0.16], 'BENCHMARKS §2 rule matching'],
  ['rule-style-eq', 'present name + false style(--g: 1)', () => sf('@container pres style(--g0: 1){#b{--o:calc(var(--t) * {k})}}'), 'sf0', R, [0.56, 0.74], 'BENCHMARKS §2; CLAUDE.md 0.7'],
  ['rule-style-bool', 'present name + false style(--g) (no value)', () => sf('@container pres style(--g0){#b{--o:calc(var(--t) * {k})}}'), 'sf0', R, [0.40, 0.41], 'BENCHMARKS §2; CLAUDE.md 0.4'],
  ['rule-range', 'present name + false range style(--h > 9)', () => sf('@container pres style(--h > 9){#b{--o:calc(var(--t) * {k})}}'), 'sf0', R, [1.57, 1.57], 'BENCHMARKS §2; CLAUDE.md 1.6'],
];

async function measure(B, b, file) {
  const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
  await p.goto(require('url').pathToFileURL(file).href); await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(500);
  const { events } = await record(p, {}, () => countFrames(p, 1500));
  await p.close();
  return median(durations(events, 'UpdateLayoutTree'));
}

async function main(argv) {
  let rounds = 3, prof = 'physics'; const only = [];
  for (let i = 0; i < argv.length; i++) { if (argv[i] === '--rounds') rounds = +argv[++i]; else if (argv[i] === '--profile') prof = argv[++i]; else only.push(argv[i]); }
  const want = new Set(CASES.filter(c => !only.length || only.includes(c[0])).flatMap(c => [c[0], c[3]]).filter(Boolean));
  const cases = CASES.filter(c => want.has(c[0]));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-costs-'));
  const B = profile(prof);
  // stylebench.js's flags (the §2 numbers were measured with it)
  const b = await B.launch({ args: prof === 'physics' ? ['--no-sandbox', '--no-zygote', '--disable-setuid-sandbox'] : undefined });
  console.log(`${prof} profile, ${b.version()}, ${rounds} interleaved rounds`);
  const ms = {};
  try {
    for (const c of cases) fs.writeFileSync(path.join(dir, c[0] + '.html'), c[2]());
    for (let r = 0; r < rounds; r++) for (let j = 0; j < cases.length; j++) {
      const c = cases[(j + r) % cases.length];
      (ms[c[0]] = ms[c[0]] || []).push(await measure(B, b, path.join(dir, c[0] + '.html')));
    }
  } finally { await b.close(); fs.rmSync(dir, { recursive: true, force: true }); }
  const m = Object.fromEntries(Object.entries(ms).map(([k, v]) => [k, median(v)]));
  let drift = 0;
  for (const [id, what, , base, units, doc, src] of cases) {
    if (!base) { console.log(`${id.padEnd(17)} ${m[id].toFixed(2).padStart(6)} ms  ${what}`); continue; }
    const per = (m[id] - m[base]) / units * 1000, [lo, hi] = doc;
    const ok = per >= lo / 2 && per <= hi * 2; if (!ok) drift++;
    console.log(`${id.padEnd(17)} ${m[id].toFixed(2).padStart(6)} ms  ${per.toFixed(2).padStart(5)} µs per unit, documented ${lo === hi ? lo : lo + '–' + hi}${ok ? '' : '  DRIFT'}  ${what} (${src})`);
  }
  console.log(drift ? `${drift} cost(s) drifted beyond ×2 of the documented value: re-measure before relying on the docs` : 'costs within ×2 of the documented values');
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { CASES };
