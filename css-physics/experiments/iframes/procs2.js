const {chromium}=require('playwright');
(async()=>{const exe=process.env.CHROME||undefined;
const b=await chromium.launch({executablePath:exe,args:['--no-sandbox',...(process.env.ARGS?process.env.ARGS.split(' '):[])]});
for(const f of process.argv.slice(2)){const p=await b.newPage();await p.goto(f.startsWith('http')?f:require('url').pathToFileURL(require('path').resolve(f)).href);await p.waitForTimeout(1500);
const cdp=await b.newBrowserCDPSession();const ev=[];cdp.on('Tracing.dataCollected',d=>ev.push(...d.value));
await cdp.send('Tracing.start',{categories:'devtools.timeline',transferMode:'ReportEvents'});await p.waitForTimeout(3000);
const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;
const by={};for(const e of ev){if(e.ph==='X'&&e.name==='UpdateLayoutTree'){const a=by[e.pid]=by[e.pid]||{n:0,t:0};a.n++;a.t+=e.dur/1000}}
console.log(f.padEnd(12),Object.entries(by).map(([k,v])=>`pid${k}: ${v.n} passes, ${(v.t/v.n).toFixed(1)}ms avg, ${(v.n/3).toFixed(1)}/s`).join(' | '));await p.close()}
await b.close()})();
