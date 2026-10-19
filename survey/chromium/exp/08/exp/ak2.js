const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.setContent('<details id=d><summary accesskey=e id=s>sum</summary>x</details><details id=d2><summary id=s2>two</summary>y</details>');
  const c = await p.context().newCDPSession(p);
  const key = async (k, mod) => { const vk = k.toUpperCase().charCodeAt(0);
    await c.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: mod, key: k, code: 'Key' + k.toUpperCase(), windowsVirtualKeyCode: vk });
    await c.send('Input.dispatchKeyEvent', { type: 'char', modifiers: mod, key: k, text: k, unmodifiedText: k, windowsVirtualKeyCode: vk });
    await c.send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: mod, key: k, windowsVirtualKeyCode: vk }); await p.waitForTimeout(50); };
  const ev = []; await p.exposeFunction('log', s => ev.push(s));
  await p.evaluate(() => { for (const t of ['mousedown','mouseup','click','DOMActivate','toggle']) document.addEventListener(t, e => log(t + ':' + e.target.id), true); });
  await key('e', 1); const r1 = await p.evaluate(() => d.open);
  await p.click('#s2'); const r2 = await p.evaluate(() => d2.open);
  await p.evaluate(() => s.click()); await p.waitForTimeout(50); const r3 = await p.evaluate(() => d.open);
  console.log(JSON.stringify({ accesskey: r1, mouse: r2, scriptClick: r3, ev }));
  await b.close();
})();
