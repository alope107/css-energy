// fullrun.js page.html maxMinutes — run the page to HALT, then read the console grid and compare with image.json expected (harness only)
const { launch, fileUrl, envArgs } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => {
  const [pg, mins = '40', haltKind = '97'] = process.argv.slice(2);
  const im = JSON.parse(fs.readFileSync(process.env.IMG || 'image.json'));
  const b = await launch({ extraArgs: envArgs('FLAGS') });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: +(process.env.VW || 1200), height: 800 }, deviceScaleFactor: +(process.env.DPR || 1) });
  const cdp = await p.context().newCDPSession(p); await cdp.send('HeapProfiler.enable');
  const t0 = Date.now();
  await p.goto(fileUrl(pg), { timeout: 600000 });
  let last = -1, same = 0, r;
  while ((Date.now() - t0) / 60000 < +mins) {
    await p.waitForTimeout(+(process.env.DT || 10000));
    if (process.env.GC) await cdp.send('HeapProfiler.collectGarbage');
    r = await p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu')); return { steps: +cs.getPropertyValue('--steps'), kind: +cs.getPropertyValue('--kind'), pc: +cs.getPropertyValue('--PC') }; });
    const rss = require('child_process').execSync("ps -eo rss,args --sort=-rss | grep -m1 renderer | awk '{print $1}'").toString().trim();
    console.error(((Date.now() - t0) / 1000).toFixed(0) + 's', JSON.stringify(r), 'rssMB', Math.round(+rss / 1024));
    if (r.steps === last) { if (++same >= 3) break; } else same = 0;
    last = r.steps;
  }
  const codes = await consoleCodes(p);
  const got = gridText(codes, im.rows, im.cols); const want = im.expected.replace(/\s+$/, '');
  console.log(JSON.stringify({ secs: (Date.now() - t0) / 1000, final: r, match: got === want }));
  console.log(got); console.log(JSON.stringify(codes.slice(0, 24)));
  await b.close();
})();
