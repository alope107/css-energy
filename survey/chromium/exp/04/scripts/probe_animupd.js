const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
const p=await b.newPage();await p.goto('file://'+process.argv[2]);await p.waitForTimeout(300);
const r=await p.evaluate(async()=>{const out=[];const c=document.querySelector('.c');let a0=c.getAnimations()[0];
for(let i=0;i<5;i++){await new Promise(r=>requestAnimationFrame(r));const a=c.getAnimations()[0];out.push([a===a0,a.effect.getTiming().delay.toFixed(1),getComputedStyle(c).animationDelay]);}return out});
console.log(JSON.stringify(r));await b.close()})();
