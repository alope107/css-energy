// can CSS tell a pending probe from a failed one? <img alt> sizes against paint's serve.js:
// never-written cell (dcz without a dictionary), a written cell's right and wrong probes, and a pending (delayed) load
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const { spawn } = require('child_process'); const fs = require('fs'), os = require('os'), path = require('path');
const SITE = '/workspaces/css-energy/paint/site';
const srv = (port, extra = []) => { const s = spawn('node', ['/workspaces/css-energy/paint/serve.js', SITE, String(port), ...extra], { stdio: 'ignore' }); return s; };
(async () => {
  const a = srv(8791), d = srv(8792, ['--delay', '6000']);
  await new Promise(r => setTimeout(r, 800));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'imgstate-'));
  const ctx = await chromium.launchPersistentContext(dir, { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  try {
    const p = await ctx.newPage();
    await p.goto('http://localhost:8791/nope', { waitUntil: 'commit' });
    // write cell 7 = 3 (the dictionary for /c/7/r/*)
    await p.setContent(`<img src="http://localhost:8791/c/7/d/3.png">`, { waitUntil: 'commit' }); await p.waitForTimeout(1500);
    const css = `<style>img{font:20px/20px monospace;border:0;vertical-align:top} .z{display:inline-block}</style>`;
    const cases = [['never written', 'http://localhost:8791/c/9/r/3.png'], ['written, right value', 'http://localhost:8791/c/7/r/3.png'],
      ['written, wrong value', 'http://localhost:8791/c/7/r/5.png'], ['404', 'http://localhost:8791/nope.png'],
      ['pending (6 s delay)', 'http://localhost:8792/c/7/r/3.png?x']];
    const html = css + cases.map(([n, u], i) => `<div>${n}: <img id=i${i} alt="XXXX" src="${u}"> <img id=n${i} src="${u}&amp;n" > <i id=c${i} class=z style="content:url(${u.replace('?x', '')}${u.includes('?') ? '&' : '?'}c)"></i></div>`).join('');
    await p.goto('http://localhost:8791/nope', { waitUntil: 'commit' }); await p.setContent(html, { waitUntil: 'commit' });
    for (const t of [300, 2500]) {
      await p.waitForTimeout(t === 300 ? 300 : 2200);
      const r = await p.evaluate(n => [...Array(n).keys()].map(i => { const s = id => { const e = document.getElementById(id); const b = e.getBoundingClientRect(); return `${b.width}x${b.height}`; }; return `alt ${s('i' + i)} | no-alt ${s('n' + i)} | content:url ${s('c' + i)}`; }), cases.length);
      console.log(`after ~${t} ms:`); r.forEach((x, i) => console.log('  ', cases[i][0].padEnd(22), x));
    }
  } finally { await ctx.close(); a.kill(); d.kill(); }
})();
