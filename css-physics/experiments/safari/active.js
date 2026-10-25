// node experiments/safari/active.js [page]: press on each grid of active.html and drag across it in 6 px steps; prints
// after which move (if any) the grid stopped being :active. BROWSER=webkit|safari|firefox as for the tools.
const {launch,open}=require('../../tools/lib/physics');
(async()=>{const f=process.argv[2]||'experiments/safari/active.html';const b=await launch();
const p=await open(b,f,{viewport:{width:600,height:700}});await p.waitForTimeout(300);
console.log(b.version?b.version():'');
for(const id of ['A','B','C','D','E','F','G']){await p.evaluate(id=>document.getElementById(id).scrollIntoView({block:'center'}),id);await p.waitForTimeout(50);const r=await p.locator('#'+id).boundingBox();const x0=r.x+20,y0=r.y+r.height/2;
 await p.mouse.move(x0,y0);await p.waitForTimeout(50);await p.mouse.down();await p.waitForTimeout(80);
 const seq=[];const act=()=>p.evaluate(id=>document.querySelector('#'+id+':active')?1:0,id);seq.push(await act());
 for(let k=1;k<=12;k++){await p.mouse.move(x0+6*k,y0+(k%2));await p.waitForTimeout(40);seq.push(await act())}
 await p.mouse.up();await p.waitForTimeout(80);const lost=seq.indexOf(0);
 console.log(`${id}: ${lost<0?'active through all 12 moves':lost===0?'never active':'lost after move '+lost} [${seq.join('')}]`)}
await b.close()})().catch(e=>{console.error(e.message);process.exit(1)});
