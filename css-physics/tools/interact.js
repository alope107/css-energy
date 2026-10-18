// mouse + touch grab checks on a PLAIN single-engine page: grab the top of the stack (body 3), drag, read its position
// (the touch checks proper are tools/touchcheck.js)
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
 else{// a real touch drag (through Chromium's gesture recognizer): touch the body, drag, hold, lift
  const c=await ctx.newCDPSession(p);const T=(type,x,y)=>c.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y}]});
  await T('touchStart',px,py);for(let k=1;k<=12;k++){await T('touchMove',px-8*k,py+4*k);await p.waitForTimeout(16)}
  await p.waitForTimeout(800);const during=await pos(p);await p.screenshot({path:'ix_touch.png',clip:{x:ar.x,y:ar.y,width:ar.width,height:ar.height}});
  await T('touchEnd');await p.waitForTimeout(1500);console.log(mode,'before',before,'during',during,'after',await pos(p))}
 await ctx.close()}
await b.close()})();
