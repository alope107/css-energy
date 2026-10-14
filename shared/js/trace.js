// trace.js — record Chrome traces through CDP and summarise them (harness only).
//
//   const {events, result} = await record(page, {categories: CATS.timeline}, () => countFrames(page, 1500));
//   const u = durations(events, 'UpdateLayoutTree'); median(u); bigmed(u, 1);
//
// Event times in a trace are µs; every function here returns ms.

const CATS = {
  timeline: 'devtools.timeline',
  // which elements get restyled or relaid out: StyleResolver::ResolveStyle instants and LayoutInvalidationTracking
  // events carry node names and reasons (js-minus-js docs/ENGINE_NOTES.md, note 34)
  invalidation: 'devtools.timeline,disabled-by-default-devtools.timeline,disabled-by-default-devtools.timeline.invalidationTracking',
  // what shared/py/passprof.py needs (Commit, LocalFrameView::UpdateStyleAndLayout, shaping): js-minus-js machine/trace.js's list
  frames: 'blink,devtools.timeline,disabled-by-default-devtools.timeline,blink.animations,fonts,benchmark,cc,blink_style',
};

// Trace while `during()` runs; returns {events, result: what during() returned}. `browser: true` traces through a
// browser-level session (every process: compositor and GPU events too) instead of the page's.
async function record(page, { categories = CATS.timeline, browser = false } = {}, during) {
  const cdp = browser ? await page.context().browser().newBrowserCDPSession() : await page.context().newCDPSession(page);
  const events = []; const h = d => events.push(...d.value);
  cdp.on('Tracing.dataCollected', h);
  await cdp.send('Tracing.start', { categories, transferMode: 'ReportEvents' });
  const result = await during();
  const done = new Promise(r => cdp.once('Tracing.tracingComplete', r));
  await cdp.send('Tracing.end'); await done;
  cdp.off('Tracing.dataCollected', h);
  await cdp.detach().catch(() => {});
  return { events, result };
}

// Durations (ms) of the complete events called `name`.
const durations = (ev, name) => ev.filter(e => e.ph === 'X' && e.name === name).map(e => e.dur / 1000);

// Upper median (the element at length >> 1 of the sorted list, as every tool has used); 0 for an empty list.
const median = a => { const v = [...a].sort((x, y) => x - y); return v.length ? v[v.length >> 1] : 0; };
const quantile = (a, q) => { const v = [...a].sort((x, y) => x - y); return v.length ? v[Math.min(v.length - 1, Math.floor(v.length * q))] : NaN; };

// Median of the "big" passes: those over max(floor, 30% of the largest). A live css-physics page alternates big
// physics passes with small ones, and the plain median mixes them.
const bigmed = (a, floor) => { const mx = a.length ? Math.max(...a) : -Infinity; return median(a.filter(x => x > Math.max(floor, mx * 0.3))); };

// {name: {n, t, max}} over complete events (t and max in ms), optionally only those passing `keep(e)`.
function aggregate(ev, keep = () => true) {
  const agg = {};
  for (const e of ev) {
    if (e.ph !== 'X' || !keep(e)) continue;
    const a = agg[e.name] = agg[e.name] || { n: 0, t: 0, max: 0 };
    a.n++; a.t += e.dur / 1000; a.max = Math.max(a.max, e.dur / 1000);
  }
  return agg;
}

// Self time on the renderer's main thread (the thread with the most RunTask + Layout time): each event's duration
// minus that of the events nested directly in it. Totals double-count nested events; self times add up.
// Returns rows [name, total ms, self ms, count] in first-seen order (sort them in the caller).
function selfTime(ev) {
  ev = ev.filter(e => e.ph === 'X' && e.dur);
  const main = {};
  for (const e of ev) if (e.name === 'ThreadControllerImpl::RunTask' || e.name === 'Layout') main[e.tid] = (main[e.tid] || 0) + e.dur;
  if (!Object.keys(main).length) for (const e of ev) main[e.tid] = (main[e.tid] || 0) + e.dur;   // categories without RunTask
  const tid = +Object.entries(main).sort((a, b) => b[1] - a[1])[0][0];
  const es = ev.filter(e => e.tid === tid).sort((a, b) => a.ts - b.ts || b.dur - a.dur);
  const self = {}, tot = {}, cnt = {}; const st = [];
  for (const e of es) {
    while (st.length && st[st.length - 1].ts + st[st.length - 1].dur <= e.ts) st.pop();
    if (st.length) self[st[st.length - 1].name] -= e.dur;
    self[e.name] = (self[e.name] || 0) + e.dur; tot[e.name] = (tot[e.name] || 0) + e.dur; cnt[e.name] = (cnt[e.name] || 0) + 1; st.push(e);
  }
  return Object.keys(tot).map(n => [n, tot[n] / 1e3, self[n] / 1e3, cnt[n]]);
}

// Write events as a trace file ({traceEvents}: what chrome://tracing, Perfetto and shared/py/passprof.py read).
const saveTrace = (ev, file) => require('fs').writeFileSync(file, JSON.stringify({ traceEvents: ev }));

module.exports = { CATS, record, durations, median, quantile, bigmed, aggregate, selfTime, saveTrace };
