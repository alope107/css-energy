// node tools/sparse.js page.html N [bodyIndex] : the sparse regime (a mostly sleeping scene with one body being dragged).
// Prints: asleep count after load, idle style ms per pass, then while dragging body k in a circle for 3 s: fps, median
// style pass ms, awake count at the end; then the time until everything sleeps again after release.
const {launch,open,arena,record,countFrames,durations,median,bigmed}=require('./lib/physics');
(async()=>{const b=await launch();
const f=process.argv[2],N=+process.argv[3];let K=+(process.argv[4]||0);
const p=await open(b,f,{viewport:{width:1000,height:900}});
await p.waitForTimeout(+(process.env.WAIT||2000));
const st=()=>p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));let a=0;for(let i=0;i<N;i++)if(+c.getPropertyValue('--SC'+i)>45)a++;return a},N);
const pos=i=>p.evaluate(i=>{const c=getComputedStyle(document.getElementById('LS'));return ['X','Y','Z'].map(k=>+c.getPropertyValue('--'+k+i))},i);
async function trace(ms,act){const {events:ev,result:n}=await record(p,{},async()=>{const t0=Date.now();const fr=countFrames(p,ms);if(act)await act(t0);return fr});
 const u=durations(ev,'UpdateLayoutTree').sort((a,b)=>a-b);
 return {fps:(n*1000/ms).toFixed(0),med:median(u).toFixed(2),bigmed:bigmed(u,0.5).toFixed(2),passes:u.length,sum:(u.reduce((a,b)=>a+b,0)/ms).toFixed(2)}}
const asleep0=await st();
const idle=await trace(1500);
const {proj}=await arena(p);
if(process.argv[4]==='c'){K=await p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));let best=0,bd=1e9;for(let i=0;i<N;i++){const d=Math.abs(+c.getPropertyValue('--X'+i))+Math.abs(+c.getPropertyValue('--Z'+i));if(d<bd){bd=d;best=i}}return best},N)}   // 'c': the body nearest the tray centre (always in view)
const [bx,by]=proj(await pos(K));await p.mouse.move(bx,by);await p.mouse.down();
const held=await p.evaluate(()=>getComputedStyle(document.getElementById('LS')).getPropertyValue('--GI'));
const drag=await trace(3000,async()=>{let k=0;const t=Date.now();while(Date.now()-t<3000){await p.mouse.move(bx+90*Math.sin(k/9),by-50-40*Math.cos(k/6));k++;await p.waitForTimeout(16)}});
const awakeEnd=N-await st();
await p.mouse.up();
let settle=-1;for(let i=0;i<60;i++){await p.waitForTimeout(500);if(await st()===N){settle=(i+1)*0.5;break}}
console.log(f.padEnd(22),`body ${K} asleep ${asleep0}/${N} held ${(+held).toFixed(0)} | idle med ${idle.med} ms (${idle.sum} ms/ms) fps ${idle.fps} | drag fps ${drag.fps} med ${drag.med} bigmed ${drag.bigmed} passes ${drag.passes} awake ${awakeEnd} | settle ${settle} s`);
await b.close()})();
