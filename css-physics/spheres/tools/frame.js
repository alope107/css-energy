// node spheres/tools/frame.js page.html [delay_ms=1500] [dur_ms=1500]
// Where a frame's main-thread time goes. A live step frame has two style passes: the step pass (the clock moved: #LT,
// the activity flags, the solver, the register writes) and the hold pass that follows layout (the register timelines
// moved: the readback chain, the render, the register holds). They are told apart by element count (the hold pass
// restyles the readback groups and the render as well). Prints one line and a JSON line (for ../shared/js/ab.js -p).
// PRESS=x,y holds the pointer down at page coordinates x,y during the measurement.
const {launch,open,record,countFrames,median}=require('../../tools/lib/physics');
const [page,DELAY='1500',DUR='1500']=process.argv.slice(2);
(async()=>{const b=await launch();const p=await open(b,page,{viewport:{width:1000,height:900}});
await p.waitForTimeout(+DELAY);
if(process.env.PRESS){const [x,y]=process.env.PRESS.split(',').map(Number);await p.mouse.move(x,y);await p.mouse.down()}
const dur=+DUR;
const {events:ev,result:fr}=await record(p,{categories:'devtools.timeline,blink,disabled-by-default-devtools.timeline'},()=>countFrames(p,dur));
const X0=ev.filter(e=>e.ph==='X');
// the renderer's main thread: the one that runs the style passes
const cnt={};for(const e of X0)if(e.name==='UpdateLayoutTree'){const k=e.pid+':'+e.tid;cnt[k]=(cnt[k]||0)+1}
const main=Object.entries(cnt).sort((a,b)=>b[1]-a[1])[0][0];
const X=X0.filter(e=>e.pid+':'+e.tid===main);
const sum=n=>X.filter(e=>e.name===n).reduce((a,e)=>a+e.dur,0)/1000;
const ult=X.filter(e=>e.name==='UpdateLayoutTree').map(e=>({d:e.dur/1000,n:(e.args&&e.args.elementCount)||0})).filter(e=>e.n>2);
const counts=[...new Set(ult.map(e=>e.n))].sort((a,b)=>a-b);
// two clusters by element count: split at the largest gap
let cut=counts[counts.length-1];let gap=0;for(let i=1;i<counts.length;i++)if(counts[i]-counts[i-1]>gap){gap=counts[i]-counts[i-1];cut=counts[i]}
const step=ult.filter(e=>e.n<cut),hold=ult.filter(e=>e.n>=cut);
const per=v=>v/fr;
const o={fps:+(fr/dur*1000).toFixed(1),frameMs:+(dur/fr).toFixed(1),
 stepMs:+median(step.map(e=>e.d)).toFixed(2),stepEl:step.length?step[0].n:0,stepPerFrame:+(step.length/fr).toFixed(2),
 holdMs:+median(hold.map(e=>e.d)).toFixed(2),holdEl:hold.length?hold[0].n:0,holdPerFrame:+(hold.length/fr).toFixed(2),
 styleF:+per(sum('UpdateLayoutTree')).toFixed(2),animateF:+per(sum('PageAnimator::serviceScriptedAnimations')).toFixed(2),
 layoutF:+per(sum('Layout')).toFixed(2),prePaintF:+per(sum('PrePaint')).toFixed(2),paintF:+per(sum('Paint')).toFixed(2),
 layerizeF:+per(sum('Layerize')).toFixed(2),commitF:+per(sum('LocalFrameView::pushPaintArtifactToCompositor')).toFixed(2),
 mainF:+per(X.filter(e=>e.name==='RunTask').reduce((a,e)=>a+e.dur,0)/1000).toFixed(2)};
console.log(`${page.padEnd(30)} fps ${o.fps} | step ${o.stepMs} ms (${o.stepEl} el, ${o.stepPerFrame}/fr) | hold ${o.holdMs} ms (${o.holdEl} el, ${o.holdPerFrame}/fr) | per frame: style ${o.styleF} animate ${o.animateF} layout ${o.layoutF} prepaint ${o.prePaintF} paint ${o.paintF} layerize ${o.layerizeF} commit ${o.commitF} main ${o.mainF}`);
console.log(JSON.stringify(o));await b.close()})();
