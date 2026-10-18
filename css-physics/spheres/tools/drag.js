// node spheres/tools/drag.js page.html [settle_ms=3000] [drag_ms=3000] [scene]
// The interactive regime: let the scene settle (or pick a scene: field loads at rest), then grab the sphere nearest the
// tray centre and drag it in a circle through the others. Prints the frame rate and the style passes while settled and
// while dragging, how many spheres the drag moved, and whether the grabbed sphere followed the pointer.
const {launch,open,record,countFrames,durations,median,bigmed,arena,saveTrace}=require('../../tools/lib/physics');
const [page,SETTLE='3000',DRAG='3000',SCENE]=process.argv.slice(2);
const state=p=>p.evaluate(()=>{const cs=getComputedStyle(document.querySelector('[id$=LC]'));const N=document.querySelectorAll('.bw').length;
 const g=n=>parseFloat(cs.getPropertyValue('--'+n));const o=[];for(let s=0;s<N;s++)o.push([g('X'+s),g('Y'+s),g('Z'+s),g('T'+s)]);return o});
(async()=>{const b=await launch();const p=await open(b,page,{viewport:{width:1000,height:900}});
if(SCENE){const l=p.locator(`#lb-${SCENE}`);const bb=await l.boundingBox();await p.mouse.move(bb.x+bb.width/2,bb.y+bb.height/2);
 await p.mouse.down();await p.waitForTimeout(150);await p.mouse.up();}
await p.waitForTimeout(+SETTLE);
const {proj}=await arena(p);
const s0=await state(p);
const idle=await record(p,{},()=>countFrames(p,1000));
// the sphere nearest the tray centre (in x/z), on top
let best=0;s0.forEach((q,i)=>{if(Math.hypot(q[0],q[2])-q[1]*0.01<Math.hypot(s0[best][0],s0[best][2])-s0[best][1]*0.01)best=i});
const [cx,cy]=proj(s0[best].slice(0,3));
await p.mouse.move(cx,cy);await p.mouse.down();
const R=60,dur=+DRAG,t0=Date.now();
const mover=(async()=>{while(Date.now()-t0<dur){const a=(Date.now()-t0)/dur*2*Math.PI*1.5;
 await p.mouse.move(cx+R*Math.sin(a),cy-R*0.5+R*0.5*Math.cos(a));await p.waitForTimeout(16)}})();
const drag=await record(p,{},()=>countFrames(p,dur));await mover;if(process.env.TRACE)saveTrace(drag.events,process.env.TRACE);
const act=await p.evaluate(()=>{const e=document.querySelector('[id$=LA]');if(!e)return '';const cs=getComputedStyle(e);const N=document.querySelectorAll('.bw').length;
 const c={ac:0,in:0,pa:0,wr:0};for(let s=0;s<N;s++)for(const k in c)c[k]+=+cs.getPropertyValue('--'+k+s)||0;return JSON.stringify(c)});
const s1=await state(p);await p.mouse.up();
const held=s1.findIndex(q=>q[3]<0);
const moved=s1.filter((q,i)=>Math.hypot(q[0]-s0[i][0],q[1]-s0[i][1],q[2]-s0[i][2])>2).length;
const f=(r,d)=>{const u=durations(r.events,'UpdateLayoutTree').sort((a,b)=>a-b);return `fps ${(r.result/d*1000).toFixed(1)} style med ${median(u).toFixed(2)} bigmed ${bigmed(u,1).toFixed(2)} ms`};
console.log(`${page} N=${s0.length}`);
console.log(`  settled: ${f(idle,1000)}`);
console.log(`  drag:    ${f(drag,dur)} | grabbed slot sphere type ${s0[best][3]}, held at end: ${held>=0?'yes':'no'} | spheres moved >2px: ${moved} | slots ${act}`);
await b.close()})();
