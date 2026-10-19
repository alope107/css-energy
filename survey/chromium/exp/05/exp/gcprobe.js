const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
function build(c) {
  const b = document.body; b.innerHTML = '';
  // c.groups group boxes under body (like memtree .tn.gn), each holding c.per anchors (wrapper div + cell)
  let h = '';
  for (let g = 0; g < c.groups; g++) {
    h += '<div style="display:block;height:0">';
    for (let i = 0; i < c.per; i++) { const k = g * c.per + i; h += c.names ? `<div style="anchor-name:--c${k};width:${k%97+1}px;height:0"><i></i></div>` : `<div style="width:${k%97+1}px;height:0"><i></i></div>`; }
    h += '</div>';
  }
  b.innerHTML = h + '<div id="drv" style="width:10px;height:1px"></div>';
  document.body.offsetWidth;
}
async function run(iters) {
  const drv = document.getElementById('drv');
  let inLayout = 0; const T0 = performance.now();
  for (let i = 0; i < iters; i++) {
    const t0 = performance.now();
    drv.style.width = (10 + (i & 1)) + 'px';
    document.body.offsetWidth;
    inLayout += performance.now() - t0;
    await new Promise(r => setTimeout(r, 0));
  }
  return {inLayout: inLayout / iters, wall: (performance.now() - T0) / iters};
}
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--js-flags=--expose-gc']});
  const cases = {none: {groups: 64, per: 256, names: false}, named: {groups: 64, per: 256, names: true}};
  for (let r = 0; r < 2; r++) for (const [n, c] of Object.entries(cases)) {
    const page = await browser.newPage();
    await page.setContent('<!doctype html><body></body>');
    await page.evaluate(build, c);
    await page.evaluate(run, 30);
    const m = await page.evaluate(run, 300);
    console.log(n, `16384 cells: in-layout ${m.inLayout.toFixed(3)} ms/pass, wall ${m.wall.toFixed(3)} ms/iter`);
    await page.close();
  }
  await browser.close();
})();
