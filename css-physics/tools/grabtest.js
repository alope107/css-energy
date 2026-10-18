// node tools/grabtest.js page.html [body…] : regression test: dragging one body must not move any other (exit 1 on failure)
// PLAIN single-engine page. For each body k (default: nine bodies spread over the index range, plus 0 itself, GRAB_ROUNDS
// times, 3 by default), reloads the page, sets gravity to 0, wakes every body (field page: a short shake; otherwise the
// rain scene, whose bodies start awake in mid-air), presses on body k and drags it. Checks that the press picked a body
// (k, or one in front of it; a press that picks nothing is skipped, and fewer than 3 picks fail) and that, while it is
// held, no other body in free flight changes velocity: with no gravity a free body keeps its velocity, so any
// acceleration means a grab force leaked to another body. (The bug this guards: body 0's grab block was gated by
// style(--GIr), true whenever anything was held, so every drag also pulled body 0.) Free flight is rare in the tray, so a
// press tests few bodies: one in seven caught that bug put back (BOOLQ=1 without the _MULTI guard), and 30 presses miss
// it about 1% of the time.
const {launch,open,bodyInfo,arena}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2];const src=fs.readFileSync(f,'utf8');
const info=bodyInfo(src);const N=info.length;
const ks=process.argv.length>3?process.argv.slice(3).map(Number):Array.from({length:+(process.env.GRAB_ROUNDS||3)},()=>
 [...new Set([...Array.from({length:9},(_,j)=>1+Math.floor(j*(N-1)/9)),0])]).flat();
const b=await launch();let fail=0,nheld=0;
for(const k of ks){
 const p=await open(b,f,{viewport:{width:1000,height:900}});
 await p.waitForTimeout(300);await p.click('label[for=g-zero]');await p.waitForTimeout(100);
 // field page (SCENE=field FIELD_GAP=30: bodies spread out, best for this test): shake wakes every body and kicks it
 // into a slow drift; otherwise restart in the rain scene, whose bodies start awake in mid-air
 // (a short shake: the kick accelerates every body for as long as the button is down, and a 150 ms press sent them
 // flying at ~400 px/s into the ceiling and each other; one pass of it wakes them all)
 const press=async(sel,ms)=>{const lb=await p.locator(sel).boundingBox();await p.mouse.move(lb.x+lb.width/2,lb.y+lb.height/2);await p.mouse.down();await p.waitForTimeout(ms);await p.mouse.up()};
 if(/id="lb-field"/.test(src))await press('#shake',+(process.env.SHAKE_MS||50));else await press('#lb-rain',150);
 const st=()=>p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));const g=n=>+c.getPropertyValue('--'+n);
  // near flags from the broadphase on #L0 (pairs np<a>_<b>, planes nw<i><F|C|X|Z>): a body with none is in free motion
  const l0=getComputedStyle(document.getElementById('L0'));const fl=n=>+l0.getPropertyValue('--'+n)||0;
  const wall=Array.from({length:N},(_,i)=>['F','C','X','Z'].some(q=>fl('nw'+i+q)));
  const pair=Array.from({length:N},(_,i)=>Array.from({length:N},(_,j)=>j!==i&&fl('np'+Math.min(i,j)+'_'+Math.max(i,j))).some(Boolean));
  return {GI:g('GI'),wall,pair,B:Array.from({length:N},(_,i)=>[g('X'+i),g('Y'+i),g('Z'+i),g('VX'+i),g('VY'+i),g('VZ'+i)])}},N);
 await p.waitForTimeout(400);const s0=await st();
 const {proj}=await arena(p);
  // aim at the body's current position; a press that picks nothing (the body drifted) is released and retried
  let bx,by;for(let tr=0;tr<4;tr++){const cur=tr?await st():s0;const pk=cur.B[k];[bx,by]=proj([pk[0],pk[1],pk[2]]);
   await p.mouse.move(bx,by);await p.mouse.down();await p.waitForTimeout(60);const g0=Math.round((await st()).GI);
   if(g0>=1&&g0<=N)break;await p.mouse.up();await p.waitForTimeout(120)}
 const samples=[];let gi=0;
 for(let t=0;t<20;t++){await p.mouse.move(bx+12*t,by-4*t);await p.waitForTimeout(30);const s=await st();s.ms=Date.now();gi=Math.max(gi,s.GI);samples.push(s)}
 await p.mouse.up();
 // Velocity change between consecutive samples of every other body in free flight: no near flag, and its bounding sphere
 // clear of the tray and of every other body by 5 px plus the distance either can travel between the two samples
 // (samples are 100-200 ms apart: each read waits for the page). (The flake this fixes: with a 5 px margin alone, a body
 // the shake kicked up at 300 px/s hit the ceiling between two samples it was 2 px clear in, and its bounce read as a
 // leak.)
 const R=info.map(bi=>bi.k==='sph'?bi.r:Math.hypot(...bi.h));
 const sp=(B,i)=>Math.hypot(B[i][3],B[i][4],B[i][5]);
 const free=(s,i,dt)=>{const B=s.B,[x,y,z]=B[i],r=R[i]+5+sp(B,i)*dt;return !s.pair[i]&&
  B.every((o,j)=>j===i||Math.hypot(o[0]-x,o[1]-y,o[2]-z)>r+R[j]+sp(B,j)*dt)};
 const tray=(s,i,dt)=>{const B=s.B,[x,y,z]=B[i],r=R[i]+5+sp(B,i)*dt;return !s.wall[i]&&y+r<0&&y-r>-280&&Math.abs(x)+r<280&&Math.abs(z)+r<180};
 const held=Math.round(gi)-1;let worst=[0,-1],checked=0;
 for(let t=1;t<samples.length;t++){const a=samples[t-1].B,c=samples[t].B;if(Math.round(samples[t].GI)!==held+1)continue;
  // (the longest interval around this pair, in s)
  const dt=Math.max(...[t-1,t,t+1].filter(u=>u>=1&&samples[u]).map(u=>samples[u].ms-samples[u-1].ms))/1000;
  for(let i=0;i<N;i++){if(i===held)continue;
   // (a contact between samples can show its near flag one sample late: require none from t-2 to t+1)
   const win=[t-2,t-1,t,t+1].filter(u=>samples[u]);
   if(!win.every(u=>free(samples[u],i,dt)&&tray(samples[u],i,dt)))continue;
   checked++;const dv=Math.hypot(c[i][3]-a[i][3],c[i][4]-a[i][4],c[i][5]-a[i][5]);if(dv>worst[0])worst=[dv,i]}}
 const picked=held>=0&&held<N;const ok=!picked||worst[0]<5;if(picked)nheld++;
 console.log(`${!picked?'SKIP':ok?'PASS':'FAIL'} ${f} aim at body ${k}: ${picked?'held body '+held:'nothing picked (GI '+gi+')'}, largest velocity change of another free body ${worst[0].toFixed(1)} px/s${worst[1]>=0?' (body '+worst[1]+')':''} (${checked} body-steps checked)`);
 if(!ok)fail=1;await p.close()}
if(nheld<3){console.log(`FAIL ${f}: only ${nheld} presses picked a body (need 3)`);fail=1}
await b.close();process.exit(fail)})();
