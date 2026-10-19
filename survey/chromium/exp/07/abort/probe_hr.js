const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--enable-blink-features=HarfRustShaping'] });
  const p = await b.newPage();
  const f1 = fs.readFileSync(process.argv[2]).toString('base64'), f0 = fs.readFileSync(process.argv[3]).toString('base64');
  await p.setContent(`<style>@font-face{font-family:A1;src:url(data:font/ttf;base64,${f1})}@font-face{font-family:A0;src:url(data:font/ttf;base64,${f0})}
  span{font-size:1024px;font-feature-settings:"cv01" 1;white-space:pre}</style>
  <span id=a1 style="font-family:A1">ab</span><br><span id=a0 style="font-family:A0">ab</span><br><span id=b1 style="font-family:A1">bab</span><br><span id=b0 style="font-family:A0">bab</span>`);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(300);
  console.log(await p.evaluate(() => ['a1', 'a0', 'b1', 'b0'].map(i => i + '=' + document.getElementById(i).getBoundingClientRect().width).join(' ')));
  await b.close();
})();
