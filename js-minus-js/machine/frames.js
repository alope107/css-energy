// frames.js page.html nframes — per-frame trace of fvm internals from frame 0 (harness-injected, page has no script)
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
(async () => {
  const [pg, nf = '12', extra = ''] = process.argv.slice(2);
  const b = await launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.addInitScript(([nf, extra]) => {
    window.__tr = [];
    const names = ['t','init','kind','go','k','fresh','PC','SP','FP','MAR','T1','T2','RES','steps','optr','A0','V0'].concat(extra ? extra.split(',') : []);
    const f = () => {
      const c = document.querySelector('#cpu');
      if (c && document.querySelector('.regs')) try { const cs = getComputedStyle(c); const o = {}; for (const n of names) o[n] = cs.getPropertyValue('--' + n).trim();
        const st = document.querySelector('#state'); o.sp = [...st.children].filter(e => e.style.anchorName).slice(0, 12).map(e => Math.round(e.getBoundingClientRect().width)).join(',');
        const vp = document.querySelector('.vp'); if (vp) { const v = getComputedStyle(vp); o.i = ['--next-PC','--next-steps','--mval','--resT','--i3','--i4'].map(x => v.getPropertyValue(x)).join(','); }
        __tr.push(o); } catch (e) { __tr.push({err: String(e)}); }
      if (__tr.length < nf) requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
  }, [+nf, extra]);
  await p.goto(fileUrl(pg), { timeout: 600000 });
  for (let i = 0; i < 60; i++) { const n = await p.evaluate(() => __tr.length); console.error("n", n); if (n >= +nf) break; await p.waitForTimeout(1000); }
  for (const o of await p.evaluate(() => __tr)) console.log(JSON.stringify(o));
  await b.close();
})();
