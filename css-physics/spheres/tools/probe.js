// node spheres/tools/probe.js page.html [seconds=6] [shot.png]
// Every 0.5 s: the slots' state read from the page (positions X/Y/Z, previous U/V/W, type T on the readback element),
// with the physics checks: worst sphere overlap, overlaps outside the window (missed contacts), floor/wall
// penetration, slots out of x order, rms speed, frames per second. Exit 1 when a check fails (CHECK=1).
const {launch,open,countFrames}=require('../../tools/lib/physics');
const page=process.argv[2],SEC=+(process.argv[3]||6),SHOT=process.argv[4];
(async()=>{const b=await launch();const p=await open(b,page,{viewport:{width:1000,height:900}});
const N=await p.evaluate(()=>document.querySelectorAll('.eng[style],.eng').length&&[...document.querySelectorAll('.sp')].filter(e=>e.offsetParent!==null||getComputedStyle(e).display!=='none').length);
let fail=[];let worstOv=0,worstMiss=0,worstPen=0;
const K=+(process.env.K||0)||await p.evaluate(()=>{const m=document.querySelector('footer').textContent.match(/window of (\d+) slots/);return m?+m[1]:0});
const RATE=+(process.env.RATE||60);
for(let t=0;t<SEC*2;t++){
 const fr=await countFrames(p,500);
 const st=await p.evaluate(N=>{const e=document.querySelector('[id$=LC]')||document.getElementById('LC');const cs=getComputedStyle(e);
  const g=n=>parseFloat(cs.getPropertyValue('--'+n));const out=[];
  for(let s=0;s<N;s++)out.push([g('X'+s),g('Y'+s),g('Z'+s),g('U'+s),g('V'+s),g('W'+s),g('T'+s)]);return out},N);
 const RMIN=13,RMAX=17,NT=6,rad=T=>RMIN+(Math.abs(T)-1)*(RMAX-RMIN)/(NT-1);
 let ov=0,miss=0,pen=0,uns=0,ke=0,nov=0;
 for(let s=0;s<N;s++){const a=st[s],ra=rad(a[6]);
  for(let u=s+1;u<N;u++){const c=st[u],d=Math.hypot(a[0]-c[0],a[1]-c[1],a[2]-c[2]),o=ra+rad(c[6])-d;
   if(o>0){ov=Math.max(ov,o);nov++;if(u-s>K)miss=Math.max(miss,o)}}
  pen=Math.max(pen,a[1]+ra);if(s+1<N&&a[0]>st[s+1][0]+0.01)uns++;
  ke+=((a[0]-a[3])**2+(a[1]-a[4])**2+(a[2]-a[5])**2)*RATE*RATE}
 worstOv=Math.max(worstOv,ov);worstMiss=Math.max(worstMiss,miss);worstPen=Math.max(worstPen,pen);
 console.log(`t=${((t+1)/2).toFixed(1)}s fps ${(fr*2).toFixed(0)} | overlap max ${ov.toFixed(2)} (${nov} pairs) missed ${miss.toFixed(2)} | floor pen ${pen.toFixed(2)} | unsorted ${uns} | vrms ${Math.sqrt(ke/N).toFixed(0)} | slot0 ${st[0].slice(0,3).map(v=>v.toFixed(1))}`);
}
if(SHOT)await p.screenshot({path:SHOT});
if(worstMiss>6)fail.push('missed contacts '+worstMiss.toFixed(1));
if(worstPen>4)fail.push('floor penetration '+worstPen.toFixed(1));
console.log(fail.length?'FAIL: '+fail.join(', '):'ok',`(N=${N} K=${K}; worst overlap ${worstOv.toFixed(2)})`);
await b.close();if(process.env.CHECK&&fail.length)process.exit(1)})();
