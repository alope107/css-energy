// node tools/overlaycheck.js page.html : regression test: the grab overlay (ring, pin, tether) follows the drag (exit 1 on failure)
// PLAIN single-engine page. Presses on a body, drags it, then holds still, and on every frame checks: the ring is centred
// on the hovered cell of the pointer grid (the pointer is that cell's centre) and its size is 16 units (--u: the arena's width / VW); the pin keeps its 8 px size and stays in the
// arena; the tether's box spans from the pin's centre to the ring's centre. (The bug this guards: in Firefox the overlay
// used --u unregistered, so its cqw resolved against #LM, the Firefox-only size container whose size changes every
// frame, and the ring, pin and tether jumped around while the drag itself worked.)
const {launch,open,bodyInfo,arena}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2];const src=fs.readFileSync(f,'utf8');const info=bodyInfo(src);
if(!info){console.error('no BODYINFO: build with COUNTS=<n> PLAIN=1');process.exit(2)}
const VW=+(src.match(/\.view\{[^}]*width:(\d+)px/)||[])[1]||900;
const b=await launch();const p=await open(b,f,{viewport:{width:1000,height:900}});
await p.waitForTimeout(2500);
const {ar,proj}=await arena(p);const u=ar.width/VW;
// aim at the body nearest the camera among the first few (the tower's bottom box in the default scene)
const st=await p.evaluate(()=>{const c=getComputedStyle(document.getElementById('LS'));return [0,1,2,3].map(i=>[+c.getPropertyValue('--X'+i),+c.getPropertyValue('--Y'+i),+c.getPropertyValue('--Z'+i)])});
const [bx,by]=proj(st[0]);
await p.mouse.move(bx,by);await p.mouse.down();
const sample=()=>p.evaluate(()=>new Promise(res=>requestAnimationFrame(()=>{const r=s=>{const e=document.querySelector('#ENG '+s);const x=e.getBoundingClientRect();return {x:x.x,y:x.y,w:x.width,h:x.height,cx:x.x+x.width/2,cy:x.y+x.height/2,op:+getComputedStyle(e).opacity}};
 const h=document.querySelector('.gr>b>i:hover');const hc=h&&h.getBoundingClientRect();
 res({ring:r('.ring'),pin:r('.pin'),tether:r('.tether'),cell:hc&&{cx:hc.x+hc.width/2,cy:hc.y+hc.height/2},GI:Math.round(+getComputedStyle(document.getElementById('LS')).getPropertyValue('--GI'))})})));
const fails=[];let n=0,held=0;
const check=(s,tag)=>{n++;if(!(s.GI>=1&&s.GI<=info.length))return;held++;const mx=s.cell?s.cell.cx:NaN,my=s.cell?s.cell.cy:NaN;
 const bad=m=>fails.length<12&&fails.push(`${tag}: ${m}`);
 if(s.ring.op<0.99)bad(`ring opacity ${s.ring.op}`);
 if(Math.hypot(s.ring.cx-mx,s.ring.cy-my)>3)bad(`ring centre ${s.ring.cx.toFixed(1)},${s.ring.cy.toFixed(1)} vs hovered cell ${mx.toFixed(1)},${my.toFixed(1)}`);
 if(Math.abs(s.ring.w-16*u)>1.5||Math.abs(s.ring.h-16*u)>1.5)bad(`ring size ${s.ring.w.toFixed(1)}x${s.ring.h.toFixed(1)}, expected ${(16*u).toFixed(1)}`);
 if(Math.abs(s.pin.w-8)>0.5||Math.abs(s.pin.h-8)>0.5)bad(`pin size ${s.pin.w.toFixed(1)}x${s.pin.h.toFixed(1)}`);
 if(s.pin.cx<ar.x||s.pin.cx>ar.x+ar.width||s.pin.cy<ar.y||s.pin.cy>ar.y+ar.height)bad(`pin outside the arena at ${s.pin.cx.toFixed(0)},${s.pin.cy.toFixed(0)}`);
 const t=s.tether,x0=Math.min(s.pin.cx,s.ring.cx),x1=Math.max(s.pin.cx,s.ring.cx),y0=Math.min(s.pin.cy,s.ring.cy),y1=Math.max(s.pin.cy,s.ring.cy);
 if(Math.abs(t.x-x0)>4||Math.abs(t.x+t.w-x1)>4||Math.abs(t.y-y0)>4||Math.abs(t.y+t.h-y1)>4)
  bad(`tether box ${t.x.toFixed(0)},${t.y.toFixed(0)} ${t.w.toFixed(0)}x${t.h.toFixed(0)} vs pin→ring ${x0.toFixed(0)},${y0.toFixed(0)}–${x1.toFixed(0)},${y1.toFixed(0)}`)};
for(let k=0;k<25;k++){await p.mouse.move(bx+6*k,by-3*k);check(await sample(),`drag ${k}`)}
for(let k=0;k<40;k++)check(await sample(),`hold ${k}`);
await p.mouse.up();await b.close();
if(held<30)fails.push(`only ${held} of ${n} frames held a body`);
console.log((fails.length?'FAIL ':'PASS ')+f,`${held}/${n} frames held`,fails.length?'\n  '+fails.join('\n  '):'');process.exit(fails.length?1:0)})();
