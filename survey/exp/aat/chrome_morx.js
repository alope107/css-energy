// does Chrome apply a web font's morx table? width of '0000|' after 5 increments: 0101 -> 600 units
const fs = require('fs'); const { launch } = require('../lib.js');
(async () => {
  const b = await launch(); const p = await b.newPage();
  const fonts = ['morx', 'gsub'].map(m => [m, fs.readFileSync(__dirname + `/ctr_${m}.ttf`).toString('base64')]);
  const html = `<style>${fonts.map(([m, d]) => `@font-face{font-family:C${m};src:url(data:font/ttf;base64,${d})}`).join('')}
    span{font-size:100px;white-space:pre}</style>` + fonts.map(([m]) => ['0000|', '0111|', '1011|'].map(t => `<div><span style="font-family:C${m}" data-m="${m}">${t}</span></div>`).join('')).join('');
  p.on('console', m => console.log('console:', m.text()));
  await p.setContent(html); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  console.log(await p.evaluate(() => [...document.querySelectorAll('span')].map(s => `${s.dataset.m} ${s.textContent} ${s.getBoundingClientRect().width}px`).join('\n')));
  console.log('expect 600 600 400 (x0.1 px per unit at 100px/1000upem: 60 60 40); unshaped: 50 70 70');
  await b.close();
})();
