// node tools/sparse.js page.html N [bodyIndex] : the sparse regime (a mostly sleeping scene with one body being dragged).
// Prints: asleep count after load, idle style ms per pass, then while dragging body k in a circle for 3 s: fps, median
// style pass ms, awake count at the end; then the time until everything sleeps again after release.
const {chromium}=require('playwright');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const f=process.argv[2],N=+process.argv[3];let K=+(process.argv[4]||0);
const p=await b.newPage({viewport:{width:1000,height:900}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);
await p.waitForTimeout(+(process.env.WAIT||2000));
const st=()=>p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));let a=0;for(let i=0;i<N;i++)if(+c.getPropertyValue('--SC'+i)>45)a++;return a},N);
const pos=i=>p.evaluate(i=>{const c=getComputedStyle(document.getElementById('LS'));return ['X','Y','Z'].map(k=>+c.getPropertyValue('--'+k+i))},i);
const cdp=await p.context().newCDPSession(p);
async function trace(ms,act){const ev=[];const h=d=>ev.push(...d.value);cdp.on('Tracing.dataCollected',h);
 await cdp.send('Tracing.start',{categories:'devtools.timeline',transferMode:'ReportEvents'});
 const t0=Date.now();const fr=p.evaluate(d=>new Promise(r=>{let n=0;const t=performance.now();(function g(){n++;if(performance.now()-t<d)requestAnimationFrame(g);else r(n)})()}),ms);
 if(act)await act(t0);const n=await fr;
 const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;cdp.off('Tracing.dataCollected',h);
 const u=[];for(const e of ev)if(e.ph==='X'&&e.name==='UpdateLayoutTree')u.push(e.dur/1000);u.sort((a,b)=>a-b);
 const big=u.filter(x=>x>Math.max(0.5,u[u.length-1]*0.3));
 return {fps:(n*1000/ms).toFixed(0),med:(u[u.length>>1]||0).toFixed(2),bigmed:(big[big.length>>1]||0).toFixed(2),passes:u.length,sum:(u.reduce((a,b)=>a+b,0)/ms).toFixed(2)}}
const asleep0=await st();
const idle=await trace(1500);
const ar=await p.locator('.arena').boundingBox();const sc=ar.width/VW;
const proj=([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
 const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,k=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*k*sc, ar.y+ar.height/2+y3*k*sc]};
if(process.argv[4]==='c'){K=await p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));let best=0,bd=1e9;for(let i=0;i<N;i++){const d=Math.abs(+c.getPropertyValue('--X'+i))+Math.abs(+c.getPropertyValue('--Z'+i));if(d<bd){bd=d;best=i}}return best},N)}   // 'c': the body nearest the tray centre (always in view)
const [bx,by]=proj(await pos(K));await p.mouse.move(bx,by);await p.mouse.down();
const held=await p.evaluate(()=>getComputedStyle(document.getElementById('LS')).getPropertyValue('--GI'));
const drag=await trace(3000,async()=>{let k=0;const t=Date.now();while(Date.now()-t<3000){await p.mouse.move(bx+90*Math.sin(k/9),by-50-40*Math.cos(k/6));k++;await p.waitForTimeout(16)}});
const awakeEnd=N-await st();
await p.mouse.up();
let settle=-1;for(let i=0;i<60;i++){await p.waitForTimeout(500);if(await st()===N){settle=(i+1)*0.5;break}}
console.log(f.padEnd(22),`body ${K} asleep ${asleep0}/${N} held ${(+held).toFixed(0)} | idle med ${idle.med} ms (${idle.sum} ms/ms) fps ${idle.fps} | drag fps ${drag.fps} med ${drag.med} bigmed ${drag.bigmed} passes ${drag.passes} awake ${awakeEnd} | settle ${settle} s`);
await b.close()})();
