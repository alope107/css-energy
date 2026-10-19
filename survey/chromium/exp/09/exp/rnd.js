const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', '--enable-blink-features=CSSRandomFunction'] });
  const p = await b.newPage();
  await p.setContent(`<!doctype html><style>
  @property --r{syntax:"<number>";inherits:false;initial-value:0}@property --t{syntax:"<number>";inherits:true;initial-value:0}
  @property --q{syntax:"<number>";inherits:false;initial-value:0}
  @property --x{syntax:"<number>";inherits:false;initial-value:-1}@property --y{syntax:"<number>";inherits:false;initial-value:-1}
  @keyframes tick{from{--t:0}to{--t:1000}}
  #w{animation:tick 10s linear infinite}
  #a{--r:random(0, 1000);--q:calc(var(--t) * 0 + random(0, 1000))}
  </style><div id=w><i id=a></i></div>
  <style>@property --o1{syntax:"<number>";inherits:false;initial-value:-1}@property --o2{syntax:"<number>";inherits:false;initial-value:-1}</style>
  <i id=m1 style="--o1:1;--o2:2"></i>`);
  const rd = () => p.evaluate(() => [getComputedStyle(a).getPropertyValue('--r'), getComputedStyle(a).getPropertyValue('--q'), getComputedStyle(w).getPropertyValue('--t')]);
  const r0 = await rd(); await p.waitForTimeout(500); const r1 = await rd();
  console.log('random across frames (static, depends-on-animated):', r0, r1);
  // optional descriptors / multi-name @property in 153
  await p.setContent(`<!doctype html><style>@property --od{syntax:"<number>"}@property --m1, --m2{syntax:"<number>";inherits:false;initial-value:0}
  #x{--od:1.50;--m2:2.50;--plain:1.50}</style><i id=x></i>`);
  console.log('optional-descriptor registered?', await p.evaluate(() => getComputedStyle(x).getPropertyValue('--od')), 'multi-name registered?', await p.evaluate(() => getComputedStyle(x).getPropertyValue('--m2')), 'unregistered control', await p.evaluate(() => getComputedStyle(x).getPropertyValue('--plain')));
  await b.close();
})();
