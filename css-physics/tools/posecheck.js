// node tools/posecheck.js page.html [ms] : does what's drawn follow each body's pose, frame by frame? (exit 1 if not)
// Any built page, PLAIN or published (the bodies are the .bw wrappers it finds). On every frame for ms (default 6000)
// compares, for every body, the values the pose animation writes on its wrapper (.bw, #w<i>) with the copies its
// drawing reads further down:
//   rotation  .bw's --Ri --Rj --Rk against .bd's (the matrix3d is built from them)
//   shadow    .bw's --Ry against .sh's (the shadow's height, size and fade)
//   faces     .bd's face colours --k0…--k5 against each face's (boxes, .bx)
// and counts the body-frames in which a copy is off (1e-3; colours by their channels) while the body moves.
// Chrome and Firefox pass the values down with an explicit `inherit`; Safari 26 didn't re-apply it when the parent's
// value changed (ARCHITECTURE.md §7): bodies slid without turning and snapped when something else restyled them.
// BROWSER=webkit|safari|firefox as for the other evaluate-based tools.
const {launch,open}=require('./lib/physics');
(async()=>{const f=process.argv[2];const T=+(process.argv[3]||6000);
const b=await launch();const p=await open(b,f,{viewport:{width:1000,height:760}});
const n=await p.evaluate(()=>document.querySelectorAll('.bw').length);
if(!n){console.error(`${f}: no body wrappers (.bw)`);process.exit(2)}
const r=await p.evaluate(T=>new Promise(res=>{
 const E=[...document.querySelectorAll('.bw')].map(w=>{const b=w.querySelector(':scope > .bd');
  return {w,b,s:w.querySelector(':scope > .sh'),f:b.classList.contains('bx')?[0,1,2,3,4,5].map(k=>b.querySelector('.f'+k)):[]}});const n=E.length;
 // a computed colour's channels (color(srgb r g b) or rgb(r, g, b), 0–1 either way)
 const ch=s=>{const m=s.match(/[-\d.e]+/g)||[];const v=m.slice(0,3).map(Number);return /^rgb/.test(s)?v.map(x=>x/255):v};
 const num=(st,k)=>+st.getPropertyValue(k);
 const kinds3={rotation:[0,0,0],shadow:[0,0,0],faces:[0,0,0]};   // [moving body-frames, off, worst]
 const ex=[];let frames=0,prev=null;const t0=performance.now();
 const note=(kind,i,moving,d,a,c)=>{const o=kinds3[kind];if(!moving)return;o[0]++;o[2]=Math.max(o[2],d);
  if(d>1e-3){o[1]++;if(ex.length<8)ex.push(`frame ${frames} body ${i} ${kind}: wrapper ${a} drawn ${c}`)}};
 function f(){frames++;const cur=[];
  for(let i=0;i<n;i++){const e=E[i],sw=getComputedStyle(e.w),sb=getComputedStyle(e.b);
   const q=['--Ri','--Rj','--Rk'].map(k=>num(sw,k)),y=num(sw,'--Ry');cur.push([...q,y]);
   const moving=prev&&Math.max(...cur[i].map((v,j)=>Math.abs(v-prev[i][j])))>1e-4;
   const qb=['--Ri','--Rj','--Rk'].map(k=>num(sb,k));
   note('rotation',i,moving,Math.max(...q.map((v,j)=>Math.abs(v-qb[j]))),q.map(v=>v.toFixed(4)),qb.map(v=>v.toFixed(4)));
   const ys=num(getComputedStyle(e.s),'--Ry');note('shadow',i,moving,Math.abs(y-ys)/Math.max(1,Math.abs(y)),y.toFixed(2),ys.toFixed(2));
   e.f.forEach((fe,k)=>{const a=sb.getPropertyValue('--k'+k).trim(),c=getComputedStyle(fe).getPropertyValue('--k'+k).trim();
    const A=ch(a),C=ch(c);note('faces',i,moving,Math.max(...A.map((v,j)=>Math.abs(v-C[j]))),a,c)})}
  prev=cur;if(performance.now()-t0<T)requestAnimationFrame(f);else res({frames,kinds:kinds3,ex})}
 requestAnimationFrame(f)}),T);
await b.close();
let bad=false;const parts=[];
for(const [k,[m,off,worst]] of Object.entries(r.kinds)){const fail=off>Math.max(2,m*0.01);bad=bad||fail;parts.push(`${k} ${off}/${m} off (worst ${worst.toPrecision(2)})${fail?' FAIL':''}`)}
console.log(`${bad?'FAIL':'PASS'} ${f}: ${r.frames} frames; body-frames moving with the drawn copy off: ${parts.join(', ')}`);
if(bad)for(const e of r.ex)console.log('  '+e);
process.exit(bad?1:0)})();
