// node tools/freeze3.js src.html ms out_prefix tgt.html...  (writes <dir of tgt>/<prefix>_<tgt name>; to freeze while holding a grab: freezegrab.js)
// snapshot the state registers of src at ms and bake them into each target as constants with a tiny
// wobble (so every dependent prop recomputes every frame while all gates stay put)
const {launch,open,vars,registerNames,bakeRegisters}=require('./lib/physics');const fs=require('fs');
(async()=>{const [src,ms,pre,...tgts]=process.argv.slice(2);
const s0=fs.readFileSync(src,'utf8');const names=registerNames(s0);
const b=await launch();
const p=await open(b,src,{viewport:{width:1000,height:900}});await p.waitForTimeout(+ms);
const vals=await vars(p,'#LS',names);
await b.close();
for(const t of tgts){const s=bakeRegisters(fs.readFileSync(t,'utf8'),names,vals);
{const path=require('path');fs.writeFileSync(path.join(path.dirname(t),pre+'_'+path.basename(t)),s)}}
console.log('froze',names.length)})();
