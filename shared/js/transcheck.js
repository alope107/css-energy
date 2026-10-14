// transcheck.js — continuity check for transform transitions (harness only). Run it through a project's wrapper:
//   node tools/transcheck.js page.html [ms=5000] [delayMs=1000]   (css-physics/)
// Logs every CSSTransition on `transform` created during the window. When a transition replaces a running one, it
// should start where the old one was at that moment; a start somewhere else is a visible jump. Reports the jumps
// (translation distance, px) and exits 1 if any exceeds TOL (default 2 px). The distance is to the running transition's path
// within ±SLACK ms (default 17, one frame) of the restart: compositor start times sit a few ms from the main thread's.
// Static screenshots and frame counts can't show this: the page looks right whenever it is at rest.
const {fileUrl}=require('./browser.js');
async function main(B,argv=process.argv.slice(2),{viewport={width:1000,height:900}}={}){const b=await B.launch();
const p=await b.newPage({viewport});
// --selftest-ok: a fixture script retargets the transition every 250 ms (must pass).
// --selftest-bad: the fixture snaps the element back to the origin before each retarget, so every transition
// restarts away from where the running one was (must fail). When body poses were transitioned (a dead end, docs/HISTORY.md),
// transitions on .bd restarted from the pose's base value (the spawn point) instead of the animated pose; a minimal page with an
// ancestor's view-timeline-animated custom property did not reproduce that.
const FIX={'--selftest-ok':`<style>#x{width:20px;height:20px;background:red;transition:transform 250ms linear}</style><div id=x></div>
<script>let k=0;setInterval(()=>{k++;x.style.transform='translate('+(k*37%300)+'px,'+(k*53%200)+'px)'},250)</script>`,
 // --selftest-small: each restart starts 10 px off the running transition's path, across its direction of motion (must fail):
 // the timing slack only absorbs offsets along the path.
 '--selftest-small':`<style>#x{width:20px;height:20px;background:red;transition:transform 250ms linear}</style><div id=x></div>
<script>let k=0,to=[0,0];setInterval(()=>{k++;const m=new DOMMatrix(getComputedStyle(x).transform),c=[m.m41,m.m42],v=[to[0]-c[0],to[1]-c[1]],l=Math.hypot(...v)||1;
x.style.transition='none';x.style.transform='translate('+(c[0]-10*v[1]/l)+'px,'+(c[1]+10*v[0]/l)+'px)';x.offsetWidth;
to=[100+k*37%200,50+k*53%150];x.style.transition='';x.style.transform='translate('+to[0]+'px,'+to[1]+'px)'},250)</script>`,
 '--selftest-bad':`<style>#x{width:20px;height:20px;background:red;transition:transform 250ms linear}</style><div id=x></div>
<script>let k=0;setInterval(()=>{k++;x.style.transition='none';x.style.transform='translate(0px,0px)';x.offsetWidth;
x.style.transition='';x.style.transform='translate('+(100+k*37%200)+'px,'+(50+k*53%150)+'px)'},250)</script>`};
if(FIX[argv[0]])await p.setContent('<!doctype html>'+FIX[argv[0]]);
else await p.goto(fileUrl(argv[0]));
await p.waitForTimeout(+(argv[2]||1000));
const r=await p.evaluate(([ms,SLACK])=>new Promise(res=>{const seen=new WeakSet(),last=new Map(),jumps=[];let n=0,fr=0;const t0=performance.now();
 const T=s=>{const m=new DOMMatrix(s);return [m.m41,m.m42,m.m43]};
 const name=el=>el.id?'#'+el.id:el.tagName.toLowerCase()+'.'+[...el.classList].join('.');
 (function f(){fr++;
  for(const a of document.getAnimations()){if(!(a instanceof CSSTransition)||a.transitionProperty!=='transform'||seen.has(a))continue;seen.add(a);n++;
   const el=a.effect.target,k=a.effect.getKeyframes(),from=T(k[0].transform),to=T(k[k.length-1].transform);
   const tm=a.effect.getTiming(),cur={start:a.startTime??document.timeline.currentTime,dur:+tm.duration,delay:+tm.delay||0,from,to};
   const old=last.get(el);
   if(old){// where the running transition was when this one started (linear easing assumed). The start time comes from
    // the compositor and can sit a few ms from the moment `from` was sampled, so measure the distance from `from` to
    // the stretch of the old path within ±SLACK ms of the start, not to one point: a restart elsewhere is still far.
    const qt=t=>Math.min(1,Math.max(0,(t-old.start-old.delay)/old.dur)),pos=q=>old.from.map((v,i)=>v+(old.to[i]-v)*q);
    const at=pos(qt(cur.start)),A=pos(qt(cur.start-SLACK)),B=pos(qt(cur.start+SLACK));
    const AB=B.map((v,i)=>v-A[i]),L2=AB.reduce((a,v)=>a+v*v,0),u=L2?Math.min(1,Math.max(0,AB.reduce((a,v,i)=>a+v*(from[i]-A[i]),0)/L2)):0;
    const d=Math.hypot(...A.map((v,i)=>v+AB[i]*u-from[i]));
    if(d>0.01)jumps.push({el:name(el),d,at:at.map(v=>+v.toFixed(1)),from:from.map(v=>+v.toFixed(1)),to:to.map(v=>+v.toFixed(1))})}
   last.set(el,cur)}
  if(performance.now()-t0<ms)requestAnimationFrame(f);else res({fr,n,jumps})})()}),[+(argv[1]||5000),+(process.env.SLACK||17)]);
const TOL=+(process.env.TOL||2),big=r.jumps.filter(j=>j.d>TOL).sort((a,b)=>b.d-a.d);
console.log(`${argv[0]}: ${r.fr} main frames, ${r.n} transform transitions, ${r.jumps.length} restarts off the running value, ${big.length} over ${TOL} px` +
  (big.length?`, max ${big[0].d.toFixed(1)} px`:''));
for(const j of big.slice(0,+(process.env.SHOW||5)))console.log(`  ${j.el}: was at ${j.at}, restarted from ${j.from} toward ${j.to} (${j.d.toFixed(1)} px)`);
await b.close();process.exit(big.length?1:0)}
module.exports={main};
if(require.main===module){console.error('run it through a project wrapper: css-physics/tools/transcheck.js');process.exit(2)}
