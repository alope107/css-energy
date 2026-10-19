const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 800, height: 900 } });
  await p.goto('file://' + __dirname + '/input.html');
  const w = sel => p.$eval(sel, e => e.getBoundingClientRect().width);
  const x = sel => p.$eval(sel, e => e.getBoundingClientRect().left);
  const raf = () => p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const out = {};
  // A
  out.A0 = await x('#ra');
  await p.focus('#r'); await p.keyboard.press('ArrowRight'); await p.keyboard.press('ArrowRight'); await raf();
  out.A1 = await x('#ra'); out.Aval = await p.$eval('#r', e => e.value);
  // drag the thumb with the mouse
  const rb = await p.$eval('#r', e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; });
  await p.mouse.move(rb[0] + rb[2] * 0.32, rb[1] + rb[3] / 2); await p.mouse.down(); await p.mouse.move(rb[0] + rb[2] * 0.8, rb[1] + rb[3] / 2, { steps: 5 });
  await raf(); out.Adrag = await x('#ra'); await p.mouse.up(); out.AvalDrag = await p.$eval('#r', e => e.value);
  // B
  out.B0 = await w('#outB');
  await p.focus('#sel'); await p.keyboard.type('q'); await raf(); out.B1 = await w('#outB');
  await p.waitForTimeout(1100); await p.keyboard.type('z'); await raf(); out.B2 = await w('#outB');
  // C
  out.C0 = [await w('#num'), await w('#outC1'), await w('#outC2')];
  await p.focus('#num'); await p.keyboard.press('ArrowUp'); await raf();
  out.C1 = [await w('#num'), await p.$eval('#num', e => e.value), await w('#outC1'), await w('#outC2')];
  await p.keyboard.press('ArrowUp'); await p.keyboard.press('ArrowUp'); await raf();
  out.C2 = [await w('#num'), await p.$eval('#num', e => e.value), await w('#outC1'), await w('#outC2')];
  await p.keyboard.type('1'); await raf();
  out.C3 = [await w('#num'), await p.$eval('#num', e => e.value), await w('#outC1'), await w('#outC2')];
  // D
  out.D0 = [await w('#outD'), await w('#outD2')];
  await p.focus('#pat'); await p.keyboard.type('ab'); await raf(); out.D1 = [await w('#outD'), await w('#outD2')];
  await p.keyboard.type('1'); await raf(); out.D2 = [await w('#outD'), await w('#outD2')];
  await p.keyboard.type('x'); await raf(); out.D3 = [await w('#outD'), await w('#outD2')];
  await p.focus('#txt'); await raf(); out.D4 = [await w('#outD'), await w('#outD2')];
  // E
  out.E0 = await w('#outE');
  await p.keyboard.press('Alt+k'); await raf(); out.E1 = await w('#outE');
  await p.keyboard.press('Alt+k'); await raf(); out.E2 = await w('#outE');
  // F
  await p.click('#sc'); out.F0 = await p.$eval('#sc', e => e.scrollTop);
  await p.keyboard.press('ArrowDown'); await p.waitForTimeout(400); out.F1 = await p.$eval('#sc', e => e.scrollTop);
  await p.keyboard.press('ArrowDown'); await p.waitForTimeout(400); out.F2 = await p.$eval('#sc', e => e.scrollTop);
  await p.keyboard.press('PageDown'); await p.waitForTimeout(400); out.F3 = await p.$eval('#sc', e => e.scrollTop);
  // G
  await p.focus('#g1'); out.G0 = await w('#outG');
  await p.keyboard.press('ArrowRight'); await p.keyboard.press('ArrowRight'); await raf(); out.G1 = await w('#outG');
  await p.keyboard.press('ArrowRight'); await raf(); out.G2 = await w('#outG');
  // txt width
  out.T0 = await w('#txt'); await p.focus('#txt'); await p.keyboard.type('abc'); await raf(); out.T1 = await w('#txt');
  await p.keyboard.type('defgh'); await raf(); out.T2 = await w('#txt');
  // I interestfor
  out.I0 = await w('#outI'); const ib = await p.$eval('#ib', e => { const r = e.getBoundingClientRect(); return [r.left + 3, r.top + 3]; });
  await p.mouse.move(ib[0], ib[1]); await p.waitForTimeout(200); out.I1 = await w('#outI'); await p.waitForTimeout(500); out.I2 = await w('#outI');
  out.Ipop = await p.$eval('#tip', e => e.matches(':popover-open'));
  await p.mouse.move(700, 800); await p.waitForTimeout(400); out.I3 = await w('#outI');
  // focusgroup
  await p.focus('#f0'); await p.keyboard.press('ArrowRight'); out.FG1 = await p.evaluate(() => document.activeElement.id);
  await p.keyboard.press('ArrowRight'); await p.keyboard.press('ArrowRight'); out.FG2 = await p.evaluate(() => document.activeElement.id);
  // customizable select
  out.CS0 = await p.$eval('#cs selectedcontent', e => [e.getBoundingClientRect().width, e.innerHTML]);
  await p.focus('#cs'); await p.keyboard.type('t'); await raf();
  out.CS1 = await p.$eval('#cs selectedcontent', e => [e.getBoundingClientRect().width, e.innerHTML, e.querySelector('span') && e.querySelector('span').getBoundingClientRect().width]);
  out.ver = b.version();
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();
