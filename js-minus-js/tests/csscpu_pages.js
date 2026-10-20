// csscpu_pages.js dir [name...] — level C2 driver (harness script): each CSS CPU page that tests/csscpu_pages.py built
// in dir runs from load until --halt is 1 (polled every 50 ms; 60 s at most); its console must be Node's output and its
// step count cc_ref's. SHARDS=N runs N browsers at once, each taking the next page as it finishes one; the lines print
// in list order. The verdicts don't depend on it; the ms column does (the default, 1, for timing).
const path = require('path'), fs = require('fs');
const { launch, fileUrl } = require(path.join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText } = require(path.join(__dirname, '..', 'tools', 'page.js'));
(async () => {
  const dir = path.resolve(process.argv[2]); const only = process.argv.slice(3);
  const names = fs.readFileSync(path.join(dir, 'list.txt'), 'utf8').split('\n').filter(n => n && (!only.length || only.includes(n)));
  const shards = Math.max(1, Math.min(+(process.env.SHARDS || 1), names.length));
  const lines = []; let printed = 0, next = 0, pass = 0; const fails = [];
  const flush = () => { while (printed < names.length && lines[printed] !== undefined) console.log(lines[printed++]); };
  // the console as the page shows it: Node's output laid out on the grid (8 columns, 16 rows, wrapping, newlines)
  const grid = (text, cols, rows) => { const cells = new Array(cols * rows).fill(32); let p = 0;
    for (const ch of text) { if (ch === '\n') p = (Math.floor(p / cols) + 1) * cols % (cols * rows); else { cells[p] = ch.charCodeAt(0); p = (p + 1) % (cols * rows); } }
    return gridText(cells, rows, cols); };
  async function shard() {
    const b = await launch({});
    for (let i; (i = next++) < names.length;) {
      const name = names[i], im = JSON.parse(fs.readFileSync(path.join(dir, name + '.json'), 'utf8'));
      const p = await b.newPage({ viewport: { width: 1200, height: 800 } }); const t0 = Date.now();
      await p.goto(fileUrl(path.join(dir, name + '.html')), { timeout: 120000 });
      let r = { halted: false, steps: 0 };
      while (Date.now() - t0 < +(process.env.MAXMS || 60000) && !r.halted) {
        await p.waitForTimeout(50);
        r = await p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu')); return { halted: +cs.getPropertyValue('--halt') === 1, steps: +cs.getPropertyValue('--steps') }; });
      }
      const ms = Date.now() - t0;
      const got = gridText(await consoleCodes(p), im.rows, im.cols), want = grid(im.expected, im.cols, im.rows);
      await p.close();
      const good = r.halted && got === want && r.steps === im.steps;
      if (good) pass++; else fails.push(name);
      lines[i] = `${good ? 'ok  ' : 'FAIL'} ${name.padEnd(22)} ${String(ms).padStart(6)} ms  steps ${r.steps}${r.steps === im.steps ? '' : ' (want ' + im.steps + ')'}` +
        (r.halted ? '' : '  no HALT') + (got === want ? '' : `  console ${JSON.stringify(got.slice(0, 40))} want ${JSON.stringify(want.slice(0, 40))}`);
      flush();
    }
    await b.close();
  }
  await Promise.all(Array.from({ length: shards }, shard));
  fails.sort((a, b) => names.indexOf(a) - names.indexOf(b));
  console.log(`${pass}/${names.length} pass` + (fails.length ? '  FAILED: ' + fails.join(' ') : ''));
})();
