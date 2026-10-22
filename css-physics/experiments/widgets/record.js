// The TV's video: records the page itself (the "drop" scene) and writes experiments/widgets/tv.webm, the arena cropped
// to 320x200 VP9. Run it, rebuild, run it again: the TV then shows itself showing the scene.
//   node experiments/widgets/record.js out/widgets.html          (from css-physics/)
const {launch, fileUrl, arena} = require('../../tools/lib/physics');
const {execFileSync} = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const FFMPEG = process.env.FFMPEG || fs.readdirSync('/ms-playwright').filter(d => d.startsWith('ffmpeg-')).sort().map(d => `/ms-playwright/${d}/ffmpeg-linux`).pop();
const f = process.argv[2] || 'out/widgets.html';
const SECS = 8;
(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tv-'));
  const b = await launch();
  const ctx = await b.newContext({viewport: {width: 1000, height: 760}, recordVideo: {dir, size: {width: 1000, height: 760}}});
  const p = await ctx.newPage();
  const t0 = Date.now();
  await p.goto(fileUrl(f));
  await p.waitForTimeout(1500);
  const {ar} = await arena(p);
  const lb = await p.locator('label[for=sc-drop]').boundingBox();
  await p.mouse.move(lb.x + lb.width / 2, lb.y + lb.height / 2);
  const start = (Date.now() - t0) / 1000;
  await p.mouse.down(); await p.waitForTimeout(200); await p.mouse.up();   // a real press: the scene resets
  await p.waitForTimeout(SECS * 1000);
  const video = p.video();
  await ctx.close(); await b.close();
  const src = await video.path();
  const crop = [ar.width, ar.height, ar.x, ar.y].map(v => Math.round(v) & ~1).join(':');
  const out = path.join(__dirname, 'tv.webm');
  execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-ss', String(start), '-t', String(SECS), '-i', src,
    '-vf', `crop=${crop},scale=320:200`, '-an', '-c:v', 'libvpx-vp9', '-b:v', '250k', '-deadline', 'good', '-cpu-used', '4', out]);
  fs.rmSync(dir, {recursive: true});
  console.log(`${out}: ${(fs.statSync(out).size / 1024).toFixed(0)} KB, ${SECS} s from ${start.toFixed(2)} s`);
})();
