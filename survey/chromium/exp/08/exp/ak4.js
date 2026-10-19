const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/' + process.argv[2]);
  const c = await p.context().newCDPSession(p);
  const ev = []; await p.exposeFunction('log', s => ev.push(s));
  await p.evaluate(() => { for (const t of ['click','DOMActivate','toggle','keydown','keypress']) document.addEventListener(t, e => log(t + ':' + (e.target.id || e.target.tagName)), true); });
  const k = 'e', vk = 69;
  await c.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: 1, key: k, code: 'KeyE', windowsVirtualKeyCode: vk });
  await c.send('Input.dispatchKeyEvent', { type: 'char', modifiers: 1, key: k, text: k, unmodifiedText: k, windowsVirtualKeyCode: vk });
  await c.send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: 1, key: k, windowsVirtualKeyCode: vk }); await p.waitForTimeout(100);
  console.log(JSON.stringify({ open: await p.evaluate(() => document.querySelector('details').open), ev }));
  await b.close();
})();
