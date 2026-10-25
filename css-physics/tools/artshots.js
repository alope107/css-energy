// node tools/artshots.js page.html out.png [browser…] : each art style as each browser draws it, side by side
// For every style label (label[for^=a-]) clicks it, waits WAIT ms (default 2500) and screenshots the arena; one row per
// style, one column per browser (default: chromium safari). Real screenshots only: Playwright's WebKit flattens 3D in
// its screenshots (CLAUDE.md), so compare Safari (BROWSER-style name `safari`) with Chromium, not WPE. ONLY=cel,paper picks
// styles; W= the width of each picture (default 480).
const {launchers,open}=require('./lib/physics');const fs=require('fs');
(async()=>{const [f,dst,...bs]=process.argv.slice(2);const brs=bs.length?bs:['chromium','safari'];const WAIT=+(process.env.WAIT||2500);
const cols=[];
for(const br of brs){const b=await launchers[br]();const p=await open(b,f,{viewport:{width:1000,height:900}});await p.waitForTimeout(500);
 const styles=(await p.evaluate(()=>[...document.querySelectorAll('label[for^="a-"]')].map(l=>l.getAttribute('for').slice(2)))).filter(s=>!process.env.ONLY||process.env.ONLY.split(',').includes(s));
 const shots=[];
 for(const st of styles){await p.click(`label[for="a-${st}"]`);await p.waitForTimeout(WAIT);
  const clip=await p.locator('.arena').boundingBox();const vw=await p.evaluate(()=>innerWidth);
  shots.push({st,clip,vw,data:(await p.screenshot()).toString('base64')})}
 cols.push({br:`${br} ${b.version()}`,shots});await b.close()}
const c=await launchers.chromium();const q=await c.newPage();
const out=await q.evaluate(async({cols,W})=>{
 const load=d=>new Promise(r=>{const i=new Image();i.onload=()=>r(i);i.src='data:image/png;base64,'+d});
 const H=Math.round(W*0.625),sc=new OffscreenCanvas(W*cols.length,H*cols[0].shots.length+24),x=sc.getContext('2d');x.fillStyle='#000';x.fillRect(0,0,sc.width,sc.height);
 x.font='15px sans-serif';
 for(const [ci,col] of cols.entries()){x.fillStyle='#fff';x.fillText(col.br,ci*W+6,17);
  for(const [ri,s] of col.shots.entries()){const im=await load(s.data);const k=im.width/s.vw,cl=s.clip;
   const r=Math.min(W/(cl.width*k),H/(cl.height*k));x.drawImage(im,cl.x*k,cl.y*k,cl.width*k,cl.height*k,ci*W,24+ri*H,cl.width*k*r,cl.height*k*r);
   x.fillStyle='#000';x.fillRect(ci*W,24+ri*H,90,18);x.fillStyle='#fff';x.fillText(s.st,ci*W+4,24+ri*H+14)}}
 const bl=await sc.convertToBlob({type:'image/png'});const u=new Uint8Array(await bl.arrayBuffer());let str='';for(const v of u)str+=String.fromCharCode(v);return btoa(str)},{cols,W:+(process.env.W||480)});
fs.writeFileSync(dst,Buffer.from(out,'base64'));await c.close();console.log(`${dst}: ${cols[0].shots.length} styles × ${cols.map(c=>c.br).join(', ')}`)})()
.catch(e=>{console.error(e.message);process.exit(1)});
