const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const fs = require('fs');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(1000);
  const src = fs.readFileSync('/tmp/prog2.js', 'utf8').replace(/\n$/, '');
  await p.click('#ed'); await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
  const lines = src.split('\n'); for (let i = 0; i < lines.length; i++) { if (i) await p.keyboard.press('Enter'); await p.keyboard.insertText(lines[i]); }
  const log = await p.evaluate(() => new Promise(res => { const out = []; document.getElementById('run').checked = true; const t0 = performance.now();
    const f = () => { const app = getComputedStyle(document.querySelector('#app')); const s = +app.getPropertyValue('--rbscan'); const pr = [...document.querySelectorAll('.probe')];
      const row = k => { const cells = pr[k].querySelectorAll('.row i'); return s > 0 ? getComputedStyle(cells[s - 1]).getPropertyValue('--lv') : '-'; };
      out.push(`${s}:${Math.round(pr[0].getBoundingClientRect().height)}/${row(0)},${Math.round(pr[1].getBoundingClientRect().height)}/${row(1)},${Math.round(pr[6].getBoundingClientRect().height)}/${row(6)}`);
      if (performance.now() - t0 < 2500) requestAnimationFrame(f); else res(out); }; requestAnimationFrame(f); }));
  console.log(log.join(' | ')); await b.close(); })();
