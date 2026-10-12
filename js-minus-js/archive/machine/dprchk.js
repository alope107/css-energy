const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1200, height: 800 }, deviceScaleFactor: +(process.env.DPR || 1) });
  await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(4000);
  console.log(await p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); const r = getComputedStyle(document.documentElement);
    return JSON.stringify({ dpr: devicePixelRatio, R: r.getPropertyValue('--R'), Rok: r.getPropertyValue('--Rok'), fok: c.getPropertyValue('--fok'), go: c.getPropertyValue('--go'), steps: c.getPropertyValue('--steps'), kind: c.getPropertyValue('--kind'),
      sent: document.querySelector('#sent span').getBoundingClientRect().width, mm: matchMedia('(min-resolution: 1.9dppx)').matches }); }));
  await b.close(); })();
