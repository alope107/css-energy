const {launch,open,envArgs,record}=require('./lib/physics');
(async()=>{const b=await launch({extraArgs:envArgs('ARGS')});
for(const f of process.argv.slice(2)){const p=await open(b,f,{viewport:{width:900,height:600}});await p.waitForTimeout(1500);
const {events:ev}=await record(p,{categories:'devtools.timeline,cc,viz,benchmark,disabled-by-default-devtools.timeline.frame',browser:true},()=>p.waitForTimeout(3000));
const cnt={};for(const e of ev){if(/DrawFrame|BeginMainFrame$|SubmitCompositorFrame|Graphics.Pipeline.DrawAndSwap|ProxyImpl::ScheduledActionDraw|UpdateLayoutTree|AnimationHost::TickAnimations|TickAnimations/.test(e.name)&&(e.ph==='X'||e.ph==='B'||e.ph==='I'||e.ph==='b')){cnt[e.name]=(cnt[e.name]||0)+1}}
let ul=0,un=0;for(const e of ev)if(e.name==='UpdateLayoutTree'&&e.ph==='X'){ul+=e.dur/1000;un++}
console.log(f.padEnd(16),'style avg',(ul/Math.max(un,1)).toFixed(1),'ms |',Object.entries(cnt).map(([k,v])=>k+':'+(v/3).toFixed(1)+'/s').join(' '));await p.close()}
await b.close()})();
