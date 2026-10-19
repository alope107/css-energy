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
  // ---- touch: css-physics's touch input (ARCHITECTURE.md "Touch"). The gestures go through Chromium's gesture recognizer
  // (CDP touch events, on a touch-emulated phone viewport): touch slop, scroll latching, axis locking, flings.
  {
    id: 'touch-snap-defer', kind: 'fact', ctx: 'touch',
    claim: 'a scroll-snap container re-snaps after a layout change at once, except while a scroll gesture is active anywhere on the page: then it waits until the gesture ends',
    docs: 'css-physics ARCHITECTURE.md "Touch" (the follower #FO, --held); Blink LocalFrameView::ShouldDeferLayoutSnap',
    page: () => html('body{margin:0;timeline-scope:--ix,--iy}#I{width:300px;height:300px;overflow:scroll;scroll-timeline:--ix x,--iy y}#I>div{width:900px;height:900px}' +
      '#O{width:10px;height:10px;overflow:hidden;scroll-snap-type:both mandatory}#O>i{display:block;position:relative;width:1000px;height:1000px}' +
      '#T{position:absolute;width:1px;height:1px;scroll-snap-align:start;animation:fx linear both,fy linear both;animation-timeline:--ix,--iy}' +
      '@keyframes fx{from{left:0}to{left:600px}}@keyframes fy{from{top:0}to{top:600px}}',
      '<div id=I><div></div></div><div id=O><i><i id=T></i></i></div>'),
    act: async (p, T) => {
      const off = () => p.evaluate(() => [I.scrollLeft, I.scrollTop, O.scrollLeft, O.scrollTop].map(Math.round));
      await p.evaluate(() => I.scrollTo(100, 100)); await p.waitForTimeout(100); const prog = await off();   // a programmatic scroll: O follows
      await T('touchStart', 150, 150); for (let k = 1; k <= 8; k++) { await T('touchMove', 150 - 8 * k, 150 - 6 * k); await p.waitForTimeout(16); }
      await p.waitForTimeout(150); const mid = await off(); await T('touchEnd'); await p.waitForTimeout(150);
      return { prog, mid, end: await off() };
    },
    read: () => ({}),
    judge: r => ({ control: r.prog[2] === r.prog[0] && r.prog[3] === r.prog[1] && r.end[0] !== r.prog[0],
      holds: r.mid[2] === r.prog[2] && r.mid[0] !== r.prog[0] && r.end[2] === r.end[0] && r.end[3] === r.end[1],
      note: `follower after a programmatic scroll ${r.prog.slice(2)} (scroller ${r.prog.slice(0, 2)}); mid-drag ${r.mid.slice(2)} (scroller ${r.mid.slice(0, 2)}); after the finger lifts ${r.end.slice(2)} (scroller ${r.end.slice(0, 2)})` }),
  },
  {
    id: 'scroll-axis-lock', kind: 'fact', ctx: 'touch',
    claim: 'scroll-axis-lock: none stops a touch drag that starts nearly horizontal from being locked to the horizontal axis',
    docs: 'css-physics ARCHITECTURE.md "Touch" (the handles)',
    page: () => html('body{margin:0}.s{position:absolute;left:0;width:300px;height:200px;overflow:scroll}.s>div{width:900px;height:900px}#a{top:0}#b{top:250px;scroll-axis-lock:none}',
      '<div class=s id=a><div></div></div><div class=s id=b><div></div></div>'),
    act: async (p, T) => {
      const drag = async y => { await T('touchStart', 250, y); for (let k = 1; k <= 12; k++) { await T('touchMove', 250 - 10 * k, y - 4 * k); await p.waitForTimeout(16); } await T('touchEnd'); await p.waitForTimeout(300); };
      await drag(150); await drag(400);
      return p.evaluate(() => ({ a: [a.scrollLeft, a.scrollTop], b: [b.scrollLeft, b.scrollTop] }));
    },
    read: () => ({}),
    judge: r => ({ control: r.a[0] > 80 && r.a[1] === 0, holds: r.b[0] > 80 && r.b[1] > 30,
      note: `drag (-120, -48): default ${r.a} (locked to x), scroll-axis-lock:none ${r.b}` }),
  },
  {
    id: 'touch-3d-scroll', kind: 'fact', ctx: 'touch',
    claim: 'a touch drag scrolls a 3D-transformed scroller by the finger movement unprojected onto its plane: its offset in its own px is the screen movement / its on-screen scale',
    docs: 'css-physics ARCHITECTURE.md "Touch" (the handles measure the drag in world units)',
    page: () => html('body{margin:0}.st{position:absolute;left:0;width:400px;height:300px;perspective:800px}#s1{top:0}#s2{top:320px}' +
      '.c{position:absolute;left:150px;top:100px;width:100px;height:100px;overflow:scroll;scrollbar-width:none;scroll-axis-lock:none}.c>div{width:2000px;height:2000px}' +
      '#d{transform:translateZ(-400px)}',
      '<div class=st id=s1><div class=c id=d><div></div></div></div><div class=st id=s2><div class=c id=f><div></div></div></div>'),
    act: async (p, T) => {
      const drag = async (x, y) => { await T('touchStart', x, y); for (let k = 1; k <= 10; k++) { await T('touchMove', x - 8 * k, y - 4 * k); await p.waitForTimeout(16); } await T('touchEnd'); await p.waitForTimeout(300); };
      const r = await p.evaluate(() => [d, f].map(e => { const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2, b.width / 100]; }));
      await drag(r[0][0], r[0][1]); await drag(r[1][0], r[1][1]);
      return { sc: r[0][2], d: await p.evaluate(() => [d.scrollLeft, d.scrollTop]), f: await p.evaluate(() => [f.scrollLeft, f.scrollTop]) };
    },
    read: () => ({}),
    judge: r => {
      // the same drag (80, 40 px minus the touch slop) on a flat scroller and on one shown at scale sc: offsets in the ratio 1 / sc
      const k = r.d[0] / r.f[0];
      return { control: r.f[0] > 40 && r.f[1] > 15, holds: Math.abs(k * r.sc - 1) < 0.08 && Math.abs(r.d[1] / r.f[1] * r.sc - 1) < 0.15,
        note: `flat ${r.f}; at on-screen scale ${r.sc.toFixed(3)}: ${r.d} (ratio ${k.toFixed(3)}, 1 / scale ${(1 / r.sc).toFixed(3)})` };
    },
  },
  // served over HTTP (probe.http: path -> [content type, body]; the page is `index.html`): stylesheet MIME checks don't
  // apply to file: URLs, and responsive iframes need a child document from the same server
  {
    id: 'quirks-lax-css', kind: 'fact',
    claim: 'a quirks-mode page applies a same-origin stylesheet served with any Content-Type (JSON, text/plain); a standards-mode page only text/css or none',
    docs: 'js-minus-js docs/ENGINE_NOTES.md 50 (the NET modem reads the gateway\'s answers, served as application/json)',
    http: {
      'index.html': ['text/html', '<!doctype html><iframe id=q src=q.html></iframe><iframe id=s src=s.html></iframe>'],
      'q.html': ['text/html', '<link rel=stylesheet href=j.json><link rel=stylesheet href=c.css><i id=j></i><i id=c></i>'],
      's.html': ['text/html', '<!doctype html><link rel=stylesheet href=j.json><link rel=stylesheet href=c.css><i id=j></i><i id=c></i>'],
      'j.json': ['application/json', '#j{--o:1}'], 'c.css': ['text/css', '#c{--o:1}'],
    },
    read: () => Object.fromEntries(['q', 's'].flatMap(f => { const d = document.getElementById(f).contentDocument;
      return ['j', 'c'].map(i => [f + i, getComputedStyle(d.getElementById(i)).getPropertyValue('--o').trim()]); })),
    judge: r => ({ control: r.qc === '1' && r.sc === '1', holds: r.qj === '1' && r.sj === '',
      note: `text/css applies in quirks / standards: ${r.qc === '1'} / ${r.sc === '1'}; application/json: ${r.qj === '1'} / ${r.sj === '1'}` }),
  },
  {
    id: 'responsive-iframe', kind: 'fact', flags: ['--enable-blink-features=ResponsiveIframes'],
    claim: 'responsive iframes (on by default from 155; a flag in 153): frame-sizing: content-height sizes the iframe to an opted-in child\'s content height, but no lower than the iframe\'s height when the child loaded',
    docs: 'js-minus-js docs/ENGINE_NOTES.md 51-52 (the NET modem\'s answers are its height)',
    http: {
      'index.html': ['text/html', '<!doctype html><style>iframe{border:0;width:50px;frame-sizing:content-height}</style>' +
        '<iframe id=t src="c.html?h=345"></iframe><iframe id=s src="c.html?h=40"></iframe><iframe id=n src="n.html"></iframe>'],
      // 153 reads the meta's content as the allowed origins, 155+ as allow-origins=…: one of the two opts in
      'c.html': ['text/html', q => `<meta name=responsive-embedded-sizing content="*"><meta name=responsive-embedded-sizing content="allow-origins=*">` +
        `<style>html,body{margin:0}</style><div style="height:${q.get('h')}px"></div>`],
      'n.html': ['text/html', '<style>html,body{margin:0}</style><div style="height:345px"></div>'],
    },
    wait: 1500,      // (the height is reported at DOMContentLoaded and at load; read after both)
    read: () => Object.fromEntries(['t', 's', 'n'].map(i => [i, document.getElementById(i).getBoundingClientRect().height])),
    judge: r => ({ control: r.n === 150, holds: r.t === 345 && r.s === 150,
      note: `content 345 px: ${r.t}; content 40 px (in a 150 px iframe): ${r.s}; not opted in: ${r.n} (150 = default)` }),
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

// touch probes run on a touch-emulated phone viewport and drive gestures through CDP (act(page, touch))
const TOUCH_CTX = { viewport: { width: 412, height: 915 }, deviceScaleFactor: 2.625, isMobile: true, hasTouch: true };
async function runProbe(B, b, dir, P) {
  const ctx = P.ctx === 'touch' ? await b.newContext(TOUCH_CTX) : null;
  const p = ctx ? await ctx.newPage() : await b.newPage({ viewport: { width: 1000, height: 800 } });
  await p.addInitScript(`window.prop = ${prop.toString()}`);   // the reads' helper (harness only: the probe pages have no script)
  try {
    let r;
    if (P.http) {
      const srv = require('http').createServer((req, res) => {
        const u = new URL(req.url, 'http://x'), [type, body] = P.http[u.pathname.slice(1)] || ['text/plain', null];
        res.writeHead(body === null ? 404 : 200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
        res.end(typeof body === 'function' ? body(u.searchParams) : body || '');
      });
      await new Promise(ok => srv.listen(0, '127.0.0.1', ok));
      try { await p.goto(`http://127.0.0.1:${srv.address().port}/index.html`); await p.waitForTimeout(P.wait || 300); r = await p.evaluate(P.read); }
      finally { srv.close(); }
    } else if (P.pages) {
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
      if (P.act) {
        const c = await p.context().newCDPSession(p);
        const T = (type, x, y) => c.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
        Object.assign(r, await P.act(p, T));
      }
    }
    const j = P.judge(r);
    const status = !j.control ? 'BROKEN' : P.kind === 'watch' ? (j.holds ? 'WATCH' : 'WATCH-CHANGED') : j.holds ? 'PASS' : 'FAIL';
    return { status, ...j };
  } catch (e) {
    return { status: 'BROKEN', note: String(e).split('\n')[0] };
  } finally { await p.close(); if (ctx) await ctx.close(); }
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
        const fb = P.flags && await B.launch({ extraArgs: P.flags });     // a probe with flags gets its own browser
        const r = await runProbe(B, fb || b, dir, P); if (fb) await fb.close();
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
