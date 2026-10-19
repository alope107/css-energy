const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/tf.html');
  const w = s => p.$eval(s, e => e.getBoundingClientRect().width);
  const r = { o1: await w('#o1'), o2: await w('#o2'), sy: await p.evaluate(() => scrollY) };
  await p.click('#l'); await p.waitForTimeout(800);
  r.after1 = [await w('#o1'), await w('#o2'), await p.evaluate(() => scrollY), await p.evaluate(() => location.href.slice(-30))];
  await p.evaluate(() => scrollTo(0, 0)); await p.waitForTimeout(100);
  await p.click('#l2'); await p.waitForTimeout(800);
  r.after2 = [await w('#o1'), await w('#o2'), await p.evaluate(() => scrollY)];
  // http-served variant needed? also test navigation to URL with directive
  await p.goto('file://' + __dirname + '/tf.html#:~:text=zebra'); await p.waitForTimeout(800);
  r.nav = [await w('#o1'), await w('#o2'), await p.evaluate(() => scrollY)];
  console.log(JSON.stringify(r)); await b.close();
})();
