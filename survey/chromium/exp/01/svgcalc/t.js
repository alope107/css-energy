const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/t.html'); await p.waitForTimeout(300);
  const r = await p.evaluate(() => new Promise(res => { const out = []; (function f() {
    out.push(['a', 'b', 'c'].map(id => document.getElementById(id).getBoundingClientRect().width).join('/') + ' fs=' + getComputedStyle(document.getElementById('a')).fontSize);
    if (out.length < 90) requestAnimationFrame(f); else res([...new Set(out)]); })(); }));
  console.log(r.join('\n')); await b.close();
})();
