// uitest.js page — load with Run off, wait, switch Run on, time until the chain reports done; read the overlay words (harness only)
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
(async () => { const b = await launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); const cdp = await p.context().newCDPSession(p); await cdp.send('Performance.enable');
  const met = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
  const t0 = Date.now(); await p.goto(fileUrl(process.argv[2]), { timeout: 600000 }); const tl = Date.now() - t0;
  await p.waitForTimeout(800); const m0 = await met();
  const r0 = await p.evaluate(() => new Promise(res => { const t = performance.now(); document.getElementById('run').checked = true;
    const vis = e => e.getClientRects().length > 0;
    const poll = () => { const d = [...document.querySelectorAll('.fin')].find(vis); const w = d ? d.querySelector('.di').getBoundingClientRect().width : 0;
      if (w % 2 === 1) res({ ms: performance.now() - t, info: w, ok: d.querySelector('.dn').getBoundingClientRect().width }); else if (performance.now() - t > 30000) res({ ms: -1, info: w }); else requestAnimationFrame(poll); };
    requestAnimationFrame(poll); }));
  const m1 = await met();
  const r = await p.evaluate(() => { const out = { code: {}, data: {} };
    for (const e of document.querySelectorAll('.ov, .ovd, .ovs, .ovn, .ovk')) { if (!e.getClientRects().length) continue; const an = getComputedStyle(e).anchorName;
      if (an && an !== 'none') out[e.classList.contains('ov') ? 'code' : 'data'][an] = Math.round(e.getBoundingClientRect().width) - 1048576; }
    return out; });
  const inf = r0.info || 0;
  console.log(JSON.stringify({ loadMs: tl, doneMs: Math.round(r0.ms), recalcMs: Math.round((m1.RecalcStyleDuration - m0.RecalcStyleDuration) * 1000),
    layoutMs: Math.round((m1.LayoutDuration - m0.LayoutDuration) * 1000), recalcs: m1.RecalcStyleCount - m0.RecalcStyleCount,
    done: inf % 2, err: Math.floor(inf / 2) % 512, words: Math.floor(inf / 1024), ok: r0.ok, ...r }));
  await b.close(); })();
