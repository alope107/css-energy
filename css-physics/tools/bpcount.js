// node tools/bpcount.js page.html N ms[,ms...] : broadphase candidate counts from the live state at each time (cumulative waits):
// sphere test (what the engine uses: R_a + R_b + 3 > dist), world AABB overlap (+3 margin), and pairs actually touching (tcp/np-exact).
const {launch,open,bodyInfo}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2],N=+process.argv[3];
const info=bodyInfo(fs.readFileSync(f,'utf8'));if(!info)throw new Error(f+': no BODYINFO (build with COUNTS=<n> PLAIN=1)');
const b=await launch();
const p=await open(b,f,{viewport:{width:1000,height:800}});
for(const t of process.argv[4].split(',')){await p.waitForTimeout(+t);
 const r=await p.evaluate(([info,N])=>{const c=getComputedStyle(document.getElementById('LS'));const g=k=>+c.getPropertyValue('--'+k);
  const B=info.map((bi,i)=>{const q=[g('QW'+i),g('QX'+i),g('QY'+i),g('QZ'+i)];const [w,x,y,z]=q;
   const R=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]];
   let ext,Rb;if(bi.k==='sph'){ext=[bi.r,bi.r,bi.r];Rb=bi.r}else{ext=[0,1,2].map(a=>bi.h[0]*Math.abs(R[a][0])+bi.h[1]*Math.abs(R[a][1])+bi.h[2]*Math.abs(R[a][2]));Rb=Math.hypot(...bi.h)}
   return {p:[g('X'+i),g('Y'+i),g('Z'+i)],ext,Rb,aw:g('SC'+i)<=45}});
  let sph=0,aabb=0,touch=0,awp=0;const els=[...document.querySelectorAll('[id^=L]')].filter(e=>/^L\d+$/.test(e.id)).map(e=>getComputedStyle(e));
  for(let a=0;a<N;a++)for(let bb=a+1;bb<N;bb++){const A=B[a],C=B[bb];if(!(A.aw||C.aw))continue;awp++;
   const d=[0,1,2].map(k=>Math.abs(A.p[k]-C.p[k]));
   if(Math.hypot(...d)<A.Rb+C.Rb+3)sph++;
   if(d.every((v,k)=>v<A.ext[k]+C.ext[k]+3))aabb++;
   for(const s of els){const v=s.getPropertyValue('--tcp'+a+'_'+bb).trim();if(v&&v!=='0'){touch++;break}
    const u=s.getPropertyValue('--p'+a+'_'+bb+'ov').trim();if(u&&u!=='0'){touch++;break}}}
  return {awake:B.filter(x=>x.aw).length,awakePairs:awp,sphere:sph,aabb,touching:touch}},[info,N]);
 console.log(t,JSON.stringify(r))}
await b.close()})();
