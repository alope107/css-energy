const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); await p.waitForTimeout(2000);
  await b.startTracing(p, { categories: ['devtools.timeline', 'blink'] }); await p.waitForTimeout(2000);
  const ev = JSON.parse((await b.stopTracing()).toString()).traceEvents.filter(e => e.ph === 'X');
  const sum = n => ev.filter(e => e.name === n).reduce((a, e) => a + e.dur / 1000, 0);
  const frames = ev.filter(e => e.name === 'WebFrameWidgetImpl::BeginMainFrame').length;
  console.log('frames/2s', frames, 'style', sum('UpdateLayoutTree').toFixed(0), 'layout', sum('Layout').toFixed(0), 'paint', sum('Paint').toFixed(0), 'prepaint', sum('PrePaint').toFixed(0), 'hit', sum('LayoutView::HitTest').toFixed(0), 'anim', sum('Blink.Animate.UpdateTime').toFixed(0), 'bmf', sum('ProxyMain::BeginMainFrame').toFixed(0));
  await b.close(); })();
