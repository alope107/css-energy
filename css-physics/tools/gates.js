const {launch,open}=require('./lib/physics');
(async()=>{const b=await launch();
const p=await open(b,process.argv[2],{viewport:{width:1000,height:800}});
const N=+process.argv[3];
for(const t of process.argv[4].split(',')){await p.waitForTimeout(+t);
console.log(t, await p.evaluate(N=>{const els=[...document.querySelectorAll('[id^=L]')].filter(e=>/^L\d+$/.test(e.id));
const res={np:0,tcp:0,ov:0,uA:0};const seen={};
for(const e of els){const c=getComputedStyle(e);
 for(let a=0;a<N;a++)for(let b=a+1;b<N;b++){for(const [k,n] of [['np','--np'+a+'_'+b],['tcp','--tcp'+a+'_'+b],['ov','--p'+a+'_'+b+'ov'],['uA','--p'+a+'_'+b+'uA']]){if(seen[n])continue;const v=c.getPropertyValue(n).trim();if(v&&v!=='0'){seen[n]=1;res[k]++}}}}
return JSON.stringify(res)+' levels '+els.length},N))}
await b.close()})();
