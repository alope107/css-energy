// hr.js page [flags...] — CPU shaping time during a FizzBuzz run (median of InlineNode::ShapeTextIncludingFirstLine > 5 ms)
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const [pg, ...flags] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu', ...flags] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto('file://' + path.resolve(pg));
  await p.waitForTimeout(3000);
  await p.click('.runbtn'); await p.waitForTimeout(3500);
  const tp = path.resolve('hr.' + process.pid + '.json');
  await b.startTracing(p, { path: tp, categories: ['blink', 'devtools.timeline'] });
  await p.waitForTimeout(4000);
  await b.stopTracing(); await b.close();
  const ev = JSON.parse(fs.readFileSync(tp)).traceEvents; fs.unlinkSync(tp);
  const d = ev.filter(e => e.ph === 'X' && e.name === 'InlineNode::ShapeTextIncludingFirstLine' && e.dur > 5000).map(e => e.dur / 1000).sort((a, b) => a - b);
  const small = ev.filter(e => e.ph === 'X' && e.name === 'InlineNode::ShapeTextIncludingFirstLine' && e.dur > 100 && e.dur < 5000).map(e => e.dur / 1000).sort((a, b) => a - b);
  console.log((flags.join(' ') || 'default').padEnd(40), `big shapings n=${d.length} median=${d[d.length >> 1].toFixed(2)} ms p25=${d[d.length >> 2].toFixed(2)} | cv01=0 shapings n=${small.length} median=${(small[small.length >> 1] || 0).toFixed(3)} ms`);
})();
