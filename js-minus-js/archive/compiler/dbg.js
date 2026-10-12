const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 });
  const props = process.argv[3].split(',');
  const r = await p.evaluate(([props, n]) => { const out = []; let i = 0;
    for (const e of document.querySelectorAll('#cc div')) { if (i++ >= n) break; const cs = getComputedStyle(e);
      out.push(e.className + ' ' + e.getAttribute('style') + ' | ' + props.map(x => x + '=' + cs.getPropertyValue(x)).join(' ')); }
    return out; }, [props, +(process.argv[4] || 20)]);
  console.log(r.join('\n')); await b.close(); })();
