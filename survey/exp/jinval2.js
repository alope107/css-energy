// restyles per pass on the js-minus-js page mid-run, by phase (UpdateLayoutTree vs Layout) and parent element
const { launch } = require('./lib.js'); const url = require('url');
const { record, CATS } = require('/workspaces/css-energy/shared/js/trace.js');
(async () => {
  const b = await launch(['--disable-gpu', '--no-proxy-server']);
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto(url.pathToFileURL(process.argv[2]).href); await p.waitForTimeout(+(process.env.WAIT || 3000));
  if (!process.env.NORUN) { await p.click('.runbtn'); await p.waitForTimeout(3500); }
  const { events } = await record(p, { categories: CATS.invalidation }, () => p.waitForTimeout(1500));
  const X = n => events.filter(x => x.name === n && x.ph === 'X');
  const sp = { layout: X('Layout'), recalc: X('UpdateLayoutTree') };
  const nPass = sp.recalc.length;
  const where = e => { for (const k of ['layout', 'recalc']) if (sp[k].some(x => x.tid === e.tid && x.ts <= e.ts && e.ts <= x.ts + x.dur)) return k; return 'other'; };
  const rs = events.filter(e => e.name === 'StyleResolver::ResolveStyle');
  const agg = {};
  for (const e of rs) { const d = e.args.data || e.args; const k = `${where(e)}|${d.parentNodeId}`; agg[k] = (agg[k] || 0) + 1; }
  const cdp = await p.context().newCDPSession(p); await cdp.send('DOM.getDocument', { depth: 0 });
  const desc = async id => { try { const { node } = await cdp.send('DOM.describeNode', { backendNodeId: id }); const a = node.attributes || []; const g = n => { const i = a.indexOf(n); return i >= 0 ? a[i + 1] : ''; }; return `${node.localName}${g('id') ? '#' + g('id') : ''}${g('class') ? '.' + g('class').split(' ').join('.') : ''}`; } catch (e) { return '?' + id; } };
  console.log(`passes (UpdateLayoutTree) ${nPass}, layouts ${sp.layout.length}, ResolveStyle ${rs.length} (${(rs.length / nPass).toFixed(0)} per pass)`);
  const tot = {}; for (const [k, v] of Object.entries(agg)) { const ph = k.split('|')[0]; tot[ph] = (tot[ph] || 0) + v; }
  console.log('by phase per pass:', Object.entries(tot).map(([k, v]) => `${k} ${(v / nPass).toFixed(0)}`).join(', '));
  for (const [k, v] of Object.entries(agg).sort((a, b) => b[1] - a[1]).slice(0, 25)) { const [ph, par] = k.split('|'); console.log(String((v / nPass).toFixed(1)).padStart(8), ph.padEnd(7), 'children of', await desc(+par)); }
  await b.close();
})();
