// node experiments/safari/inherit.js [page] [ms]: for each row of inherit.html, the frames in which the child's (and
// grandchild's) value differs from the parent's by more than 1. BROWSER=webkit|safari|firefox as for the tools.
const {launch,open}=require('../../tools/lib/physics');
(async()=>{const f=process.argv[2]||'experiments/safari/inherit.html',T=+(process.argv[3]||3000);
const b=await launch();const p=await open(b,f,{viewport:{width:1000,height:600}});await p.waitForTimeout(300);
const r=await p.evaluate(T=>new Promise(res=>{const rows=[...document.querySelectorAll('.row')];const out={};
 const val=(el,k)=>+getComputedStyle(el).getPropertyValue(k);
 for(const row of rows)out[row.id]={frames:0,stale:0,worst:0,ex:''};
 const t0=performance.now();
 const M=document.querySelector('#M .p');let fr=0;
 function f(){if(M)M.style.setProperty('--x',String((fr++*3)%200));for(const row of rows){const o=out[row.id];o.frames++;
   const k=/[CJ]/.test(row.id)?'--xi':'--x';const pv=val(row.querySelector('.p'),k);
   const kids=[...row.querySelectorAll('.c,.g')].map(e=>(row.id==='E'&&e.classList.contains('c'))||/[JK]/.test(row.id)?val(e,'--y'):val(e,k));
   const d=Math.max(...kids.map(v=>Math.abs(v-pv)));o.worst=Math.max(o.worst,d);if(d>1){o.stale++;if(!o.ex)o.ex=`parent ${pv.toFixed(1)} children ${kids.map(v=>v.toFixed(1))}`}}
  if(performance.now()-t0<T)requestAnimationFrame(f);else res(out)}
 requestAnimationFrame(f)}),T);
console.log(b.version?b.version():'');for(const [k,o] of Object.entries(r))console.log(`${k}: ${o.stale}/${o.frames} frames stale, worst ${o.worst.toFixed(1)} ${o.ex}`);
await b.close()})().catch(e=>{console.error(e.message);process.exit(1)});
