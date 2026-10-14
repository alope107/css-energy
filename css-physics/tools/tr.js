// trace profile: node tools/tr.js file.html[,file2.html…] [delayMs=1500] [durMs=2000]
// prints per-pass style recalc time (UpdateLayoutTree), layout, frames. V=1 lists the top events; TRACE=t.json saves the
// trace (several pages: t-0.json, t-1.json, …); with CAT=blink,devtools.timeline,disabled-by-default-devtools.timeline,cc
// it has what python3 ../shared/py/passprof.py t.json needs (passes and style+layout ms per frame)
const {launch,open,record,countFrames,aggregate,durations,median,bigmed,saveTrace}=require('./lib/physics');
(async()=>{const b=await launch();
const files=process.argv[2].split(',');
for(const [k,f] of files.entries()){
const p=await open(b,f,{viewport:{width:1000,height:800}});
if(process.env.HOVER){await p.mouse.move(500,400);}
await p.waitForTimeout(+(process.argv[3]||1500));
if(process.env.PRESS){await p.mouse.move(+process.env.PX||500,+process.env.PY||420);await p.mouse.down();}
const dur=+(process.argv[4]||2000);
const {events:ev,result:fr}=await record(p,{categories:process.env.CAT||'devtools.timeline'},()=>countFrames(p,dur));
if(process.env.TRACE)saveTrace(ev,files.length>1?process.env.TRACE.replace(/(\.json)?$/,'-'+k+'$1'):process.env.TRACE);
const agg=aggregate(ev,e=>['UpdateLayoutTree','Layout','Paint','PrePaint','Layerize','UpdateLayer','RunTask','Animation','UpdateAnimations','ScrollTimeline'].includes(e.name)||/Style|Timeline/.test(e.name));
const u=agg.UpdateLayoutTree||{n:0,t:0};
const uds=durations(ev,'UpdateLayoutTree').sort((a,b)=>a-b);const med=median(uds);const bmed=bigmed(uds,1);
console.log(f.padEnd(26),'med',med.toFixed(2),'bigmed',bmed.toFixed(2),'fps',(fr/dur*1000).toFixed(1),'| style passes',u.n,'avg',(u.t/Math.max(1,u.n)).toFixed(2),'ms; per frame',(u.t/fr).toFixed(1),'| layout',((agg.Layout||{t:0}).t/fr).toFixed(2),'| paint',((agg.Paint||{t:0}).t/fr).toFixed(2));
if(process.env.V)for(const [k,v] of Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,14))console.log('   ',k.padEnd(34),v.n,v.t.toFixed(1),'ms max',v.max.toFixed(1));
await p.close()}await b.close()})();
