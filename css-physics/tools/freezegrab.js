// node freezegrab.js src.html settle_ms out.html : settle, grab the stack top, wiggle, then snapshot
// registers + pointer into a static page that keeps --att:1 (a frozen grab)
const {chromium}=require('playwright');const fs=require('fs');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
(async()=>{const [src,ms,out]=process.argv.slice(2);
const s0=fs.readFileSync(src,'utf8');const names=[...s0.matchAll(/@keyframes q\d+\{from\{--([A-Za-z0-9_]+):/g)].map(m=>m[1]);
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:900}});await p.goto(require('url').pathToFileURL(require('path').resolve(src)).href);await p.waitForTimeout(+ms);
const ar=await p.locator('.arena').boundingBox();const sc=ar.width/VW;
const proj=([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
 const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,k=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*k*sc, ar.y+ar.height/2+y3*k*sc]};
const [bx,by]=proj(process.env.TOWER?[70,-145,10]:[-60,-145,0]);await p.mouse.move(bx,by);await p.mouse.down();
for(let k=0;k<40;k++){await p.mouse.move(bx+60*Math.sin(k/6),by+40*Math.cos(k/5)-Math.min(k,40)*2);await p.waitForTimeout(16)}
const vals=await p.evaluate((names)=>{const c=getComputedStyle(document.getElementById('LS'));return names.map(n=>c.getPropertyValue('--'+n))},names);
const ptr=await p.evaluate(()=>{const c=getComputedStyle(document.querySelector('.ptr'));return ['sx','sy','yaw'].map(n=>c.getPropertyValue('--'+n))});
await b.close();
let s=s0;
s=s.replace(/#LS\{\s*animation-name:[^;]*;\s*animation-duration:[^;]*;\s*animation-iteration-count:[^;]*;\s*animation-timing-function:[^;]*;\s*animation-fill-mode:[^;]*;\s*animation-timeline:[^;]*;/,'#LS{animation:clk2 100s linear infinite;');
if(!s.includes('#LS{animation:clk2'))throw new Error('LS pattern');
const asleep=new Set();names.forEach((n,i)=>{const m=n.match(/^SC(\d+)$/);if(m&&+vals[i]>45&&process.env.ONLYAWAKE)asleep.add(m[1])});
const consts=names.map((n,i)=>{if(n==='TP'||n==='DB')return '';const bi=(n.match(/^[A-Z]+(\d+)$/)||[])[1];if(/^(SC\d+|GI|GT|GYP)$/.test(n)||(bi!==undefined&&asleep.has(bi)))return `--${n}:${vals[i]};`;return `--${n}:calc(${vals[i]} + 0.0000001 * sin(var(--now2) * 50));`}).join('');
s=s.replace(/(#LS\{animation:clk2[^}]*)\}/,`$1;${consts}}`);
s=s.replace('<style>',"<style>@property --now2{syntax:'<number>';inherits:false;initial-value:0}@keyframes clk2{from{--now2:0}to{--now2:100}}");
s=s.replace(/(#w\d+\{)animation-name:[^;]*;animation-timeline:[^;]*;/g,'$1');
s=s.replace('</style>',`#app{--att:1!important}.ptr{animation:none!important;--sx:${ptr[0]}!important;--sy:${ptr[1]}!important;--yaw:${ptr[2]}!important}</style>`);
fs.writeFileSync(out,s);console.log('froze grab',ptr.join(','),'GI',vals[names.indexOf('GI')])})();
