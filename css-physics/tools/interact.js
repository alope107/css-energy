// mouse + touch grab checks on a PLAIN single-engine page: grab the top of the stack (body 3), drag, read its position
const {launch,fileUrl,arena}=require('./lib/physics');
(async()=>{const b=await launch();
const f=process.argv[2];
const pos=p=>p.evaluate(()=>{const c=getComputedStyle(document.getElementById('LS'));return ['X3','Y3','Z3','GI'].map(k=>(+c.getPropertyValue('--'+k)).toFixed(1)).join(',')});
for(const mode of ['mouse','touch']){
 const ctx=mode=='mouse'?await b.newContext({viewport:{width:1000,height:900}}):await b.newContext({viewport:{width:412,height:900},hasTouch:true,isMobile:true,deviceScaleFactor:2.625});
 const p=await ctx.newPage();await p.goto(fileUrl(f));
 if(mode=='mouse')await p.click('label[for=sc-stack]');else await p.locator('label[for=sc-stack]').tap();
 await p.waitForTimeout(2500);
 const {ar,proj}=await arena(p);
 const before=await pos(p);const [px,py]=proj([-60,-145,0]);
 if(mode=='mouse'){await p.mouse.move(px,py);await p.mouse.down();await p.waitForTimeout(200);await p.mouse.move(px+200,py-60,{steps:12});await p.waitForTimeout(1200);
  const during=await pos(p);await p.screenshot({path:'ix_mouse.png',clip:{x:ar.x,y:ar.y,width:ar.width,height:ar.height}});await p.mouse.up();await p.waitForTimeout(1500);
  console.log(mode,'before',before,'during',during,'after',await pos(p))}
 else{await p.touchscreen.tap(px,py);await p.waitForTimeout(400);
  for(let k=1;k<=12;k++){await p.evaluate(()=>{const t=document.querySelector('.tl');t.scrollLeft-=8;t.scrollTop+=4});await p.waitForTimeout(50)}
  await p.waitForTimeout(800);const during=await pos(p);await p.screenshot({path:'ix_touch.png',clip:{x:ar.x,y:ar.y,width:ar.width,height:ar.height}});
  await p.touchscreen.tap(ar.x+ar.width-20,ar.y+20);await p.waitForTimeout(1500);console.log(mode,'before',before,'during',during,'after',await pos(p))}
 await ctx.close()}
await b.close()})();
