// trace profile: node p2/tr.js file.html [delayMs=1500] [durMs=2000]
// prints per-pass style recalc time (UpdateLayoutTree), layout, frames
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
for(const f of process.argv[2].split(',')){
const p=await b.newPage({viewport:{width:1000,height:800}});
await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);
if(process.env.HOVER){await p.mouse.move(500,400);}
await p.waitForTimeout(+(process.argv[3]||1500));
if(process.env.PRESS){await p.mouse.move(+process.env.PX||500,+process.env.PY||420);await p.mouse.down();}
const cdp=await p.context().newCDPSession(p);
const ev=[];cdp.on('Tracing.dataCollected',d=>ev.push(...d.value));
await cdp.send('Tracing.start',{categories:process.env.CAT||'devtools.timeline',transferMode:'ReportEvents'});
const dur=+(process.argv[4]||2000);
const fr=await p.evaluate(d=>new Promise(r=>{let n=0;const t0=performance.now();(function f(){n++;if(performance.now()-t0<d)requestAnimationFrame(f);else r(n)})()}),dur);
const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;
const agg={};const uds=[];
for(const e of ev){if(e.ph!=='X')continue;if(['UpdateLayoutTree','Layout','Paint','PrePaint','Layerize','UpdateLayer','RunTask','Animation','UpdateAnimations','ScrollTimeline'].includes(e.name)||/Style|Timeline/.test(e.name)){if(e.name==='UpdateLayoutTree')uds.push(e.dur/1000);const a=agg[e.name]=agg[e.name]||{n:0,t:0,max:0};a.n++;a.t+=e.dur/1000;a.max=Math.max(a.max,e.dur/1000)}}
const u=agg.UpdateLayoutTree||{n:0,t:0};
uds.sort((a,b)=>a-b);const med=uds.length?uds[uds.length>>1]:0;const big=uds.filter(x=>x>Math.max(1,uds[uds.length-1]*0.3));const bmed=big.length?big[big.length>>1]:0;
console.log(f.padEnd(26),'med',med.toFixed(2),'bigmed',bmed.toFixed(2),'fps',(fr/dur*1000).toFixed(1),'| style passes',u.n,'avg',(u.t/Math.max(1,u.n)).toFixed(2),'ms; per frame',(u.t/fr).toFixed(1),'| layout',((agg.Layout||{t:0}).t/fr).toFixed(2),'| paint',((agg.Paint||{t:0}).t/fr).toFixed(2));
if(process.env.V)for(const [k,v] of Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,14))console.log('   ',k.padEnd(34),v.n,v.t.toFixed(1),'ms max',v.max.toFixed(1));
await p.close()}await b.close()})();
