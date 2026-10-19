const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/ak.html');
  const c = await p.context().newCDPSession(p);
  const key = async (k, mod) => {
    const code = 'Key' + k.toUpperCase(), vk = k.toUpperCase().charCodeAt(0);
    await c.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: mod, key: k, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    await c.send('Input.dispatchKeyEvent', { type: 'char', modifiers: mod, key: k, code, text: k, unmodifiedText: k, windowsVirtualKeyCode: vk });
    await c.send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: mod, key: k, code, windowsVirtualKeyCode: vk });
    await p.waitForTimeout(50);
  };
  const w = s => p.$eval(s, e => e.getBoundingClientRect().width);
  const r = {};
  for (const k of ['e','p']) await key(k, 1);
  r.open = await p.evaluate(() => document.querySelector('details').open); r.after = [await w('#oh'), await w('#ov'), await w('#x'), await w('#od'), await p.$eval('#p', e => e.matches(':popover-open')), await p.evaluate(() => location.hash)];
  console.log(JSON.stringify(r));
  await b.close();
})();
