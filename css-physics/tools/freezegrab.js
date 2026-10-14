// node freezegrab.js src.html settle_ms out.html : settle, grab the stack top, wiggle, then snapshot
// registers + pointer into a static page that keeps --att:1 (a frozen grab)
const {launch,open,arena,vars,registerNames,bakeRegisters}=require('./lib/physics');const fs=require('fs');
(async()=>{const [src,ms,out]=process.argv.slice(2);
const s0=fs.readFileSync(src,'utf8');const names=registerNames(s0);
const b=await launch();
const p=await open(b,src,{viewport:{width:1000,height:900}});await p.waitForTimeout(+ms);
const {proj}=await arena(p);
// BODY=k grabs body k wherever it is (read from the state registers); TOWER the tower's top box; default the stack's
const at=process.env.BODY!==undefined?await p.evaluate(i=>{const c=getComputedStyle(document.getElementById('LS'));return ['X','Y','Z'].map(k=>+c.getPropertyValue('--'+k+i))},+process.env.BODY):(process.env.TOWER?[70,-145,10]:[-60,-145,0]);
const [bx,by]=proj(at);await p.mouse.move(bx,by);await p.mouse.down();
for(let k=0;k<40;k++){await p.mouse.move(bx+60*Math.sin(k/6),by+40*Math.cos(k/5)-Math.min(k,40)*2);await p.waitForTimeout(16)}
const vals=await vars(p,'#LS',names);
const ptr=await p.evaluate(()=>{const c=getComputedStyle(document.querySelector('.ptr'));return ['sx','sy','yaw'].map(n=>c.getPropertyValue('--'+n))});
await b.close();
let s=bakeRegisters(s0,names,vals);
s=s.replace('</style>',`#app{--att:1!important}.ptr{animation:none!important;--sx:${ptr[0]}!important;--sy:${ptr[1]}!important;--yaw:${ptr[2]}!important}</style>`);
fs.writeFileSync(out,s);console.log('froze grab',ptr.join(','),'GI',vals[names.indexOf('GI')])})();
