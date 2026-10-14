// node bench.js page.html[,page2...] [delay] [dur] -> median UpdateLayoutTree ms, layout ms per frame, fps
const {launch,open,envArgs,record,countFrames,durations,median}=require('./lib/physics');
(async()=>{
const b=await launch({args:['--no-sandbox','--no-zygote','--disable-setuid-sandbox'],extraArgs:envArgs('ARGS')});
for(const f of process.argv[2].split(',')){
const p=await open(b,f,{viewport:{width:1000,height:800}});await p.evaluate(()=>document.fonts.ready);
await p.waitForTimeout(+(process.argv[3]||800));
const dur=+(process.argv[4]||1500);
const {events:ev,result:fr}=await record(p,{},()=>countFrames(p,dur));
const u=durations(ev,'UpdateLayoutTree').sort((a,b)=>a-b),l=durations(ev,'Layout');const med=median(u);
let extra='';if(process.env.PROBE)extra=await p.evaluate(s=>eval(s),process.env.PROBE);
console.log(f.padEnd(24),'style med',med.toFixed(3),'max',(u[u.length-1]||0).toFixed(2),'n',u.length,'| layout/fr',(l.reduce((a,b)=>a+b,0)/fr).toFixed(3),'| fps',(fr/dur*1000).toFixed(1),extra);
await p.close()}await b.close()})();
