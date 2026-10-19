const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox']});
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><style>
    .a{height:10px} .r{position:absolute;top:0;left:0;height:1px}
  </style><body style="position:relative">
  <div class="a" style="anchor-name:--cvh;width:50px;content-visibility:hidden"></div>
  <div class="a" style="anchor-name:--cva;width:60px;content-visibility:auto;contain-intrinsic-size:auto 60px 10px"></div>
  <div class="a" style="anchor-name:--vis;width:70px"></div>
  <div style="content-visibility:hidden;width:80px;height:10px"><div class="a" style="anchor-name:--inner;width:80px"></div></div>
  <div class="r" id="r1" style="width:anchor-size(--cvh width, 7px)"></div>
  <div class="r" id="r2" style="width:anchor-size(--cva width, 7px)"></div>
  <div class="r" id="r3" style="width:anchor-size(--vis width, 7px)"></div>
  <div class="r" id="r4" style="width:anchor-size(--inner width, 7px)"></div></body>`);
  await page.waitForTimeout(300);
  console.log(await page.evaluate(() => ['r1','r2','r3','r4'].map(id => id + '=' + document.getElementById(id).offsetWidth).join(' ')));
  await browser.close();
})();
