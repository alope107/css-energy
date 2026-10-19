const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  for (const flags of [[], ['--enable-experimental-web-platform-features']]) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...flags] });
    const p = await b.newPage();
    await p.setContent('<div id=d></div>');
    const r = await p.evaluate(() => {
      const cs = getComputedStyle(document.body);
      const props = [...cs].filter(n => /trigger/.test(n));
      const sup = {};
      for (const [prop, val] of [
        ['animation-trigger', '--t play-forwards play-backwards'],
        ['animation-trigger', '--t play'],
        ['animation-trigger', '--t play-alternate'],
        ['animation-trigger', '--t play-pause'],
        ['animation-trigger', '--t replay reset'],
        ['animation-trigger', 'once view() contain'],
        ['timeline-trigger', '--t view() contain 0% contain 100%'],
        ['timeline-trigger', '--t view() contain 0% contain 100% / cover 0% cover 100%'],
        ['timeline-trigger', '--t view() entry 100% / auto'],
        ['timeline-trigger-name', '--t'],
        ['timeline-trigger-source', 'view()'],
        ['timeline-trigger-range', 'contain'],
        ['timeline-trigger-activation-range', 'contain'],
        ['timeline-trigger-active-range', 'contain'],
        ['timeline-trigger-exit-range', 'contain'],
        ['trigger-scope', 'all'],
        ['trigger-scope', '--t'],
        ['event-trigger', '--e click'],
        ['event-trigger-name', '--e'],
        ['event-trigger-source', 'click'],
      ]) sup[prop + ': ' + val] = CSS.supports(prop, val);
      const ifaces = ['AnimationTrigger', 'TimelineTrigger', 'EventTrigger', 'TimelineTriggerRange'].filter(n => n in window);
      return { props, sup, ifaces };
    });
    console.log(JSON.stringify(flags), JSON.stringify(r, null, 1));
    await b.close();
  }
})();
