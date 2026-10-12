// node bench.js page.html[,page2...] [delay] [dur] -> median UpdateLayoutTree ms, layout ms per frame, fps
const {chromium}=require('playwright');
(async()=>{const exe=process.env.CHROME||undefined;
const b=await chromium.launch({executablePath:exe,args:['--no-sandbox','--no-zygote','--disable-setuid-sandbox',...(process.env.ARGS?process.env.ARGS.split(' '):[])]});
for(const f of process.argv[2].split(',')){
const p=await b.newPage({viewport:{width:1000,height:800}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);await p.evaluate(()=>document.fonts.ready);
await p.waitForTimeout(+(process.argv[3]||800));
const cdp=await p.context().newCDPSession(p);const ev=[];cdp.on('Tracing.dataCollected',d=>ev.push(...d.value));
await cdp.send('Tracing.start',{categories:'devtools.timeline',transferMode:'ReportEvents'});
const dur=+(process.argv[4]||1500);
const fr=await p.evaluate(d=>new Promise(r=>{let n=0;const t0=performance.now();(function f(){n++;if(performance.now()-t0<d)requestAnimationFrame(f);else r(n)})()}),dur);
const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;
const u=[],l=[];for(const e of ev){if(e.ph!=='X')continue;if(e.name==='UpdateLayoutTree')u.push(e.dur/1000);if(e.name==='Layout')l.push(e.dur/1000)}
u.sort((a,b)=>a-b);const med=u.length?u[u.length>>1]:0;
let extra='';if(process.env.PROBE)extra=await p.evaluate(s=>eval(s),process.env.PROBE);
console.log(f.padEnd(24),'style med',med.toFixed(3),'max',(u[u.length-1]||0).toFixed(2),'n',u.length,'| layout/fr',(l.reduce((a,b)=>a+b,0)/fr).toFixed(3),'| fps',(fr/dur*1000).toFixed(1),extra);
await p.close()}await b.close()})();
