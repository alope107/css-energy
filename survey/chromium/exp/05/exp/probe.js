// Rough layout-cost probes in Chromium 153. JS only in the harness.
// Each case builds DOM, then times N forced style+layout passes caused by a tiny driver change.
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const cases = {
  // E1: anchored OOF elements are restyled + relaid out on every OOF layout of their containing block
  a0_fixed_plain:    {N:2000, mode:'fixed', width:'50px'},
  a1_fixed_anchor:   {N:2000, mode:'fixed', width:'anchor-size(--a width)'},
  a2_fixed_anchor_cb:{N:2000, mode:'fixed', width:'anchor-size(--a width)', cb:true},
  // E2: anchor propagation copies per rebuilt ancestor level
  b0_noanchor_d0:  {N:4000, mode:'anchors', names:false, depth:0, drvInside:true},
  b1_anchor_d0:    {N:4000, mode:'anchors', names:true,  depth:0, drvInside:true},
  b2n_noanchor_d40:{N:4000, mode:'anchors', names:false, depth:40, drvInside:true},
  b2_anchor_d40:   {N:4000, mode:'anchors', names:true,  depth:40, drvInside:true},
  b3_anchor_d40_drvtop:{N:4000, mode:'anchors', names:true, depth:40, drvInside:false},
  // E3: FindScopeElement walk: anchors at the bottom of a deep display:contents chain, parent rebuilt each pass
  c0n_chain0_noname: {N:1000, mode:'chain', names:false, chain:0},
  c0_chain0:         {N:1000, mode:'chain', names:true, chain:0},
  c1n_chain400_noname:{N:1000, mode:'chain', names:false, chain:400},
  c1_chain400:       {N:1000, mode:'chain', names:true, chain:400},
  c2_chain400_scope: {N:1000, mode:'chain', names:true, chain:400, scope:true},
};
function build(c) {
  const b = document.body; b.innerHTML = '';
  const st = document.createElement('style'); document.head.appendChild(st);
  const drv = document.createElement('div'); drv.id = 'drv'; drv.style.cssText = 'width:10px;height:1px';
  if (c.mode === 'fixed') {
    const host = c.cb ? Object.assign(document.createElement('div'), {style: 'contain: layout; position:relative'}) : b;
    if (c.cb) b.appendChild(host);
    const a = document.createElement('div'); a.style.cssText = 'anchor-name:--a;width:50px;height:2px'; host.appendChild(a);
    let h = '';
    for (let i = 0; i < c.N; i++) h += `<div class="f"></div>`;
    const w = document.createElement('div'); w.innerHTML = h; host.appendChild(w);
    st.textContent = `.f{position:fixed;top:0;left:0;height:1px;width:${c.width}}`;
    b.appendChild(drv);
  } else if (c.mode === 'anchors') {
    let parent = b;
    for (let d = 0; d < c.depth; d++) { const x = document.createElement('div'); x.style.cssText='display:flow-root'; parent.appendChild(x); parent = x; }
    const W = document.createElement('div'); W.style.cssText = 'display:flow-root';
    let h = '';
    for (let i = 0; i < c.N; i++) h += c.names ? `<div style="anchor-name:--n${i}" class="x"></div>` : `<div class="x"></div>`;
    W.innerHTML = h; parent.appendChild(W);
    st.textContent = `.x{width:3px;height:1px}`;
    (c.drvInside ? parent : b).appendChild(drv);
  } else if (c.mode === 'chain') {
    const W = document.createElement('div'); W.style.cssText = 'display:flow-root'; b.appendChild(W);
    let parent = W;
    for (let d = 0; d < c.chain; d++) { const x = document.createElement('div'); x.style.display='contents'; parent.appendChild(x); parent = x; }
    if (c.scope) parent.style.anchorScope = 'all';
    let h = '';
    for (let i = 0; i < c.N; i++) h += c.names ? `<div style="anchor-name:--n${i}" class="x"></div>` : `<div class="x"></div>`;
    const tmp = document.createElement('div'); tmp.innerHTML = h;
    while (tmp.firstChild) parent.appendChild(tmp.firstChild);
    st.textContent = `.x{width:3px;height:1px}`;
    W.appendChild(drv);   // drv inside W: W (the anchors' parent box) is rebuilt every pass
  }
  document.body.offsetWidth;
}
function run(iters) {
  const drv = document.getElementById('drv');
  const t = [];
  for (let i = 0; i < iters; i++) {
    const t0 = performance.now();
    drv.style.width = (10 + (i & 1)) + 'px';
    document.body.offsetWidth;
    t.push(performance.now() - t0);
  }
  t.sort((a, b) => a - b);
  return t[t.length >> 1];
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(cases);
  const rounds = 3, res = {};
  for (let r = 0; r < rounds; r++) for (const n of names) {
    const page = await browser.newPage();
    await page.setContent('<!doctype html><html><head></head><body></body></html>');
    await page.evaluate(build, cases[n]);
    await page.evaluate(run, 30);
    const m = await page.evaluate(run, 200);
    (res[n] = res[n] || []).push(m);
    await page.close();
  }
  for (const n of names) { const v = res[n].sort((a,b)=>a-b); console.log(n.padEnd(24), 'median ms/pass', v[1].toFixed(3), ' all', v.map(x=>x.toFixed(3)).join(' ')); }
  await browser.close();
})();
