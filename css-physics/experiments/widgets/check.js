// Face widgets: do the controls on the moving faces take real clicks and typing, and do the wired ones reach the
// engine? Prints pass/fail per check; SHOT=dir saves screenshots.
//   node experiments/widgets/check.js out/widgets.html          (from css-physics/)
const {launch, fileUrl, arena} = require('../../tools/lib/physics');
const path = require('path');
const f = process.argv[2] || 'out/widgets.html';
const shot = process.env.SHOT;
let fails = 0;
const ok = (c, msg) => { console.log((c ? 'ok   ' : 'FAIL ') + msg); if (!c) fails++; };
(async () => {
  const b = await launch();
  const p = await b.newPage({viewport: {width: 1000, height: 900}});
  await p.goto(fileUrl(f));
  await p.waitForTimeout(2500);
  const {ar} = await arena(p);
  const snap = async name => shot && p.screenshot({path: path.join(shot, name + '.png'), clip: {x: ar.x, y: ar.y, width: ar.width, height: ar.height}});
  const app = k => p.evaluate(k => getComputedStyle(document.getElementById('app')).getPropertyValue(k).trim(), k);
  const yaw = () => p.evaluate(() => +getComputedStyle(document.querySelector('.ptr')).getPropertyValue('--yaw'));
  // the topmost element at an element's centre must be that element (or inside it): hit testing through the 3D faces
  const hit = sel => p.evaluate(sel => {
    const e = document.querySelector(sel), r = e.getBoundingClientRect();
    const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return {self: e.contains(t) || (e.labels && [...e.labels].some(l => l.contains(t))), top: t && (t.id || t.className || t.tagName)};
  }, sel);
  await snap('load');
  for (const sel of ['#wg-shake', '.wf textarea', '.wf video', '.wf .terms', '#wg-word', '.wd .boop']) {
    const h = await hit(sel);
    console.log(`     ${sel}: topmost at its centre is ${h.top}${h.self ? '' : ' (hidden behind something or facing away)'}`);
  }
  // the cube's SHAKE button: hold it, the scene wakes (kick)
  const g0 = await app('--gy');
  const btn = p.locator('#wg-shake');
  if ((await hit('#wg-shake')).self) {
    const bb = await btn.boundingBox();
    await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
    await p.mouse.down(); await p.waitForTimeout(150);
    ok(await app('--kick') === '1', 'SHAKE held: --kick is 1');
    await p.mouse.up(); await p.waitForTimeout(80);
    ok(await app('--kick') === '0', 'SHAKE released: --kick is 0');
    await p.waitForTimeout(600); await snap('shaken');
  } else console.log('skip SHAKE: not facing the camera');
  // the magic word, typed into the brick's front face
  await p.waitForTimeout(2500);
  if ((await hit('#wg-word')).self) {
    await p.locator('#wg-word').click();
    await p.keyboard.type('float', {delay: 40});
    ok(await app('--gy') === '0', `typed "float": --gy ${g0} -> ${await app('--gy')}`);
    await p.waitForTimeout(1200); await snap('float');
    await p.keyboard.press('Backspace');
    ok(await app('--gy') === g0, `deleted a letter: --gy back to ${await app('--gy')}`);
  } else console.log('skip magic word: not facing the camera');
  // the textarea on the brick's back, the book's terms: they take typing wherever they are (focus, not position)
  await p.locator('.wf textarea').focus(); await p.keyboard.type('hi');
  ok(await p.locator('.wf textarea').inputValue() === 'hi', 'textarea takes typing');
  // the camera select on the cube's right side (selectOption doesn't need it to face us)
  const y0 = await yaw();
  await p.selectOption('#wg-cam', 'c'); await p.waitForTimeout(1200);
  ok(Math.abs(await yaw() - 1.45) < 1e-3, `camera select "side": yaw ${y0} -> ${(await yaw()).toFixed(3)}`);
  await snap('side');
  // the video plays
  const vt = await p.evaluate(() => { const v = document.querySelector('.wf video'); return v ? [v.readyState, v.currentTime, v.paused] : null; });
  ok(vt && vt[0] >= 2 && !vt[2], `video readyState ${vt && vt[0]}, t ${vt && vt[1].toFixed(2)} s, paused ${vt && vt[2]}`);
  await b.close();
  console.log(fails ? `${fails} failed` : 'all passed');
  process.exit(fails ? 1 : 0);
})();
