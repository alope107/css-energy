// trace profile: node tools/tr.js file.html[,file2.html…] [delayMs=1500] [durMs=2000]
// TOUCH=1 opens it on a phone-sized touch screen. Prints per-pass style recalc time (UpdateLayoutTree), layout, frames. V=1 lists the top events; TRACE=t.json saves the
// trace (several pages: t-0.json, t-1.json, …); with CAT=blink,devtools.timeline,disabled-by-default-devtools.timeline,cc
// it has what python3 ../shared/py/passprof.py t.json needs (passes and style+layout ms per frame)
const {launch,open,record,countFrames,aggregate,durations,median,bigmed,saveTrace,projector}=require('./lib/physics');
(async()=>{const b=await launch();
const files=process.argv[2].split(',');
for(const [k,f] of files.entries()){
// TOUCH=1: a phone-sized touch screen (touch mode: the handles and #TI instead of the hover grid)
const p=await open(b,f,process.env.TOUCH?{viewport:{width:412,height:915},deviceScaleFactor:2.625,isMobile:true,hasTouch:true}:{viewport:{width:1000,height:800}});
if(process.env.HOVER){await p.mouse.move(500,400);}
await p.waitForTimeout(+(process.argv[3]||1500));
// TOUCHDRAG=1 (with TOUCH=1): a finger on the front-most body's handle, moving in a circle while it records
let touching;if(process.env.TOUCHDRAG){const c=await p.context().newCDPSession(p);const T=(type,x,y)=>c.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y}]});
 const ar=await p.locator('.arena').boundingBox();const proj=projector(ar);
 const [x,y]=await p.evaluate(()=>{for(const h of [...document.querySelectorAll('.eng')].find(e=>getComputedStyle(e).display!=='none').querySelectorAll('.hd')){
  const r=h.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;const e=document.elementFromPoint(x,y);if(e&&e.closest('.hd')===h)return [x,y]}});
 await T('touchStart',x,y);await p.waitForTimeout(100);touching={stop:false};const tg=touching;(async()=>{for(let k=0;k<2000&&!tg.stop;k++){await T('touchMove',x+40*Math.sin(k/20)-1,y-60+40*Math.cos(k/20));await p.waitForTimeout(16)}})()}
if(process.env.PRESS){await p.mouse.move(+process.env.PX||500,+process.env.PY||420);await p.mouse.down();}
const dur=+(process.argv[4]||2000);
const {events:ev,result:fr}=await record(p,{categories:process.env.CAT||'devtools.timeline'},()=>countFrames(p,dur));
if(process.env.TRACE)saveTrace(ev,files.length>1?process.env.TRACE.replace(/(\.json)?$/,'-'+k+'$1'):process.env.TRACE);
const agg=aggregate(ev,e=>['UpdateLayoutTree','Layout','Paint','PrePaint','Layerize','UpdateLayer','RunTask','Animation','UpdateAnimations','ScrollTimeline'].includes(e.name)||/Style|Timeline/.test(e.name));
const u=agg.UpdateLayoutTree||{n:0,t:0};
const uds=durations(ev,'UpdateLayoutTree').sort((a,b)=>a-b);const med=median(uds);const bmed=bigmed(uds,1);
console.log(f.padEnd(26),'med',med.toFixed(2),'bigmed',bmed.toFixed(2),'fps',(fr/dur*1000).toFixed(1),'| style passes',u.n,'avg',(u.t/Math.max(1,u.n)).toFixed(2),'ms; per frame',(u.t/fr).toFixed(1),'| layout',((agg.Layout||{t:0}).t/fr).toFixed(2),'| paint',((agg.Paint||{t:0}).t/fr).toFixed(2));
if(process.env.V)for(const [k,v] of Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,14))console.log('   ',k.padEnd(34),v.n,v.t.toFixed(1),'ms max',v.max.toFixed(1));
if(touching)touching.stop=true;await p.close()}await b.close()})();
