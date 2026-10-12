const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); await p.waitForTimeout(2000);
  await b.startTracing(p, { categories: ['devtools.timeline', 'blink', 'cc', 'gpu'] }); await p.waitForTimeout(1000);
  const ev = JSON.parse((await b.stopTracing()).toString()).traceEvents.filter(e => e.ph === 'X' && e.dur > 500);
  const agg = {}; for (const e of ev) { agg[e.name] = agg[e.name] || [0, 0]; agg[e.name][0] += e.dur / 1000; agg[e.name][1]++; }
  console.log(Object.entries(agg).sort((a, b) => b[1][0] - a[1][0]).slice(0, 18).map(([k, v]) => `${k} ${v[0].toFixed(0)}ms x${v[1]}`).join('\n'));
  const ul = ev.filter(e => e.name === 'UpdateLayoutTree').map(e => `${(e.dur / 1000).toFixed(1)}/${e.args && e.args.elementCount}`); console.log(ul.slice(0, 12).join(' '));
  await b.close(); })();
