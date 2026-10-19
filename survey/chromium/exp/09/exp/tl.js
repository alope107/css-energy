const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const P = '@property --o{syntax:"<number>";inherits:false;initial-value:-1}';
const sc = (name, top) => `<div style="height:100px;overflow:hidden;position:relative"><div style="position:absolute;top:${top}px;height:10px;width:10px;view-timeline:${name} block"></div><div style="height:1000px"></div></div>`;
const css = P + '@keyframes k{from{--o:0}to{--o:100}}i{display:block;animation:k 1000s linear both;animation-timeline:--nowhere}';
const pages = {
  // a name declared outside the reader's ancestors, no timeline-scope: inactive today; active with global names
  global: `<style>${css}</style><div>${sc('--g', 50)}</div><i id=r style="animation-timeline:--g"></i>`,
  // same, hoisted with timeline-scope on a common ancestor: active today (control)
  scoped: `<style>${css}</style><div style="timeline-scope:--s"><div>${sc('--s', 50)}</div><i id=r style="animation-timeline:--s"></i></div>`,
  // two timelines with the same name under one scope: unresolved (inactive) today; last in tree order once the clash rule ships
  clash: `<style>${css}</style><div style="timeline-scope:--c"><div>${sc('--c', 20)}</div><div>${sc('--c', 80)}</div><i id=r style="animation-timeline:--c"></i></div>`,
  // timeline-scope: all (flag CSSTimelineScopeAll)
  all: `<style>${css}</style><div style="timeline-scope:all"><div>${sc('--a', 50)}</div><i id=r style="animation-timeline:--a"></i></div>`,
};
(async () => {
  for (const f of ['', 'CSSTimelineScopeAll']) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(f ? ['--enable-blink-features=' + f] : [])] });
    const out = [];
    for (const [k, h] of Object.entries(pages)) {
      const p = await b.newPage(); await p.setContent('<!doctype html><body style="margin:0">' + h); await p.waitForTimeout(200);
      out.push(`${k}=${await p.evaluate(() => getComputedStyle(r).getPropertyValue('--o'))}`); await p.close();
    }
    console.log(f || 'none', out.join(' ')); await b.close();
  }
})();
