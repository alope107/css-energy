// node tools/touchcheck.js page.html : touch dragging on a phone-sized touch screen (PLAIN single-engine page; exit 1 on failure)
// Real touch gestures (CDP Input.dispatchTouchEvent goes through Chromium's gesture recognizer: touch slop, scroll
// latching, axis locking, flings, as on a phone), not scripted scrolls. ARCHITECTURE.md "Touch" has the mechanism.
//   drag      touch a body's centre, drag, hold: that body is held (GI) and follows the finger; let go: dropped
//             within a few frames, and it falls
//   quick     the same with no pause between touching and moving (no :hover ever arrives on a quick drag)
//   axis      a drag that starts nearly horizontal and then goes up: followed in both axes (no axis lock)
//   fling     let go while moving fast: dropped within 250 ms
//   tap       a tap on a body grabs nothing
//   empty     a drag where there is no body grabs nothing and scrolls the page
//   drag-box, drag-sphere, corner   the drag check on the lowest reachable box and sphere, and in the corner view
// TOUCHCHECK_SHOT=out.png saves the arena mid-drag.
const {launch,fileUrl,bodyInfo,projector}=require('./lib/physics');const fs=require('fs');
const f=process.argv[2];const info=bodyInfo(fs.readFileSync(f,'utf8'));const N=info.length;
const VIEW={viewport:{width:412,height:915},deviceScaleFactor:2.625,isMobile:true,hasTouch:true};
(async()=>{const b=await launch();let fails=[];const note=(ok,msg)=>{console.log((ok?'ok   ':'FAIL ')+msg);if(!ok)fails.push(msg)};
const fresh=async()=>{const ctx=await b.newContext(VIEW);const p=await ctx.newPage();await p.goto(fileUrl(f));
 const c=await ctx.newCDPSession(p);
 // in-page log, one entry per frame: time, GI, att, and every body's position
 await p.evaluate(N=>{window.TL=[];window.EV=[];const ls=document.getElementById('LS'),ti=document.getElementById('TI');
  for(const e of ['touchstart','touchend'])addEventListener(e,()=>EV.push([e,performance.now()]),true);
  (function fr(){const s=getComputedStyle(ls),t=getComputedStyle(ti);const g=n=>+s.getPropertyValue('--'+n);
   TL.push({t:performance.now(),GI:Math.round(g('GI')),att:+t.getPropertyValue('--att'),held:+t.getPropertyValue('--held'),
    B:Array.from({length:N},(_,i)=>[g('X'+i),g('Y'+i),g('Z'+i)])});if(TL.length>4000)TL.splice(0,2000);requestAnimationFrame(fr)})()},N);
 const T=(type,x,y)=>c.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y}]});
 return {ctx,p,T}};
// one gesture: touch at (x,y), wait pre ms, move by (dx,dy) along a path of `steps` 16 ms steps, wait post ms, lift
const gesture=async(p,T,x,y,path,pre,post,beforeLift)=>{await T('touchStart',x,y);await p.waitForTimeout(pre);let cx=x,cy=y;
 for(const [dx,dy] of path){cx=x+dx;cy=y+dy;await T('touchMove',cx,cy);await p.waitForTimeout(16)}
 await p.waitForTimeout(post);const mid=beforeLift&&await beforeLift();await T('touchEnd');return [cx,cy,mid]};
const line=(dx,dy,n)=>Array.from({length:n},(_,k)=>[dx*(k+1)/n,dy*(k+1)/n]);
const last=p=>p.evaluate(()=>TL[TL.length-1]);
// bodies whose handle is what a finger at their projected centre touches, front-most first
const targets=async(p,yaw=0.25)=>{const ar=await p.locator('.arena').boundingBox();const pj=projector(ar),proj=q=>pj(q,yaw);const s=await last(p);
 const hit=await p.evaluate(pts=>pts.map(([x,y])=>{const e=document.elementFromPoint(x,y);const h=e&&e.closest('.hd');return h?+h.id.replace(/\D/g,''):-1}),
  s.B.map(q=>proj(q)));
 return {ar,proj:pj,ks:s.B.map((q,i)=>i).filter(i=>hit[i]===i).sort((i,j)=>s.B[i][1]-s.B[j][1])}};
const settle=async p=>{for(let t=0;t<40;t++){const a=await last(p);await p.waitForTimeout(150);const c=await last(p);
 if(a.B.every((q,i)=>Math.hypot(q[0]-c.B[i][0],q[1]-c.B[i][1],q[2]-c.B[i][2])<0.05))return}};

{const {ctx,p}=await fresh();
 const tm=await p.evaluate(()=>[getComputedStyle(document.getElementById('app')).getPropertyValue('--tm').trim(),getComputedStyle(document.querySelector('.hd')).display]);
 note(tm[0]==='1'&&tm[1]==='block',`touch mode on a coarse pointer (--tm ${tm[0]}, handles ${tm[1]})`);await ctx.close()}

// drag, quick, axis, fling: each on a fresh page, on the top body of the stack; drag-box and drag-sphere: the lowest
// box and sphere that a finger can reach; corner: a drag in the corner camera view (yaw 0.85 instead of 0.25)
for(const kind of ['drag','quick','axis','fling','drag-box','drag-sphere','corner']){
 const {ctx,p,T}=await fresh();await p.locator('label[for=sc-stack]').tap();
 const yaw=kind==='corner'?0.85:0.25;if(kind==='corner'){await p.locator('label[for=v-b]').tap();await p.waitForTimeout(1500)}
 await p.waitForTimeout(500);await settle(p);
 const {ar,proj:pj,ks}=await targets(p,yaw);const proj=q=>pj(q,yaw);
 const pickK=kind==='drag-box'?ks.filter(i=>info[i].k==='box').pop():kind==='drag-sphere'?ks.filter(i=>info[i].k==='sph').pop():ks[0];
 if(pickK===undefined){note(false,`${kind}: no suitable body's handle is under its own centre`);await ctx.close();continue}
 const k=pickK;const s0=await last(p);const [x,y]=proj(s0.B[k]);
 const path=kind==='corner'?line(-100,30,14):kind==='drag-sphere'||kind==='drag-box'?line(40,-110,14):kind==='axis'?[...line(30,-3,6),...line(30,-3,6).map(([a,b_])=>[30+a/6,-3+b_*0-a*2.5])]:
  kind==='fling'?line(-40,-70,5):line(-50,-90,14);
 const pre=kind==='quick'||kind==='fling'?0:150,post=kind==='fling'?0:500;console.log(`     ${kind}: body ${k} (${info[k].k})`);
 const t0=await p.evaluate(()=>performance.now());
 const [fx,fy,mid]=await gesture(p,T,x,y,path,pre,post,async()=>{const m=await last(p);
  if(process.env.TOUCHCHECK_SHOT&&kind==='drag')await p.screenshot({path:process.env.TOUCHCHECK_SHOT,clip:ar});return m});
 await p.waitForTimeout(700);
 const {TL,EV}=await p.evaluate(()=>({TL,EV}));const tEnd=EV.filter(e=>e[0]==='touchend').pop()[1];
 const during=TL.filter(e=>e.t>t0&&e.t<tEnd);const heldK=during.filter(e=>e.GI===k+1).length,heldOther=during.filter(e=>e.GI&&e.GI!==k+1).length;
 const drop=TL.find(e=>e.t>tEnd&&e.GI===0);const dropMs=drop?drop.t-tEnd:Infinity;
 note(heldK>0&&!heldOther,`${kind}: body ${k} held while the finger is down (${heldK} frames; other bodies ${heldOther})`);
 note(dropMs<(kind==='fling'?250:70),`${kind}: dropped ${dropMs.toFixed(0)} ms after the finger lifted`);
 if(kind!=='fling'){
  // where the body is on screen vs the finger: off by about the touch slop (the drag starts after it), not more
  const [bx,by]=proj(mid.B[k]);const off=Math.hypot(bx-fx,by-fy);
  note(off<30,`${kind}: body ${k} is ${off.toFixed(1)} px from the finger (finger moved ${Math.hypot(fx-x,fy-y).toFixed(0)} px)`);
  const end=TL[TL.length-1];if(kind!=='corner')note(end.B[k][1]>mid.B[k][1]+5,`${kind}: body ${k} falls after the drop (y ${mid.B[k][1].toFixed(0)} -> ${end.B[k][1].toFixed(0)})`)}
 await ctx.close()}

// tap: nothing grabbed, nothing moves
{const {ctx,p,T}=await fresh();await p.locator('label[for=sc-stack]').tap();await p.waitForTimeout(500);await settle(p);
 const {proj,ks}=await targets(p);const k=ks[0];const s0=await last(p);const [x,y]=proj(s0.B[k]);const t0=await p.evaluate(()=>performance.now());
 await gesture(p,T,x,y,[],60,0);await p.waitForTimeout(500);
 const TL=await p.evaluate(()=>TL);const after=TL.filter(e=>e.t>t0);const s1=after[after.length-1];
 const moved=Math.max(...s1.B.map((q,i)=>Math.hypot(q[0]-s0.B[i][0],q[1]-s0.B[i][1],q[2]-s0.B[i][2])));
 note(!after.some(e=>e.GI)&&moved<1,`tap: nothing grabbed (max GI ${Math.max(...after.map(e=>e.GI))}), nothing moved (${moved.toFixed(2)})`);await ctx.close()}

// empty: a drag where no handle is grabs nothing and scrolls the page
{const {ctx,p,T}=await fresh();await p.waitForTimeout(500);const {ar}=await targets(p);
 const pts=[];for(let gx=0.05;gx<1;gx+=0.05)for(let gy=0.05;gy<0.5;gy+=0.05)pts.push([ar.x+gx*ar.width,ar.y+gy*ar.height]);
 const free=await p.evaluate(pts=>pts.find(([x,y])=>{const e=document.elementFromPoint(x,y);return e&&!e.closest('.hd')}),pts);
 const t0=await p.evaluate(()=>performance.now());const sy0=await p.evaluate(()=>scrollY);
 await gesture(p,T,free[0],free[1],line(0,-120,10),0,200);await p.waitForTimeout(400);
 const TL=await p.evaluate(()=>TL);const sy1=await p.evaluate(()=>scrollY);
 note(!TL.filter(e=>e.t>t0).some(e=>e.GI)&&sy1>sy0+50,`empty: nothing grabbed, the page scrolled ${sy1-sy0} px`);await ctx.close()}

await b.close();console.log(fails.length?`FAIL ${fails.length}`:'PASS');process.exit(fails.length?1:0)})();
