// node perf3.js page.html : chaos fps (first 6 s), time to settle, idle fps, drag fps (tower top box), grab-still fps
const {chromium}=require('playwright');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
for(const f of process.argv.slice(2)){
const p=await b.newPage({viewport:{width:1000,height:900}});const t0=Date.now();await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);
const fpsFor=ms=>p.evaluate(d=>new Promise(r=>{let n=0;const t=performance.now();(function g(){n++;if(performance.now()-t<d)requestAnimationFrame(g);else r(n*1000/d)})()}),ms);
const chaos=[];for(let i=0;i<6;i++)chaos.push((await fpsFor(1000)).toFixed(0));
let settle=-1;for(let i=0;i<40;i++){const cn=await p.evaluate(()=>getComputedStyle(document.querySelector('[id$=L0]')).containerName);if(cn==='q'){settle=6+i*0.5;break}await p.waitForTimeout(500)}
const idle=(await fpsFor(1500)).toFixed(0);
const ar=await p.locator('.arena').boundingBox();const sc=ar.width/VW;
const proj=([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
 const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,k=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*k*sc, ar.y+ar.height/2+y3*k*sc]};
const [bx,by]=proj([70,-145,10]);await p.mouse.move(bx,by);await p.mouse.down();
let k=0;const dr=fpsFor(3000);const st=Date.now();while(Date.now()-st<3000){await p.mouse.move(bx+80*Math.sin(k/7),by-60-40*Math.cos(k/5));k++;await p.waitForTimeout(16)}const drag=(await dr).toFixed(0);
const still=(await fpsFor(1500)).toFixed(0);await p.mouse.up();
console.log(f.padEnd(18),'chaos',chaos.join(' '),'| settled',settle,'s | idle',idle,'| drag',drag,'| hold',still);await p.close()}
await b.close()})();
