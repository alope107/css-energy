// node tools/filmstrip.js page.html out.png [delayMs=1500] [durMs=1000] : what the user sees, frame by frame (harness only)
// Records the compositor's frames with CDP screencast and writes a contact sheet of consecutive frames (out.png) to look
// at. Also scores "snap-backs": low-resolution cells that return to how they looked 2–30 frames earlier after changing
// a lot in between. Forward motion rarely does that; a pose that jumps back and forth does it every cycle.
// Use it on anything that moves on the compositor (transitions, animations): screenshots and fps can't show it.
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [src,dst,delay='1500',dur='1000']=process.argv.slice(2);
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:900}});
await p.goto(require('url').pathToFileURL(require('path').resolve(src)).href);await p.waitForTimeout(+delay);
const clip=await p.locator(process.env.CLIP||'.arena').first().boundingBox({timeout:2000}).catch(()=>null);   // crop to the arena if there is one
const cdp=await p.context().newCDPSession(p);const frames=[];
cdp.on('Page.screencastFrame',f=>{frames.push({t:f.metadata.timestamp,data:f.data});cdp.send('Page.screencastFrameAck',{sessionId:f.sessionId}).catch(()=>{})});
await cdp.send('Page.startScreencast',{format:'jpeg',quality:70,maxWidth:1000,maxHeight:900,everyNthFrame:1});
await p.waitForTimeout(+dur);await cdp.send('Page.stopScreencast');
const fps=frames.length/((frames.at(-1).t-frames[0].t)||1);
// analysis and contact sheet in a blank page (canvas decodes the JPEGs)
const q=await b.newPage();
const r=await q.evaluate(async({frames,COLS,clip})=>{
 const raw=await Promise.all(frames.map(f=>new Promise(r=>{const i=new Image();i.onload=()=>r(i);i.src='data:image/jpeg;base64,'+f.data})));
 const k=raw[0].width/1000,cb=clip?[clip.x*k,clip.y*k,clip.width*k,clip.height*k]:[0,0,raw[0].width,raw[0].height];
 const imgs=raw.map(i=>{const o=new OffscreenCanvas(cb[2],cb[3]);o.getContext('2d').drawImage(i,cb[0],cb[1],cb[2],cb[3],0,0,cb[2],cb[3]);return o});
 const W=64,H=48,c=new OffscreenCanvas(W,H),x=c.getContext('2d',{willReadFrequently:true});
 const g=imgs.map(i=>{x.drawImage(i,0,0,W,H);const d=x.getImageData(0,0,W,H).data,o=new Float32Array(W*H);for(let k=0;k<W*H;k++)o[k]=(d[4*k]+d[4*k+1]+d[4*k+2])/3;return o});
 let snaps=0,cells=0;
 for(let t=2;t<g.length;t++)for(let k=0;k<W*H;k++){cells++;
  for(let s=2;s<=Math.min(30,t);s++){const a=g[t-s];if(Math.abs(g[t][k]-a[k])>6)continue;
   let m=0;for(let j=t-s+1;j<t;j++)m=Math.max(m,Math.abs(g[j][k]-a[k]));if(m>40){snaps++;break}}}
 const n=Math.min(imgs.length,COLS*6),w=imgs[0].width,h=imgs[0].height,sc=new OffscreenCanvas(COLS*w,Math.ceil(n/COLS)*h),sx=sc.getContext('2d');
 sx.font='14px monospace';sx.fillStyle='#ff0';
 for(let i=0;i<n;i++){sx.drawImage(imgs[i],(i%COLS)*w,Math.floor(i/COLS)*h);sx.fillText(String(i),(i%COLS)*w+4,Math.floor(i/COLS)*h+16)}
 const blob=await sc.convertToBlob({type:'image/png'});const buf=new Uint8Array(await blob.arrayBuffer());let s='';for(const v of buf)s+=String.fromCharCode(v);
 return {snapRate:snaps/Math.max(1,cells),png:btoa(s),n}},{frames,COLS:+(process.env.COLS||6),clip});
fs.writeFileSync(dst,Buffer.from(r.png,'base64'));
console.log(`${src}: ${frames.length} compositor frames (${fps.toFixed(1)}/s), snap-back cells ${(r.snapRate*1000).toFixed(2)} per 1000; first ${r.n} frames in ${dst}`);
await b.close()})();
