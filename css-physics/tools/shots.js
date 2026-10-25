// node tools/shots.js page.html out.png [delayMs=800] [n=24] : a contact sheet of n screenshots taken back to back
// For browsers without a screencast (BROWSER=safari: each screenshot is a WebDriver round trip, roughly 5–10 a second;
// filmstrip.js records every compositor frame, Chromium only). Crops to .arena (CLIP= another selector, CLIP= empty
// for the whole window), labels each frame with its time since the first, and lays them out 6 across in Chromium.
const {launch,launchers,open}=require('./lib/physics');const fs=require('fs');
(async()=>{const [f,dst,delay='800',n='24']=process.argv.slice(2);
const b=await launch();const p=await open(b,f,{viewport:{width:1000,height:760}});await p.waitForTimeout(+delay);
const sel=process.env.CLIP??'.arena';const clip=sel?await p.locator(sel).boundingBox():null;const vw=(await p.evaluate(()=>innerWidth));
const shots=[];const t0=Date.now();
for(let i=0;i<+n;i++){const png=await p.screenshot();shots.push({t:Date.now()-t0,data:png.toString('base64')})}
await b.close();
const c=await launchers.chromium();const q=await c.newPage();
const out=await q.evaluate(async({shots,clip,vw})=>{
 const imgs=await Promise.all(shots.map(s=>new Promise(r=>{const i=new Image();i.onload=()=>r(i);i.src='data:image/png;base64,'+s.data})));
 const k=imgs[0].width/vw,cb=clip?[clip.x*k,clip.y*k,clip.width*k,clip.height*k]:[0,0,imgs[0].width,imgs[0].height];
 const s=Math.min(1,320/cb[2]),w=Math.round(cb[2]*s),h=Math.round(cb[3]*s),COLS=6;
 const sc=new OffscreenCanvas(COLS*w,Math.ceil(imgs.length/COLS)*h),x=sc.getContext('2d');x.font='14px sans-serif';
 imgs.forEach((im,i)=>{const X=(i%COLS)*w,Y=Math.floor(i/COLS)*h;x.drawImage(im,cb[0],cb[1],cb[2],cb[3],X,Y,w,h);
  x.fillStyle='#000';x.fillRect(X,Y,70,18);x.fillStyle='#fff';x.fillText(`${i} ${shots[i].t}ms`,X+3,Y+14)});
 const bl=await sc.convertToBlob({type:'image/png'});const u=new Uint8Array(await bl.arrayBuffer());let str='';for(const v of u)str+=String.fromCharCode(v);return btoa(str)},{shots,clip,vw});
fs.writeFileSync(dst,Buffer.from(out,'base64'));await c.close();
const dt=shots.slice(1).map((s,i)=>s.t-shots[i].t);
console.log(`${dst}: ${shots.length} screenshots over ${shots.at(-1).t} ms (median gap ${dt.sort((a,b)=>a-b)[dt.length>>1]} ms)`)})()
.catch(e=>{console.error(e.message);process.exit(1)});
