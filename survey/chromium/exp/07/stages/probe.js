const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  const f = fs.readFileSync(process.argv[2]).toString('base64');
  await p.setContent(`<style>@font-face{font-family:S;src:url(data:font/ttf;base64,${f})}
  span{font-family:S;font-size:1024px;white-space:pre}</style>
  <span id=lat>a</span><br><span id=ar>&#x628;</span><br><span id=pf>&#xfb50;</span><br><span id=ar3>&#x628;&#x628;&#x628;</span><br>
  <span id=heb>&#x5d0;</span><br><span id=mix>a&#x628;</span><br><span id=off style="font-feature-settings:'stch' 0,'ccmp' 0">&#x628;</span>`);
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  console.log(await p.evaluate(() => ['lat', 'ar', 'pf', 'ar3', 'heb', 'mix', 'off'].map(i => i + '=' + document.getElementById(i).getBoundingClientRect().width).join(' ')));
  await b.close();
})();
