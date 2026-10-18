// does a GSUB with more than 16,384 (aliased) subtables run in Chrome, with HarfBuzz and with HarfRust?
const fs = require('fs'); const { launch } = require('../lib.js');
(async () => {
  for (const flags of [[], ['--enable-blink-features=HarfRustShaping']]) {
    const b = await launch(flags); const p = await b.newPage();
    const ms = ['5', '5000', '6000'];
    await p.setContent(`<style>${ms.map(m => `@font-face{font-family:C${m};src:url(data:font/ttf;base64,${fs.readFileSync(__dirname + `/cap${m}.ttf`).toString('base64')})}`).join('')} span{font-size:100px;white-space:pre}</style>` +
      ms.map(m => `<div><span style="font-family:C${m}" data-m="${m}">0000000000000000|</span></div>`).join(''));
    await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(500);
    const r = await p.evaluate(() => [...document.querySelectorAll('span')].map(s => `M=${s.dataset.m} ${s.getBoundingClientRect().width}px`));
    console.log((flags[0] || 'default HarfBuzz').padEnd(40), r.join(', '), '| expect', ms.map(m => (16 + [...(+m).toString(2)].filter(c => c === '1').length) * 10).join(', '), '(unshaped 160)');
    await b.close();
  }
})();
