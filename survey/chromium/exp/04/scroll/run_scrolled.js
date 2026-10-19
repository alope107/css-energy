const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
const raf=p=>p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  await p.goto('file://'+__dirname+'/scrolled.html');await raf(p);
  const st=()=>p.evaluate(()=>document.getElementById('s').scrollLeft+':'+getComputedStyle(document.getElementById('c')).color);
  const r=['init '+await st()];
  await p.mouse.click(520,40);await p.waitForTimeout(300);await raf(p);r.push('btnRight '+await st());
  await p.mouse.click(580,40);await p.waitForTimeout(300);await raf(p);r.push('btnLeft '+await st());
  await p.focus('#s');await p.keyboard.press('ArrowRight');await p.waitForTimeout(300);await raf(p);r.push('keyRight '+await st());
  await p.keyboard.press('ArrowLeft');await p.waitForTimeout(300);await raf(p);r.push('keyLeft '+await st());
  await p.mouse.click(520,40);await p.waitForTimeout(300);await raf(p);r.push('btnRight '+await st());
  await p.mouse.move(100,130);await p.mouse.wheel(100,0);await p.waitForTimeout(400);await raf(p);r.push('wheelRight '+await st());
  console.log(r.join(' | '));
  await b.close();
})();
