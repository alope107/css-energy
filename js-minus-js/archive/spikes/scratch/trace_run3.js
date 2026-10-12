const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 });
  if (process.argv[3] === 'ui') { await p.waitForTimeout(4000); await p.click('.runbtn'); await p.waitForTimeout(12000); } else await p.waitForTimeout(4000);
  await b.startTracing(p, { categories: ['devtools.timeline', 'blink'] }); await p.waitForTimeout(3000);
  const ev = JSON.parse((await b.stopTracing()).toString()).traceEvents.filter(e => e.ph === 'X');
  const ul = ev.filter(e => e.name === 'UpdateLayoutTree');
  const frames = ev.filter(e => e.name === 'WebFrameWidgetImpl::BeginMainFrame').length;
  const cnt = {}; for (const e of ul) { const k = e.args && e.args.elementCount; cnt[k] = cnt[k] || [0, 0]; cnt[k][0]++; cnt[k][1] += e.dur / 1000; }
  console.log('frames', frames, 'recalcs', ul.length, Object.entries(cnt).sort((a, b) => b[1][1] - a[1][1]).slice(0, 8).map(([k, v]) => `n=${k}: ${v[0]}x ${v[1].toFixed(0)}ms`).join('; '));
  for (const n of ['Layout', 'InlineNode::ShapeTextIncludingFirstLine', 'PrePaint', 'Paint', 'UpdateLayoutTree', 'Animation', 'ProxyMain::BeginMainFrame', 'LayoutView::HitTest', 'Document::updateStyle', 'StyleEngine::UpdateStyleAndLayoutTreeForContainer']) { const es = ev.filter(e => e.name === n); console.log(n, es.length, es.reduce((a, e) => a + e.dur / 1000, 0).toFixed(0) + 'ms'); }
  const paint = ev.filter(e => e.name === 'Paint'); console.log('paint events', paint.length, paint.reduce((a, e) => a + e.dur / 1000, 0).toFixed(0) + 'ms');
  await b.close(); })();
