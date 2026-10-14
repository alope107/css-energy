// node tools/cellcheck.js page.html N [bodyIndex] : drag body k through a (cells-gated) page and, every 100 ms, check that
// every sleeper within reach of an awake body is present (--nb = 1 on #LW, i.e. its name is in --AN), and count how
// many sleepers are present at all. Prints violations (asleep, near an awake body, not present) and the presence rate.
const {launch,open,bodyInfo,arena}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2],N=+process.argv[3],K=+(process.argv[4]||0);
const info=bodyInfo(fs.readFileSync(f,'utf8'));
const R=info.map(b=>b.k==='sph'?b.r:Math.hypot(...b.h));
const b=await launch();
const p=await open(b,f,{viewport:{width:1000,height:900}});
await p.waitForTimeout(2000);
const pos=i=>p.evaluate(i=>{const c=getComputedStyle(document.getElementById('LS'));return ['X','Y','Z'].map(k=>+c.getPropertyValue('--'+k+i))},i);
const {proj}=await arena(p);
const [bx,by]=proj(await pos(K));await p.mouse.move(bx,by);await p.mouse.down();
let worst=[],samples=0,present=0,sleepers=0,viol=0;
const t=Date.now();let k=0;
while(Date.now()-t<4000){await p.mouse.move(bx+90*Math.sin(k/9),by-50-40*Math.cos(k/6));k++;await p.waitForTimeout(16);
 if(k%2)continue;
 const r=await p.evaluate(([N,R])=>{const c=getComputedStyle(document.getElementById('LS')),w=getComputedStyle(document.getElementById('LW'));
  const an=w.containerName;const B=[];for(let i=0;i<N;i++)B.push({p:['X','Y','Z'].map(q=>+c.getPropertyValue('--'+q+i)),v:['VX','VY','VZ'].map(q=>+c.getPropertyValue('--'+q+i)),sc:+c.getPropertyValue('--SC'+i),nb:+w.getPropertyValue('--nb'+i),hx:w.getPropertyValue('--hx'+i),hz:w.getPropertyValue('--hz'+i),named:an.split(' ').includes('b'+i)});
  const out={sleepers:0,present:0,viol:[],an:an.length};
  for(let i=0;i<N;i++){if(B[i].sc<=45)continue;out.sleepers++;if(B[i].named)out.present++;
   for(let j=0;j<N;j++){if(i===j||B[j].sc>45)continue;const d=Math.hypot(...[0,1,2].map(a=>B[i].p[a]-(B[j].p[a]+B[j].v[a]/90)));
    if(d<R[i]+R[j]+3&&!B[i].named){out.viol.push([i,j,d.toFixed(0),B[i].nb,B[i].hx,B[i].hz]);break}}}
  return out},[N,R]);
 samples++;present+=r.present;sleepers+=r.sleepers;viol+=r.viol.length;if(r.viol.length&&worst.length<6)worst.push(JSON.stringify(r.viol.slice(0,3)));}
await p.mouse.up();
console.log(f,`samples ${samples} | sleepers ${(sleepers/samples).toFixed(1)} present ${(present/samples).toFixed(1)} | violations ${viol}`,worst.join(' '));
await b.close()})();
