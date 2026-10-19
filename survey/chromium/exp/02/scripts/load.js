// node load.js page.html [waitMs] -> durations of style-setup events during load
const path = require('path');
const R = '/workspaces/css-energy/.claude/worktrees/chromium-survey';
const { chromium } = require(require.resolve('playwright', { paths: ['/workspaces/css-energy/css-physics'] }));
const T = require(path.join(R, 'shared/js/trace.js'));
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
  await p.goto('about:blank');
  const t0 = Date.now();
  const { events } = await T.record(p, { categories: 'blink,blink_style,devtools.timeline,loading' }, async () => {
    await p.goto('file://' + path.resolve(process.argv[2]), { waitUntil: 'load', timeout: 120000 });
    const tl = Date.now() - t0;
    await p.waitForTimeout(+(process.argv[3] || 3000));
    return tl;
  });
  const names = ['ParseHTML', 'CSSParserImpl::parseStyleSheet', 'CSSParserImpl::parseStyleSheet.parse', 'ParseAuthorStyleSheet',
    'Document::updateActiveStyle', 'StyleEngine::updateActiveStyleSheets', 'RuleSet::addRulesFromSheet', 'UpdateLayoutTree',
    'Document::recalcStyle', 'Document::rebuildLayoutTree', 'Layout', 'Paint', 'MajorGC', 'MinorGC', 'BlinkGC.AtomicPhase', 'V8.GC_MC_BACKGROUND_MARKING'];
  const agg = T.aggregate(events);
  for (const n of names) if (agg[n]) console.log(n.padEnd(40), 'n', String(agg[n].n).padStart(4), 'total ms', agg[n].t.toFixed(1).padStart(8), 'max', agg[n].max.toFixed(1));
  const u = T.durations(events, 'UpdateLayoutTree');
  console.log('first 5 UpdateLayoutTree ms', u.slice(0, 5).map(x => x.toFixed(1)).join(' '), '| median later', T.median(u.slice(5)).toFixed(1));
  // top self-time events
  const st = T.selfTime(events).sort((a, c) => c[2] - a[2]).slice(0, 15);
  for (const [n, tot, self, c] of st) console.log('  self', n.padEnd(48), self.toFixed(1), 'ms (total', tot.toFixed(1) + ', n', c + ')');
  await b.close();
})();
