// node tools/grabtest.js page.html [body…] : regression test: dragging one body must not move any other (exit 1 on failure)
// PLAIN single-engine page. For each body k (default: nine bodies spread over the index range, plus 0 itself), reloads the page, sets gravity to 0 and switches to the rain scene (every body starts awake, drifting and
// spinning slowly in mid-air), presses on body k and drags it. Checks that the press picked a body (k, or one in front
// of it; a press that picks nothing is skipped, and fewer than 3 picks fail) and that, while it is held, no other body that touches nothing changes velocity: with no gravity a free body keeps its
// velocity, so any acceleration means a grab force leaked to another body. (The bug this guards: body 0's grab block
// was gated by style(--GIr), true whenever anything was held, so every drag also pulled body 0.)
const {chromium}=require('playwright');const fs=require('fs');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
(async()=>{const f=process.argv[2];const src=fs.readFileSync(f,'utf8');
const info=JSON.parse(src.match(/<!--BODYINFO (.*?)-->/)[1]);const N=info.length;
const ks=process.argv.length>3?process.argv.slice(3).map(Number):[...new Set([...Array.from({length:9},(_,j)=>1+Math.floor(j*(N-1)/9)),0])];
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});let fail=0,nheld=0;
for(const k of ks){
 const p=await b.newPage({viewport:{width:1000,height:900}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);
 await p.waitForTimeout(300);await p.click('label[for=g-zero]');await p.waitForTimeout(100);
 // field page (SCENE=field FIELD_GAP=30: bodies spread out, best for this test): shake wakes every body and kicks it
 // into a slow drift; otherwise restart in the rain scene, whose bodies start awake in mid-air
 const press=async sel=>{const lb=await p.locator(sel).boundingBox();await p.mouse.move(lb.x+lb.width/2,lb.y+lb.height/2);await p.mouse.down();await p.waitForTimeout(150);await p.mouse.up()};
 await press(/id="lb-field"/.test(src)?'#shake':'#lb-rain');
 const st=()=>p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));const g=n=>+c.getPropertyValue('--'+n);
  // near flags from the broadphase on #L0 (pairs np<a>_<b>, planes nw<i><F|C|X|Z>): a body with none is in free motion
  const l0=getComputedStyle(document.getElementById('L0'));const fl=n=>+l0.getPropertyValue('--'+n)||0;
  const near=Array.from({length:N},(_,i)=>['F','C','X','Z'].some(q=>fl('nw'+i+q))||Array.from({length:N},(_,j)=>j!==i&&fl('np'+Math.min(i,j)+'_'+Math.max(i,j))).some(Boolean));
  return {GI:g('GI'),near,B:Array.from({length:N},(_,i)=>[g('X'+i),g('Y'+i),g('Z'+i),g('VX'+i),g('VY'+i),g('VZ'+i)])}},N);
 await p.waitForTimeout(400);const s0=await st();
 const ar=await p.locator('.arena').boundingBox();const sc=ar.width/VW;
 const proj=([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
  const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,q=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*q*sc, ar.y+ar.height/2+y3*q*sc]};
  // aim at the body's current position; a press that picks nothing (the body drifted) is released and retried
  let bx,by;for(let tr=0;tr<4;tr++){const cur=tr?await st():s0;const pk=cur.B[k];[bx,by]=proj([pk[0],pk[1],pk[2]]);
   await p.mouse.move(bx,by);await p.mouse.down();await p.waitForTimeout(60);const g0=Math.round((await st()).GI);
   if(g0>=1&&g0<=N)break;await p.mouse.up();await p.waitForTimeout(120)}
 const samples=[];let gi=0;
 for(let t=0;t<20;t++){await p.mouse.move(bx+12*t,by-4*t);await p.waitForTimeout(30);const s=await st();gi=Math.max(gi,s.GI);samples.push(s)}
 await p.mouse.up();
 // velocity change of every other body with no near flag (no contact possible) between consecutive samples
 // and (sphere/sphere and plane flags have no margin) its bounding sphere is 5 px clear of every body and the tray
 const R=info.map(bi=>bi.k==='sph'?bi.r:Math.hypot(...bi.h));
 const clear=(B,i)=>{const [x,y,z]=B[i],r=R[i]+5;return y+r<0&&y-r>-280&&Math.abs(x)+r<280&&Math.abs(z)+r<180&&
  B.every((o,j)=>j===i||Math.hypot(o[0]-x,o[1]-y,o[2]-z)>r+R[j])};
 const held=Math.round(gi)-1;let worst=[0,-1];
 for(let t=1;t<samples.length;t++){const a=samples[t-1].B,c=samples[t].B;if(Math.round(samples[t].GI)!==held+1)continue;
  for(let i=0;i<N;i++){if(i===held)continue;
   // (a contact between samples can show its near flag one sample late: require none from t-2 to t+1)
   if([t-2,t-1,t,t+1].some(u=>samples[u]&&(samples[u].near[i]||!clear(samples[u].B,i))))continue;
   const dv=Math.hypot(c[i][3]-a[i][3],c[i][4]-a[i][4],c[i][5]-a[i][5]);if(dv>worst[0])worst=[dv,i]}}
 const picked=held>=0&&held<N;const ok=!picked||worst[0]<5;if(picked)nheld++;
 console.log(`${!picked?'SKIP':ok?'PASS':'FAIL'} ${f} aim at body ${k}: ${picked?'held body '+held:'nothing picked (GI '+gi+')'}, largest velocity change of another free body ${worst[0].toFixed(1)} px/s${worst[1]>=0?' (body '+worst[1]+')':''}`);
 if(!ok)fail=1;await p.close()}
if(nheld<3){console.log(`FAIL ${f}: only ${nheld} presses picked a body (need 3)`);fail=1}
await b.close();process.exit(fail)})();
