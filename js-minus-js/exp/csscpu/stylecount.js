// stylecount.js page.html [waitMs] [secs] — which elements a CPU page restyles per layout pass: StyleResolver::ResolveStyle
// instants (ENGINE_NOTES 34) grouped by the node's name, inside Layout vs Document::recalcStyle, with Layout and
// recalcStyle durations. Harness only.
const path = require('path');
const { launch, fileUrl } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
const { record, CATS, durations, median } = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'trace.js'));
(async () => {
  const [pg, wait = '1200', secs = '1'] = process.argv.slice(2);
  const b = await launch({}); const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto(fileUrl(pg)); await p.waitForTimeout(+wait);
  const { events } = await record(p, { categories: CATS.invalidation }, () => p.waitForTimeout(+secs * 1000));
  const lay = events.filter(e => e.ph === 'X' && e.name === 'Layout'), rs = events.filter(e => e.ph === 'X' && e.name === 'Document::recalcStyle');
  const inside = (e, L) => L.some(l => l.tid === e.tid && e.ts >= l.ts && e.ts <= l.ts + l.dur);
  // node ids are backend node ids: name them by tag and class
  const cdp = await p.context().newCDPSession(p); await cdp.send('DOM.getDocument', { depth: -1 });
  const names = {};
  for (const id of new Set(events.filter(e => e.name === 'StyleResolver::ResolveStyle').map(e => e.args.data.nodeId))) {
    try { const { node } = await cdp.send('DOM.describeNode', { backendNodeId: id }); const a = node.attributes || [];
          const cl = a[a.indexOf('class') + 1]; names[id] = node.localName + (a.includes('class') ? '.' + cl.split(' ')[0] : a.includes('id') ? '#' + a[a.indexOf('id') + 1] : ''); }
    catch { names[id] = '?'; }
  }
  const cnt = { layout: {}, recalc: {}, other: {} };
  for (const e of events) {
    if (e.name !== 'StyleResolver::ResolveStyle') continue;
    const nm = (names[e.args.data.nodeId] || '?') + (e.args.data.pseudoId ? '::' + e.args.data.pseudoId : '');
    const k = inside(e, lay) ? 'layout' : inside(e, rs) ? 'recalc' : 'other'; cnt[k][nm] = (cnt[k][nm] || 0) + 1;
  }
  // per style recalc (UpdateLayoutTree): resolves and their top node names
  const ult = events.filter(e => e.ph === 'X' && e.name === 'UpdateLayoutTree').sort((a, b) => a.ts - b.ts);
  const rs2 = events.filter(e => e.name === 'StyleResolver::ResolveStyle');
  if (process.env.PER) for (const u of ult) {
    const c = {}; for (const e of rs2) if (e.tid === u.tid && e.ts >= u.ts && e.ts <= u.ts + u.dur) { const nm = names[e.args.data.nodeId] || '?'; c[nm] = (c[nm] || 0) + 1; }
    const tot = Object.values(c).reduce((a, b) => a + b, 0);
    console.log((u.dur / 1000).toFixed(1).padStart(6), 'ms', String(tot).padStart(6), Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([n, k]) => n + ':' + k).join(' '));
  }
  const L = durations(events, 'Layout'), R = durations(events, 'Document::recalcStyle');
  console.log(`Layout n=${L.length} median ${median(L).toFixed(1)} ms; recalcStyle n=${R.length} median ${median(R).toFixed(1)} ms`);
  for (const k of Object.keys(cnt)) {
    const rows = Object.entries(cnt[k]).sort((a, b) => b[1] - a[1]); const tot = rows.reduce((s, r) => s + r[1], 0);
    console.log(k, 'per Layout', (tot / Math.max(1, L.length)).toFixed(0), rows.slice(0, 14).map(([n, c]) => `${n}:${(c / Math.max(1, L.length)).toFixed(1)}`).join('  '));
  }
  await b.close();
})();
