// feasible.js — pass/fail checks for storage and addressing primitives the RAM catalog (README.md) lists. Harness only.
//   ident     a registered <custom-ident> = ident("--c" var(--k)) names the anchor anchor-size() reads (flag CSSIdentFunction)
//   twoword   a content-visibility: hidden leaf remembers width and height separately: two words per leaf
//   snap      a scroll offset as a cell: written by turning snapping on with the one snap area at the value, held with
//             snapping off while the area moves, read back through a scroll timeline
const B = require('/workspaces/css-energy/shared/js/browser.js').profile('fontcpu');
const frames = (p, n) => p.evaluate(n => new Promise(r => { const f = k => k ? requestAnimationFrame(() => f(k - 1)) : r(); f(n); }), n);
(async () => {
  const b = await B.launch({ extraArgs: ['--enable-blink-features=CSSIdentFunction'] });
  let p = await b.newPage();
  // ident
  await p.setContent(`<!doctype html><style>@property --k{syntax:"<integer>";inherits:false;initial-value:0}
    @property --n{syntax:"<custom-ident>";inherits:false;initial-value:--x}
    ${[...Array(64)].map((_, i) => `#a${i}{anchor-name:--c${i};width:${i * 3 + 1}px;height:1px}`).join('')}
    #r{--n:ident("--c" var(--k));position:absolute;width:anchor-size(var(--n) width,0px);height:1px}</style>
    ${[...Array(64)].map((_, i) => `<div id=a${i}></div>`).join('')}<div id=r></div>`);
  const id = await p.evaluate(() => { const r = document.getElementById('r'); let ok = 0;
    for (let k = 0; k < 64; k++) { r.style.setProperty('--k', k); if (r.getBoundingClientRect().width === k * 3 + 1) ok++; } return ok; });
  console.log(JSON.stringify({ check: 'ident', ok: id, of: 64 }));
  // twoword: write (visible, sized), then hide (c-v hidden, contain-intrinsic-size: auto) and read both axes after frames
  await p.setContent(`<!doctype html><style>.w{anchor-name:--w;width:max-content}
    .c{display:block;contain-intrinsic-size:auto 1px auto 1px;content-visibility:hidden}
    .c.on{content-visibility:visible;width:var(--x);height:var(--y)}
    #r{position:absolute;top:100px;width:anchor-size(--w width,0px);height:anchor-size(--w height,0px)}</style>
    <div class=w><i class=c id=c></i></div><div id=r></div>`);
  const tw = [];
  for (const [x, y] of [[1048575, 777], [12345, 1048000], [3, 5]]) {
    await p.evaluate(([x, y]) => { const c = document.getElementById('c'); c.style.setProperty('--x', x + 'px'); c.style.setProperty('--y', y + 'px'); c.classList.add('on'); }, [x, y]);
    await frames(p, 2);
    await p.evaluate(() => document.getElementById('c').classList.remove('on')); await frames(p, 2);
    tw.push(await p.evaluate(([x, y]) => { const r = document.getElementById('r').getBoundingClientRect(); return r.width === x && r.height === y; }, [x, y]));
  }
  console.log(JSON.stringify({ check: 'twoword', results: tw }));
  // snap
  await p.setContent(`<!doctype html><style>
    @property --rd{syntax:"<integer>";inherits:false;initial-value:0}
    @keyframes rd{from{--rd:0}to{--rd:100000}}
    #s{width:50px;height:50px;overflow:hidden;scroll-timeline:--st y;position:relative}
    #s.on{scroll-snap-type:y mandatory}
    #t{height:100050px;width:1px}
    #a{position:absolute;left:0;top:var(--v);width:1px;height:1px;scroll-snap-align:start}
    #o{animation:rd linear both;animation-timeline:--st;animation-duration:auto}
    body{timeline-scope:--st}</style>
    <div id=s><div id=t></div><div id=a></div></div><div id=o></div>`);
  const rd = () => p.evaluate(() => [getComputedStyle(document.getElementById('o')).getPropertyValue('--rd'), document.getElementById('s').scrollTop]);
  const set = (v, on) => p.evaluate(([v, on]) => { const a = document.getElementById('a'); a.style.setProperty('--v', v + 'px'); document.getElementById('s').classList.toggle('on', on); }, [v, on]);
  const sn = [];
  await set(1234, true); await frames(p, 3); sn.push(['write 1234', ...(await rd())]);
  await set(50000, false); await frames(p, 3); sn.push(['hold, area moved to 50000', ...(await rd())]);
  await set(777, true); await frames(p, 3); sn.push(['write 777', ...(await rd())]);
  await set(9, false); await frames(p, 3); sn.push(['hold, area moved to 9', ...(await rd())]);
  await p.evaluate(() => document.getElementById('s').style.display = 'none'); await frames(p, 2);
  await p.evaluate(() => document.getElementById('s').style.display = ''); await frames(p, 2); sn.push(['after display: none and back', ...(await rd())]);
  console.log(JSON.stringify({ check: 'snap', steps: sn }));
  await b.close();
})();
