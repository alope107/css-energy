const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const ctx = await b.newContext({ viewport: { width: 400, height: 700 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  const p = await ctx.newPage(); await p.goto('file://' + __dirname + '/touch.html');
  const c = await ctx.newCDPSession(p);
  const x = s => p.$eval(s, e => e.getBoundingClientRect().left);
  const w = s => p.$eval(s, e => e.getBoundingClientRect().width);
  const r = {};
  const rb = await p.$eval('#r', e => { const q = e.getBoundingClientRect(); return [q.left, q.top + q.height / 2, q.width]; });
  r.thumb0 = await x('#ra'); r.v0 = await p.$eval('#r', e => e.value);
  // touch drag via synthesizeScrollGesture? use dispatchTouchEvent sequence
  const tx = rb[0] + rb[2] * 0.1, ty = rb[1];
  await c.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: tx, y: ty }] });
  for (let i = 1; i <= 10; i++) { await c.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: tx + i * 15, y: ty }] }); await p.waitForTimeout(16); }
  r.thumbMid = await x('#ra'); r.vMid = await p.$eval('#r', e => e.value);
  await c.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await p.waitForTimeout(100); r.thumb1 = await x('#ra'); r.v1 = await p.$eval('#r', e => e.value);
  // long press on interest button
  const ib = await p.$eval('#ib', e => { const q = e.getBoundingClientRect(); return [q.left + 20, q.top + 20]; });
  await c.send('Input.synthesizeTapGesture', { x: ib[0], y: ib[1], duration: 1200, tapCount: 1, gestureSourceType: 'touch' });
  await p.waitForTimeout(200); r.interest = await w('#oi'); r.pop = await p.$eval('#tip', e => e.matches(':popover-open'));
  // :active during a held touch (no move)
  const ac = await p.$eval('#ac', e => { const q = e.getBoundingClientRect(); return [q.left + 20, q.top + 20]; });
  await c.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: ac[0], y: ac[1] }] });
  await p.waitForTimeout(60); r.active60 = await w('#oa'); await p.waitForTimeout(300); r.active360 = await w('#oa');
  await c.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  console.log(JSON.stringify(r)); await b.close();
})();
