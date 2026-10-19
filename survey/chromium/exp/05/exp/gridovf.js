const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  const page = await browser.newPage();
  const results = [];
  for (const [n, w] of [[1000, 1000], [1000, 60000], [1000, 70000], [1000, 100000], [2000, 100000], [100, 1000000]]) {
    await page.setContent(`<!doctype html><style>
      #g{display:grid;grid-template-columns:repeat(${2*n},auto);width:max-content}
      #a{grid-column:1 / ${2*n+1};grid-row:1;width:${w}px;height:1px}
      #b{grid-column:1 / ${n+1};grid-row:2;width:0;height:1px}
      #p{grid-column:${n+1};grid-row:3;height:1px}
    </style><div id=g><div id=a></div><div id=p></div></div>`);
    const r = await page.evaluate(() => ({left: document.getElementById('p').offsetLeft, gw: document.getElementById('g').offsetWidth}));
    results.push({tracksPerSet: n, itemWidth: w, expectedLeft: +(w*n/(2*n-1)).toFixed(1), ...r, raw_x_ratio: w*64*n, wraps: w*64*n >= 2**32});
  }
  console.table(results);
  await browser.close();
})();
