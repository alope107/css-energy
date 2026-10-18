// node spheres/tools/snap.js page.html ms out.json — every register's value (the readback properties on #LC) at `ms`
const {launch,open}=require('../../tools/lib/physics');
(async()=>{const b=await launch();const p=await open(b,process.argv[2],{viewport:{width:1000,height:900}});
await p.waitForTimeout(+process.argv[3]);
const v=await p.evaluate(()=>{const css=[...document.styleSheets].flatMap(s=>[...s.cssRules]).map(r=>r.cssText).join('\n');
 const names=[...css.matchAll(/@keyframes q\d+ \{\s*0% \{ --([A-Za-z0-9_]+):/g)].map(m=>m[1]);
 const cs=getComputedStyle(document.querySelector('[id$=LC]'));const o={};for(const n of names)o[n]=parseFloat(cs.getPropertyValue('--'+n));return o});
require('fs').writeFileSync(process.argv[4],JSON.stringify(v));console.log(Object.keys(v).length,'registers');await b.close()})();
