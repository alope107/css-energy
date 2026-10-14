// node sanity3.js page.html ms : run, then report floor penetration, sphere overlaps, speeds, sleepers
const {launch,open,bodyInfo}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2];const s=fs.readFileSync(f,'utf8');const info=bodyInfo(process.argv[4]?fs.readFileSync(process.argv[4],'utf8'):s);if(!info)throw new Error(f+': no BODYINFO (build with COUNTS=<n> PLAIN=1)');
const b=await launch();
const p=await open(b,f,{viewport:{width:1000,height:760}});
const r=await p.evaluate(([info,T])=>new Promise(res=>{const el=document.getElementById('LS');let worst=-1e9,ov=0,vmax=0,n=0,t0=performance.now();
function rd(){const st=getComputedStyle(el);const g=k=>+st.getPropertyValue('--'+k);return info.map((bi,i)=>({x:g('X'+i),y:g('Y'+i),z:g('Z'+i),w:g('QW'+i),qx:g('QX'+i),qy:g('QY'+i),qz:g('QZ'+i),v:Math.hypot(g('VX'+i),g('VY'+i),g('VZ'+i)),sc:g('SC'+i)}))}
function f(){const B=rd();n++;const late=performance.now()-t0>T*0.5;
for(let i=0;i<B.length;i++){const o=B[i],bi=info[i];let sup;if(bi.k=='sph')sup=bi.r;else{const {w,qx:x,qy:y,qz:z}=o;const ay=[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)];sup=ay.reduce((a,v,j)=>a+Math.abs(v)*bi.h[j],0)}
 if(late)worst=Math.max(worst,o.y+sup);vmax=Math.max(vmax,o.v);
 for(let j=i+1;j<B.length;j++)if(bi.k=='sph'&&info[j].k=='sph'&&late){const d=Math.hypot(o.x-B[j].x,o.y-B[j].y,o.z-B[j].z);ov=Math.max(ov,bi.r+info[j].r-d)}}
if(performance.now()-t0<T)requestAnimationFrame(f);else res({frames:n,floorPen:worst.toFixed(2),sphOverlap:ov.toFixed(2),vmax:vmax.toFixed(0),asleep:B.filter(o=>o.sc>45).length,ys:B.map(o=>o.y.toFixed(0)).join(' ')})}
requestAnimationFrame(f)}),[info,+process.argv[3]]);
console.log(f,JSON.stringify(r));await b.close()})();
