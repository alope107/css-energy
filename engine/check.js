// engine/check.js — does this Chrome still behave the way css-physics and js-minus-js depend on? (harness only)
//
//   node engine/check.js [--profile physics|fontcpu|both] [probe-id …]      (from the repo root; default: both)
//
// Each probe tests one documented engine fact on a minimal page and checks a control on the same page: a case that
// must behave normally whatever the fact, so a probe that can't observe anything (a typo, a missing feature) is
// reported as BROKEN rather than as a pass or a fail.
//   PASS    the fact holds
//   FAIL    the control behaves but the fact doesn't: Chrome changed. Re-read the notes that cite it before relying on them.
//   BROKEN  the control failed: the probe itself is wrong, or the feature it uses is gone
//   WATCH   (watch probes) a missing feature both projects would use if Chrome shipped it; "changed" means it shipped
// Exits 1 on any FAIL or BROKEN. Run it after every Chrome upgrade (the devcontainer's Playwright image tag).
// The facts and where each project relies on them: engine/README.md.
const fs = require('fs'), os = require('os'), path = require('path');
const { profile } = require('../shared/js/browser.js');

const N = n => `@property --${n.name}{syntax:'${n.syntax || '<integer>'}';inherits:${n.inherits ? 'true' : 'false'};initial-value:${n.init ?? 0}}`;
const html = (css, body) => `<!doctype html><meta charset="utf-8"><style>${css}</style><body>${body}</body>`;
const prop = (id, name) => getComputedStyle(document.getElementById(id)).getPropertyValue(name).trim();

const PROBES = [
  {
    id: 'style-int-256', kind: 'fact',
    claim: '@container style(--v: N) never matches a calc()-computed registered <integer> of 256 or more',
    docs: 'js-minus-js docs/ENGINE_NOTES.md 1; CLAUDE.md pitfalls',
    page: () => html(N({ name: 'v' }) + '.c{--v:calc(var(--a) * 1)}.l{--v:256}i{--o:0}' +
      [255, 256, 1000].map(n => `@container style(--v: ${n}){.n${n}{--o:1}}`).join(''),
      [255, 256, 1000].map(n => `<div class=c style="--a:${n}"><i class=n${n} id=c${n}></i></div>`).join('') + '<div class=l><i class=n256 id=lit></i></div>'),
    read: () => ({ c255: prop('c255', '--o'), c256: prop('c256', '--o'), c1000: prop('c1000', '--o'), lit256: prop('lit', '--o') }),
    judge: r => ({ control: r.c255 === '1', holds: r.c256 === '0' && r.c1000 === '0',
      note: `computed 255 matches: ${r.c255 === '1'}; computed 256 / 1000: ${r.c256 === '1'} / ${r.c1000 === '1'}; literal 256 (not covered by the fact): ${r.lit256 === '1'}` }),
  },
  {
    id: 'var-6-digits', kind: 'fact',
    claim: 'a calc()-computed registered <integer>, or any registered <number>, keeps 6 significant digits when it crosses var()',
    docs: 'js-minus-js ENGINE_NOTES.md 2 (1048575 reads back as 1048580: keep words |v| < 2^19); css-physics CLAUDE.md (6 bodies per decimal word)',
    page: () => html(['r', 'x', 'd', 'y'].map(n => N({ name: n })).join('') + ['xn', 'yn', 'dn'].map(n => N({ name: n, syntax: '<number>' })).join('') +
      '#c7{--r:1048000;--x:calc(var(--r) + 575);--d:calc(var(--x) - 1048570);--y:var(--x)}#c6{--r:123000;--x:calc(var(--r) + 456);--d:calc(var(--x) - 123450)}' +
      '#l7{--x:1048575;--d:calc(var(--x) - 1048570)}#n8{--xn:1234.5678;--yn:var(--xn);--dn:calc((var(--yn) - 1234) * 10000)}',
      '<i id=c7></i><i id=c6></i><i id=l7></i><i id=n8></i>'),
    read: () => ({ calc7: +prop('c7', '--d'), calc6: +prop('c6', '--d'), lit7: +prop('l7', '--d'), num8: +prop('n8', '--dn'), plain7: prop('c7', '--y'), ser7: prop('c7', '--x') }),
    judge: r => ({ control: r.calc6 === 6, holds: r.calc7 === 10 && Math.abs(r.num8 - 5700) < 1,
      note: `calc() 1048575 serializes as ${r.ser7} and reads ${1048570 + r.calc7} in calc() (exact 1048575); 123456 exact: ${r.calc6 === 6}; ` +
        `1234.5678 reads 1234 + ${r.num8 / 10000}; observed, not part of the fact: a literal 1048575 reads ${1048570 + r.lit7}, and plain --y: var(--x) of the calc() value gives ${r.plain7} (invalid as an <integer>: the initial value)` }),
  },
  {
    id: 'style-bool', kind: 'fact',
    claim: 'style(--x) with no value is true iff a registered --x differs from its initial value (any other value, not just 1); an unregistered --x iff it is declared',
    docs: 'css-physics CLAUDE.md (BOOLQ; the style(--GIr) grab bug), docs/BENCHMARKS.md §2 feature support',
    page: () => html(N({ name: 'f' }) + N({ name: 'g', init: 7 }) + 'i{--o:0}@container style(--f){.qf{--o:1}}@container style(--g){.qg{--o:1}}@container style(--u){.qu{--o:1}}',
      [['f0', '--f:0', 'qf'], ['f1', '--f:1', 'qf'], ['f2', '--f:2', 'qf'], ['g7', '--g:7', 'qg'], ['g0', '--g:0', 'qg'], ['u0', '--u:0', 'qu'], ['un', '', 'qu']]
        .map(([id, st, q]) => `<div style="${st}"><i class=${q} id=${id}></i></div>`).join('')),
    read: () => Object.fromEntries(['f0', 'f1', 'f2', 'g7', 'g0', 'u0', 'un'].map(id => [id, prop(id, '--o') === '1'])),
    judge: r => ({ control: r.f1, holds: !r.f0 && r.f2 && !r.g7 && r.g0 && r.u0 && !r.un, note: JSON.stringify(r) }),
  },
  {
    id: 'style-range', kind: 'fact',
    claim: 'range style queries work: style(--h > 5)',
    docs: 'css-physics docs/BENCHMARKS.md §2 (1.7 µs per rule); CLAUDE.md',
    page: () => html(N({ name: 'h' }) + 'i{--o:0}@container style(--h > 5){.r{--o:1}}@container style(--h: 7){.e{--o:1}}',
      '<div style="--h:7"><i class=r id=r7></i><i class=e id=e7></i></div><div style="--h:3"><i class=r id=r3></i></div>'),
    read: () => ({ e7: prop('e7', '--o'), r7: prop('r7', '--o'), r3: prop('r3', '--o') }),
    judge: r => ({ control: r.e7 === '1', holds: r.r7 === '1' && r.r3 === '0', note: JSON.stringify(r) }),
  },
  {
    id: 'if-style', kind: 'fact',
    claim: 'if(style(--k: v): a; else: b) selects by a custom property',
    docs: 'js-minus-js display: if(style(--ccgo: 1): …) and read ports; css-physics experiments (r_if)',
    page: () => html(N({ name: 'k' }) + '.w{height:1px;width:if(style(--k: 1): 10px; else: 20px)}', '<div class=w id=a style="--k:1"></div><div class=w id=b style="--k:0"></div><div id=c style="width:30px;height:1px"></div>'),
    read: () => ({ a: document.getElementById('a').getBoundingClientRect().width, b: document.getElementById('b').getBoundingClientRect().width, c: document.getElementById('c').getBoundingClientRect().width }),
    judge: r => ({ control: r.c === 30, holds: r.a === 10 && r.b === 20, note: JSON.stringify(r) }),
  },
  {
    id: 'anchor-last', kind: 'fact',
    claim: 'when several elements share an anchor name, anchor-size() reads the last one in tree order',
    docs: 'js-minus-js ENGINE_NOTES.md 21 (compiler overlays override RAM leaves)',
    page: () => html('.box{position:relative;width:200px;height:50px}.a1,.a2,.s{height:5px}.a1{anchor-name:--q;width:10px}.a2{anchor-name:--q;width:20px}.s{anchor-name:--s;width:33px}' +
      '.rd{position:absolute;height:1px;width:anchor-size(--q width)}.rs{position:absolute;height:1px;width:anchor-size(--s width)}',
      '<div class=box><div class=a1></div><div class=a2></div><div class=s></div><div class=rd id=rd></div><div class=rs id=rs></div></div>'),
    read: () => ({ shared: document.getElementById('rd').getBoundingClientRect().width, solo: document.getElementById('rs').getBoundingClientRect().width }),
    judge: r => ({ control: r.solo === 33, holds: r.shared === 20, note: `shared name reads ${r.shared} (first 10, last 20); single anchor ${r.solo}` }),
  },
  {
    id: 'anchor-hidden', kind: 'fact',
    claim: 'an element in a display: none subtree is no anchor: anchor-size(--n width, fallback) reads the fallback',
    docs: 'js-minus-js ENGINE_NOTES.md 42 (sparse RAM groups)',
    page: () => html('.box{position:relative;width:200px;height:50px}.h{display:none}.a{width:40px;height:2px}.r{position:absolute;height:1px}',
      '<div class=box><div class=h><div class=a style="anchor-name:--hid"></div></div><div class=a style="anchor-name:--vis"></div>' +
      '<div class=r id=rh style="width:anchor-size(--hid width, 33px)"></div><div class=r id=rv style="width:anchor-size(--vis width, 33px)"></div></div>'),
    read: () => ({ hidden: document.getElementById('rh').getBoundingClientRect().width, visible: document.getElementById('rv').getBoundingClientRect().width }),
    judge: r => ({ control: r.visible === 40, holds: r.hidden === 33, note: JSON.stringify(r) }),
  },
  {
    id: 'html-nesting-512', kind: 'fact',
    claim: 'the HTML parser stops nesting at 512 elements; XHTML nests as deep as the markup',
    docs: 'js-minus-js ENGINE_NOTES.md 19, CLAUDE.md (pages must be XHTML)',
    pages: () => ({
      html: '<!doctype html><body>' + '<div>'.repeat(600) + '<i id=deep></i>' + '</div>'.repeat(600) + '</body>',
      xhtml: '<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/></head><body>' + '<div>'.repeat(600) + '<i id="deep"/>' + '</div>'.repeat(600) + '</body></html>',
    }),
    read: () => { let d = 0; for (let e = document.getElementById('deep'); e; e = e.parentElement) d++; return d; },
    judge: r => ({ control: r.xhtml >= 600, holds: r.html < 600, note: `depth of the innermost element: HTML ${r.html}, XHTML ${r.xhtml} (600 nested divs)` }),
  },
  {
    id: 'font-resets-fvs', kind: 'fact',
    claim: 'the font shorthand resets font-variation-settings declared before it',
    docs: 'css-physics CLAUDE.md; js-minus-js ENGINE_NOTES.md 8',
    page: () => html('', `<i id=a style="font-variation-settings:'wght' 700;font:16px serif"></i><i id=b style="font:16px serif;font-variation-settings:'wght' 700"></i>`),
    read: () => ({ before: getComputedStyle(document.getElementById('a')).fontVariationSettings, after: getComputedStyle(document.getElementById('b')).fontVariationSettings }),
    judge: r => ({ control: /wght/.test(r.after), holds: r.before === 'normal', note: JSON.stringify(r) }),
  },
  {
    id: 'play-state-base', kind: 'fact',
    claim: "animation-play-state computed from an element's own animated custom property doesn't pause its animations (Blink reads it from the base style)",
    docs: 'js-minus-js ENGINE_NOTES.md 9 (the original probe is lost; this is the literal reading)',
    page: () => html(N({ name: 'p' }) + N({ name: 'z', syntax: '<number>' }) + '@keyframes setp{from{--p:1}to{--p:1}}@keyframes spin{from{--z:0}to{--z:100}}' +
      '#an{animation:setp 1000s linear infinite,spin 10s linear infinite}#st{--p:1;animation:spin 10s linear infinite}' +
      '#an,#st{animation-play-state:if(style(--p: 1): paused; else: running)}',
      '<i id=an></i><i id=st></i>'),
    wait: 600,
    read: () => { const z = id => +getComputedStyle(document.getElementById(id)).getPropertyValue('--z');
      return { animated: z('an'), static: z('st'), animatedState: getComputedStyle(document.getElementById('an')).animationPlayState, p: prop('an', '--p') }; },
    judge: r => ({ control: r.static === 0, holds: r.animated > 0, note: `animated flag (--p = ${r.p}, computed play state "${r.animatedState}"): --z ${r.animated.toFixed(2)}; static flag: --z ${r.static}` }),
  },
  {
    id: 'var-ident', kind: 'watch',
    claim: 'var(ident("--m" var(--k))) (dynamic property names) is not supported',
    docs: 'unsupported in 141 and 153; it would give both projects dynamic indexing',
    page: () => html(N({ name: 'op', syntax: '<number>', init: -99 }), '<i id=x style=\'--pc:3;--m3:13;--op:var(ident("--m" var(--pc)))\'></i><i id=y style="--m3:13;--op:var(--m3)"></i>'),
    read: () => ({ ident: +prop('x', '--op'), plain: +prop('y', '--op') }),
    judge: r => ({ control: r.plain === 13, holds: r.ident !== 13, note: `var(ident(…)) reads ${r.ident} (13 if supported)` }),
  },
];

async function runProbe(B, b, dir, P) {
  const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
  await p.addInitScript(`window.prop = ${prop.toString()}`);   // the reads' helper (harness only: the probe pages have no script)
  try {
    let r;
    if (P.pages) {
      r = {};
      for (const [ext, src] of Object.entries(P.pages())) {
        const f = path.join(dir, `${P.id}.${ext}`); fs.writeFileSync(f, src);
        await p.goto(require('url').pathToFileURL(f).href); await p.waitForTimeout(P.wait || 100);
        r[ext] = await p.evaluate(P.read);
      }
    } else {
      const f = path.join(dir, `${P.id}.html`); fs.writeFileSync(f, P.page());
      await p.goto(require('url').pathToFileURL(f).href); await p.waitForTimeout(P.wait || 100);
      r = await p.evaluate(P.read);
    }
    const j = P.judge(r);
    const status = !j.control ? 'BROKEN' : P.kind === 'watch' ? (j.holds ? 'WATCH' : 'WATCH-CHANGED') : j.holds ? 'PASS' : 'FAIL';
    return { status, ...j };
  } catch (e) {
    return { status: 'BROKEN', note: String(e).split('\n')[0] };
  } finally { await p.close(); }
}

async function main(argv) {
  let profiles = ['physics', 'fontcpu']; const only = [];
  for (let i = 0; i < argv.length; i++) { if (argv[i] === '--profile') { const v = argv[++i]; profiles = v === 'both' ? profiles : [v]; } else only.push(argv[i]); }
  const probes = PROBES.filter(P => !only.length || only.includes(P.id));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-check-'));
  let bad = 0;
  try {
    for (const name of profiles) {
      const B = profile(name); const b = await B.launch();
      console.log(`== ${name} profile (${B.args.join(' ')}): ${b.version()}`);
      for (const P of probes) {
        const r = await runProbe(B, b, dir, P);
        if (r.status === 'FAIL' || r.status === 'BROKEN') bad++;
        console.log(`${r.status.padEnd(13)} ${P.id.padEnd(18)} ${P.claim}\n${''.padEnd(32)}${r.note}`);
      }
      await b.close();
    }
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
  console.log(bad ? `${bad} probe(s) failed or broken` : 'all facts hold');
  process.exit(bad ? 1 : 0);
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { PROBES };
