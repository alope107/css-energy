// node tools/traceagg.js page.html [delayMs=2000] [durMs=1500] : every traced event (blink, cc, animation) by total time;
// SELF=1 prints self time on the main thread instead (a parent's time minus its children's: these add up)
const {launch,open,record,aggregate,selfTime}=require('./lib/physics');
(async()=>{const b=await launch();
const p=await open(b,process.argv[2],{viewport:{width:1000,height:800}});await p.waitForTimeout(+process.argv[3]||2000);
const {events:ev}=await record(p,{categories:'devtools.timeline,disabled-by-default-devtools.timeline,blink,blink.debug,blink_style,disabled-by-default-blink.debug,cc,animation'},()=>p.waitForTimeout(+process.argv[4]||1500));
if(process.env.SELF)console.log(selfTime(ev).sort((a,b)=>b[2]-a[2]).slice(0,30).map(([k,t,s,n])=>k.padEnd(50)+n+'\t'+t.toFixed(1)+'\tself '+s.toFixed(1)).join('\n'));
else{const agg=aggregate(ev,e=>e.dur);
console.log(Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,30).map(([k,v])=>k.padEnd(50)+v.n+'\t'+v.t.toFixed(1)).join('\n'))}
await b.close()})();
