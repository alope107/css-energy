const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:800}});await p.goto(require('url').pathToFileURL(require('path').resolve(process.argv[2])).href);await p.waitForTimeout(+process.argv[3]||2000);
const cdp=await p.context().newCDPSession(p);const ev=[];cdp.on('Tracing.dataCollected',d=>ev.push(...d.value));
await cdp.send('Tracing.start',{categories:'devtools.timeline,disabled-by-default-devtools.timeline,blink,blink.debug,blink_style,disabled-by-default-blink.debug,cc,animation',transferMode:'ReportEvents'});
await p.waitForTimeout(+process.argv[4]||1500);
const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;
const agg={};for(const e of ev){if(e.ph!=='X')continue;if(!e.dur)continue;const a=agg[e.name]=agg[e.name]||{n:0,t:0};a.n++;a.t+=e.dur/1000}
console.log(Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,30).map(([k,v])=>k.padEnd(50)+v.n+'\t'+v.t.toFixed(1)).join('\n'));
await b.close()})();
