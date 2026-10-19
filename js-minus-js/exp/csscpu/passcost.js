// passcost.js page.html [waitMs] [secs] — per-frame cost on a running CPU page from a light trace (devtools.timeline):
// Layout and UpdateLayoutTree (style) per frame, layouts per frame, frame interval. Harness only.
const path = require('path');
const { launch, fileUrl } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
const { record, CATS, median } = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'trace.js'));
(async () => {
  const [pg, wait = '900', secs = '1'] = process.argv.slice(2);
  const b = await launch({}); const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto(fileUrl(pg)); await p.waitForTimeout(+wait);
  const { events } = await record(p, { categories: CATS.timeline }, () => p.waitForTimeout(+secs * 1000));
  const X = events.filter(e => e.ph === 'X' && e.dur);
  const lay = X.filter(e => e.name === 'Layout'), sty = X.filter(e => e.name === 'UpdateLayoutTree');
  const main = lay.length ? lay[0].tid : 0;
  const frames = X.filter(e => e.tid === main && (e.name === 'PageAnimator::serviceScriptedAnimations' || e.name === 'WebFrameWidgetImpl::UpdateLifecycle' || e.name === 'LocalFrameView::RunPostLifecycleSteps'));
  const ulc = X.filter(e => e.tid === main && e.name === 'UpdateLifecycle' ).length ? X.filter(e => e.tid === main && e.name === 'UpdateLifecycle') : X.filter(e => e.tid === main && e.name === 'WebFrameWidgetImpl::UpdateLifecycle');
  const sum = a => a.reduce((s, e) => s + e.dur / 1000, 0);
  const t0 = Math.min(...X.map(e => e.ts)), t1 = Math.max(...X.map(e => e.ts + e.dur)), span = (t1 - t0) / 1000;
  const n = Math.max(1, ulc.length);
  console.log(JSON.stringify({ page: path.basename(pg), spanMs: +span.toFixed(0), frames: ulc.length, msPerFrame: +(span / n).toFixed(1),
    layoutsPerFrame: +(lay.length / n).toFixed(2), layoutMsPerFrame: +(sum(lay) / n).toFixed(1), styleMsPerFrame: +(sum(sty) / n).toFixed(1),
    layoutMedian: +median(lay.map(e => e.dur / 1000)).toFixed(2), styleMedian: +median(sty.map(e => e.dur / 1000)).toFixed(2) }));
  await b.close();
})();
