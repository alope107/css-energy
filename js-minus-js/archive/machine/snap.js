// snap.js page.html stepsTarget — dump .vp input counters at the first frame where --steps == target
const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const path = require('path');
(async () => {
  const [pg, tgt] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.addInitScript(tgt => { window.__snap = null; const f = () => {
      const c = document.querySelector('#cpu'), vp = document.querySelector('.vp');
      if (c && vp && document.querySelector('.regs')) { const cs = getComputedStyle(c);
        if (+cs.getPropertyValue('--steps') == tgt && !window.__snap) { const v = getComputedStyle(vp); const o = {};
          for (let i = 0; i < 1200; i++) { const x = v.getPropertyValue('--i' + i); if (x !== '') o[i] = +x; }
          const r = {}; for (const n of ['PC','SP','FP','RES','CR','MAR','T1','T2','init','kind','resvT','v0','v1','isMISS','isWFAIL','isPUTC','isHALT','isEXT','vdirty','fill0','doWB','go','fresh','k'].concat([...Array(16).keys()].flatMap(k => ['A'+k,'V'+k,'vf'+k,'vd'+k,'tag'+k,'vfT'+k,'vdT'+k,'tagT'+k,'valT'+k]))) r[n] = v.getPropertyValue('--' + n);
          window.__snap = { inputs: o, regs: r }; return; } }
      requestAnimationFrame(f); }; requestAnimationFrame(f); }, +tgt);
  await p.goto('file://' + path.resolve(pg), { timeout: 600000 });
  await p.waitForFunction(() => window.__snap, null, { timeout: 120000, polling: 500 });
  console.log(JSON.stringify(await p.evaluate(() => __snap)));
  await b.close();
})();
