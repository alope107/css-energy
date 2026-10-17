// node perf3.js page.html : chaos fps (first 6 s), time to settle, idle fps, drag fps (tower top box), grab-still fps
const {launch,open,arena,countFrames}=require('./lib/physics');
(async()=>{const b=await launch();
for(const f of process.argv.slice(2)){
const p=await open(b,f,{viewport:{width:1000,height:900}});
const fpsFor=ms=>countFrames(p,ms).then(n=>n*1000/ms);
const chaos=[];for(let i=0;i<6;i++)chaos.push((await fpsFor(1000)).toFixed(0));
let settle=-1;for(let i=0;i<40;i++){const cn=await p.evaluate(()=>getComputedStyle((document.querySelector('[id$=LN]')||document.querySelector('[id$=L0]'))).containerName);if(cn==='q'){settle=6+i*0.5;break}await p.waitForTimeout(500)}
const idle=(await fpsFor(1500)).toFixed(0);
const {proj}=await arena(p);
const [bx,by]=proj([70,-145,10]);await p.mouse.move(bx,by);await p.mouse.down();
let k=0;const dr=fpsFor(3000);const st=Date.now();while(Date.now()-st<3000){await p.mouse.move(bx+80*Math.sin(k/7),by-60-40*Math.cos(k/5));k++;await p.waitForTimeout(16)}const drag=(await dr).toFixed(0);
const still=(await fpsFor(1500)).toFixed(0);await p.mouse.up();
console.log(f.padEnd(18),'chaos',chaos.join(' '),'| settled',settle,'s | idle',idle,'| drag',drag,'| hold',still);await p.close()}
await b.close()})();
