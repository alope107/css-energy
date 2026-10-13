// node tools/transcheck.js page.html [ms=5000] [delayMs=1000] : continuity check for transform transitions (harness only)
// Logs every CSSTransition on `transform` created during the window. When a transition replaces a running one, it
// should start where the old one was at that moment; a start somewhere else is a visible jump. Reports the jumps
// (translation distance, px) and exits 1 if any exceeds TOL (default 2 px).
// Static screenshots and frame counts can't show this: the page looks right whenever it is at rest.
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:900}});
// --selftest-ok: a fixture script retargets the transition every 250 ms (must pass).
// --selftest-bad: the fixture snaps the element back to the origin before each retarget, so every transition
// restarts away from where the running one was (must fail). When body poses were transitioned (a dead end, docs/HISTORY.md),
// transitions on .bd restarted from the pose's base value (the spawn point) instead of the animated pose; a minimal page with an
// ancestor's view-timeline-animated custom property did not reproduce that.
const FIX={'--selftest-ok':`<style>#x{width:20px;height:20px;background:red;transition:transform 250ms linear}</style><div id=x></div>
<script>let k=0;setInterval(()=>{k++;x.style.transform='translate('+(k*37%300)+'px,'+(k*53%200)+'px)'},250)</script>`,
 '--selftest-bad':`<style>#x{width:20px;height:20px;background:red;transition:transform 250ms linear}</style><div id=x></div>
<script>let k=0;setInterval(()=>{k++;x.style.transition='none';x.style.transform='translate(0px,0px)';x.offsetWidth;
x.style.transition='';x.style.transform='translate('+(100+k*37%200)+'px,'+(50+k*53%150)+'px)'},250)</script>`};
if(FIX[process.argv[2]])await p.setContent('<!doctype html>'+FIX[process.argv[2]]);
else await p.goto(require('url').pathToFileURL(require('path').resolve(process.argv[2])).href);
await p.waitForTimeout(+(process.argv[4]||1000));
const r=await p.evaluate(ms=>new Promise(res=>{const seen=new WeakSet(),last=new Map(),jumps=[];let n=0,fr=0;const t0=performance.now();
 const T=s=>{const m=new DOMMatrix(s);return [m.m41,m.m42,m.m43]};
 const name=el=>el.id?'#'+el.id:el.tagName.toLowerCase()+'.'+[...el.classList].join('.');
 (function f(){fr++;
  for(const a of document.getAnimations()){if(!(a instanceof CSSTransition)||a.transitionProperty!=='transform'||seen.has(a))continue;seen.add(a);n++;
   const el=a.effect.target,k=a.effect.getKeyframes(),from=T(k[0].transform),to=T(k[k.length-1].transform);
   const tm=a.effect.getTiming(),cur={start:a.startTime??document.timeline.currentTime,dur:+tm.duration,delay:+tm.delay||0,from,to};
   const old=last.get(el);
   if(old){const q=Math.min(1,Math.max(0,(cur.start-old.start-old.delay)/old.dur));   // linear easing assumed
    const at=old.from.map((v,i)=>v+(old.to[i]-v)*q),d=Math.hypot(...at.map((v,i)=>v-from[i]));
    if(d>0.01)jumps.push({el:name(el),d,at:at.map(v=>+v.toFixed(1)),from:from.map(v=>+v.toFixed(1)),to:to.map(v=>+v.toFixed(1))})}
   last.set(el,cur)}
  if(performance.now()-t0<ms)requestAnimationFrame(f);else res({fr,n,jumps})})()}),+(process.argv[3]||5000));
const TOL=+(process.env.TOL||2),big=r.jumps.filter(j=>j.d>TOL).sort((a,b)=>b.d-a.d);
console.log(`${process.argv[2]}: ${r.fr} main frames, ${r.n} transform transitions, ${r.jumps.length} restarts off the running value, ${big.length} over ${TOL} px` +
  (big.length?`, max ${big[0].d.toFixed(1)} px`:''));
for(const j of big.slice(0,+(process.env.SHOW||5)))console.log(`  ${j.el}: was at ${j.at}, restarted from ${j.from} toward ${j.to} (${j.d.toFixed(1)} px)`);
await b.close();process.exit(big.length?1:0)})();
