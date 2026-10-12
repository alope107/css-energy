const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 });
  console.log(await p.evaluate((an) => { const out = [];
    for (const e of document.querySelectorAll('.ov')) { const cs = getComputedStyle(e); if (cs.anchorName === an) { const k = [...e.classList].find(c => /^k\d+$/.test(c)).slice(1);
      out.push('slot ' + k + ' l=' + cs.getPropertyValue('--q-o_l' + k) + ' w=' + cs.getPropertyValue('--q-o_w' + k) + ' ln=' + cs.getPropertyValue('--ln')); } }
    for (const e of document.querySelectorAll('.lp')) { const cs = getComputedStyle(e); if (cs.display !== 'none') out.push('lab ' + cs.anchorName + ' ' + e.getBoundingClientRect().width); }
    return out.join('\n'); }, process.argv[3]));
  await b.close(); })();
