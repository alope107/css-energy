// node tools/floatcheck.js page.html [page2.html …] : regression test for bodies asleep in mid-air (exit 1 on failure)
// For every scene of each PLAIN single-engine page (each multi-engine page's visible engine also works if it is
// PLAIN): selects the scene by clicking its label (the first scene is also checked straight after load, without a
// click), then samples at 0.3, 1.5 and 4 s whether any ASLEEP body (sleep counter > 45) is unsupported: its lowest
// point is more than TOL px above the floor and its bounding sphere doesn't reach another body's. A sleeping body is
// frozen, so one that starts asleep in the air hangs there until something hits it. That bug has come back more
// than once (scene start states leaking between scenes; upper layers starting asleep).
const {launch,open,bodyInfo}=require('./lib/physics');const fs=require('fs');
const TOL=+(process.env.TOL||2);
(async()=>{let fail=0;const b=await launch();
for(const f of process.argv.slice(2)){
const src=fs.readFileSync(f,'utf8');const info=bodyInfo(src);if(!info){console.error(f,'no BODYINFO: build with COUNTS=<n> PLAIN=1');process.exit(2)}const scenes=[...src.matchAll(/id="lb-([a-z]+)"/g)].map(x=>x[1]);
const runs=[[scenes[0],false],...scenes.map(s=>[s,true])];
for(const [sc,click] of runs){
 const p=await open(b,f,{viewport:{width:1000,height:900}});
 // a real press: the label's :active must last through a style pass, or the scene radio flips without the reset
 if(click){await p.waitForTimeout(300);const lb=await p.locator(`#lb-${sc}`).boundingBox();await p.mouse.move(lb.x+lb.width/2,lb.y+lb.height/2);
  await p.mouse.down();await p.waitForTimeout(150);await p.mouse.up()}
 const t0=Date.now();const bad=[];
 for(const at of [300,1500,4000]){await p.waitForTimeout(Math.max(0,at-(Date.now()-t0)));
  const r=await p.evaluate(info=>{const c=getComputedStyle(document.getElementById('LS'));const g=k=>+c.getPropertyValue('--'+k);
   const B=info.map((bi,i)=>{const x=g('X'+i),y=g('Y'+i),z=g('Z'+i),qx=g('QX'+i),qy=g('QY'+i),qz=g('QZ'+i);const w=Math.sqrt(Math.max(0,1-qx*qx-qy*qy-qz*qz));
    let ext,R;if(bi.k==='sph'){ext=R=bi.r}else{const ay=[2*(qx*qy+w*qz),1-2*(qx*qx+qz*qz),2*(qy*qz-w*qx)];ext=ay.reduce((a,v,j)=>a+Math.abs(v)*bi.h[j],0);R=Math.hypot(...bi.h)}
    return {i,x,y,z,ext,R,asleep:g('SC'+i)>45}});
   const out=[];for(const a of B){if(!a.asleep)continue;const gap=-(a.y+a.ext);if(gap<=0)continue;
    const touch=B.some(o=>o!==a&&Math.hypot(a.x-o.x,a.y-o.y,a.z-o.z)<a.R+o.R+1);if(!touch)out.push([a.i,+gap.toFixed(1)])}
   return out},info);
  for(const [i,gap] of r)if(gap>TOL)bad.push(`t=${at}ms body ${i} asleep ${gap}px above the floor, touching nothing`)}
 console.log(`${bad.length?'FAIL':'PASS'} ${f} scene ${sc}${click?' (selected)':' (on load)'}${bad.length?': '+[...new Set(bad)].slice(0,6).join('; '):''}`);
 if(bad.length)fail=1;await p.close()}}
await b.close();process.exit(fail)})();
