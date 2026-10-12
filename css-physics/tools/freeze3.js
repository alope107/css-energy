// node tools/freeze3.js src.html ms out_prefix tgt.html...  (writes <dir of tgt>/<prefix>_<tgt name>) [env GRAB=x,y to hold a grab while freezing]
// snapshot the state registers of src at ms and bake them into each target as constants with a tiny
// wobble (so every dependent prop recomputes every frame while all gates stay put)
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [src,ms,pre,...tgts]=process.argv.slice(2);
const s0=fs.readFileSync(src,'utf8');const names=[...s0.matchAll(/@keyframes q\d+\{from\{--([A-Za-z0-9_]+):/g)].map(m=>m[1]);
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:900}});await p.goto(require('url').pathToFileURL(require('path').resolve(src)).href);await p.waitForTimeout(+ms);
const vals=await p.evaluate((names)=>{const c=getComputedStyle(document.getElementById('LS'));return names.map(n=>c.getPropertyValue('--'+n))},names);
await b.close();
for(const t of tgts){let s=fs.readFileSync(t,'utf8');
s=s.replace(/#LS\{\s*animation-name:[^;]*;\s*animation-duration:[^;]*;\s*animation-iteration-count:[^;]*;\s*animation-timing-function:[^;]*;\s*animation-fill-mode:[^;]*;\s*animation-timeline:[^;]*;/,'#LS{animation:clk2 100s linear infinite;');
if(!s.includes('#LS{animation:clk2'))throw new Error('LS pattern');
const asleep=new Set();names.forEach((n,i)=>{const m=n.match(/^SC(\d+)$/);if(m&&+vals[i]>45&&process.env.ONLYAWAKE)asleep.add(m[1])});
const consts=names.map((n,i)=>{if(n==='TP'||n==='DB')return '';const bi=(n.match(/^[A-Z]+(\d+)$/)||[])[1];if(/^(SC\d+|GI|GT|GYP)$/.test(n)||(bi!==undefined&&asleep.has(bi)))return `--${n}:${vals[i]};`;return `--${n}:calc(${vals[i]} + 0.0000001 * sin(var(--now2) * 50));`}).join('');
s=s.replace(/(#LS\{animation:clk2[^}]*)\}/,`$1;${consts}}`);
s=s.replace('<style>',"<style>@property --now2{syntax:'<number>';inherits:false;initial-value:0}@keyframes clk2{from{--now2:0}to{--now2:100}}");
s=s.replace(/(#w\d+\{)animation-name:[^;]*;animation-timeline:[^;]*;/g,'$1');
{const path=require('path');fs.writeFileSync(path.join(path.dirname(t),pre+'_'+path.basename(t)),s)}}
console.log('froze',names.length)})();
