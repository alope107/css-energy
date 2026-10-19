// node run.js dir page1,page2,... [rounds]  -> per page: median UpdateLayoutTree ms, ResolveStyle instants per UpdateLayoutTree
const path = require('path');
const R = '/workspaces/css-energy/.claude/worktrees/chromium-survey';
const { chromium } = require(require.resolve('playwright', { paths: ['/workspaces/css-energy/css-physics'] }));
const T = require(path.join(R, 'shared/js/trace.js'));
const dir = process.argv[2], pages = process.argv[3].split(','), rounds = +(process.argv[4] || 1);
const cats = process.env.INV ? T.CATS.invalidation : T.CATS.timeline;
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const res = {};
  for (let r = 0; r < rounds; r++) for (const f of pages) {
    const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
    await p.goto('file://' + path.resolve(dir, f));
    await p.waitForTimeout(+(process.env.WAIT||700));
    const { events } = await T.record(p, { categories: cats }, () => p.waitForTimeout(1200));
    const u = T.durations(events, 'UpdateLayoutTree');
    const rs = events.filter(e => e.name === 'StyleResolver::ResolveStyle').length;
    (res[f] = res[f] || []).push({ med: T.median(u), n: u.length, rsPer: u.length ? rs / u.length : 0 });
    await p.close();
  }
  for (const f of pages) {
    const a = res[f];
    console.log(f.padEnd(26), 'style med ms', a.map(x => x.med.toFixed(3)).join(' '), '| passes', a.map(x => x.n).join(' '),
      process.env.INV ? '| ResolveStyle/pass ' + a.map(x => x.rsPer.toFixed(1)).join(' ') : '');
  }
  await b.close();
})();
