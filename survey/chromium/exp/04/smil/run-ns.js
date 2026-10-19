const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const r = await page.evaluate(() => {
    const src = '<svg><foreignObject><div>x</div><set attributeName="width" to="3"/></foreignObject><g id="after"></g></svg>';
    const out = {};
    for (const type of ['text/html', 'application/xhtml+xml']) {
      const doc = new DOMParser().parseFromString(type === 'text/html' ? src : '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + src.replace('<svg>', '<svg xmlns="http://www.w3.org/2000/svg">').replace('<div>', '<div xmlns="http://www.w3.org/1999/xhtml">') + '</body></html>', type);
      const set = doc.querySelector('set');
      const g = doc.getElementById('after');
      out[type] = { setNS: set && set.namespaceURI, gParent: g && g.parentNode.localName, gNS: g && g.namespaceURI };
    }
    return out;
  });
  console.log(JSON.stringify(r));
  await browser.close();
})();
