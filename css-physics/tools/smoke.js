// node tools/smoke.js page.html [ms] : pass/fail physics check on a PLAIN single-engine page (exit 1 on failure)
// Runs the page for ms (default 12000) and fails on: non-finite state, floor penetration > 3 px in the second
// half, sphere/sphere overlap > 4 px in the second half, or speed > 5000.
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const f=process.argv[2];const T=+(process.argv[3]||12000);const s=fs.readFileSync(f,'utf8');
const m=s.match(/<!--BODYINFO (.*?)-->/);if(!m){console.error('no BODYINFO: build with COUNTS=<n> PLAIN=1');process.exit(2)}
const info=JSON.parse(m[1]);
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:760}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);
const r=await p.evaluate(([info,T])=>new Promise(res=>{const el=document.getElementById('LS');let pen=-1e9,ov=0,vmax=0,bad=0,n=0;const t0=performance.now();
function rd(){const st=getComputedStyle(el);const g=k=>parseFloat(st.getPropertyValue('--'+k));return info.map((bi,i)=>({x:g('X'+i),y:g('Y'+i),z:g('Z'+i),w:g('QW'+i),qx:g('QX'+i),qy:g('QY'+i),qz:g('QZ'+i),v:Math.hypot(g('VX'+i),g('VY'+i),g('VZ'+i)),sc:g('SC'+i)}))}
function f(){const B=rd();n++;const late=performance.now()-t0>T*0.5;
 for(let i=0;i<B.length;i++){const o=B[i],bi=info[i];
  if(![o.x,o.y,o.z,o.v].every(Number.isFinite))bad++;
  let sup;if(bi.k=='sph')sup=bi.r;else{const w=Number.isFinite(o.w)?o.w:Math.sqrt(Math.max(0,1-o.qx*o.qx-o.qy*o.qy-o.qz*o.qz));const x=o.qx,y=o.qy,z=o.qz;const ay=[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)];sup=ay.reduce((a,v,j)=>a+Math.abs(v)*bi.h[j],0)}
  vmax=Math.max(vmax,o.v||0);if(late)pen=Math.max(pen,o.y+sup);
  for(let j=i+1;j<B.length;j++)if(late&&bi.k=='sph'&&info[j].k=='sph'){const d=Math.hypot(o.x-B[j].x,o.y-B[j].y,o.z-B[j].z);ov=Math.max(ov,bi.r+info[j].r-d)}}
 if(performance.now()-t0<T)requestAnimationFrame(f);else res({frames:n,bad,floorPen:+pen.toFixed(2),sphOverlap:+ov.toFixed(2),vmax:Math.round(vmax),asleep:B.filter(o=>o.sc>45).length,n:B.length})}
requestAnimationFrame(f)}),[info,T]);
await b.close();
const fails=[];if(r.bad)fails.push('non-finite state');if(r.floorPen>3)fails.push('floor penetration '+r.floorPen);if(r.sphOverlap>4)fails.push('sphere overlap '+r.sphOverlap);if(r.vmax>5000)fails.push('speed '+r.vmax);
console.log((fails.length?'FAIL ':'PASS ')+f,JSON.stringify(r),fails.join('; '));process.exit(fails.length?1:0)})();
