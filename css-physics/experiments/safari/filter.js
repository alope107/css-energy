// node experiments/safari/filter.js: for each row of filter.html, how much the filtered box's pixels differ from the
// unfiltered one's (mean absolute difference, 0–255; ~0 means the filter didn't apply). Each row is scrolled into view
// and shot on its own. BROWSER=safari|chromium.
const {launch,launchers,open}=require('../../tools/lib/physics');
(async()=>{const b=await launch();const p=await open(b,'experiments/safari/filter.html',{viewport:{width:800,height:600}});await p.waitForTimeout(500);
const ids=await p.evaluate(()=>[...document.querySelectorAll('.row')].map(r=>r.id));const vw=await p.evaluate(()=>innerWidth);const rows=[];
for(const id of ids){await p.evaluate(id=>document.getElementById(id).scrollIntoView({block:'center'}),id);await p.waitForTimeout(300);
 // (the box itself, or for rows that filter a wrapper, the wrapper)
 const bx=await p.evaluate(id=>[...document.getElementById(id).children].slice(1).map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}),id);
 rows.push({id,a:bx[0],b:bx[1],png:(await p.screenshot()).toString('base64')})}
const ver=b.version();await b.close();
const c=await launchers.chromium();const q=await c.newPage();
const r=await q.evaluate(async({rows,vw})=>{const out=[];for(const {id,a,b,png} of rows){
 const im=await new Promise(r=>{const i=new Image();i.onload=()=>r(i);i.src='data:image/png;base64,'+png});
 const k=im.width/vw,cv=new OffscreenCanvas(im.width,im.height),x=cv.getContext('2d');x.drawImage(im,0,0);
 const w=Math.round(Math.min(a.w,b.w)*k),h=Math.round(Math.min(a.h,b.h)*k);
 const A=x.getImageData(Math.round(a.x*k),Math.round(a.y*k),w,h).data,B=x.getImageData(Math.round(b.x*k),Math.round(b.y*k),w,h).data;
 let d=0;for(let i=0;i<A.length;i+=4)d+=Math.abs(A[i]-B[i])+Math.abs(A[i+1]-B[i+1])+Math.abs(A[i+2]-B[i+2]);out.push(`${id}: ${(d/(A.length/4)/3).toFixed(1)}`)}
 return out},{rows,vw});
console.log(ver,r.join('  '));await c.close()})().catch(e=>{console.error(e.message);process.exit(1)});
