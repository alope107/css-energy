// grab a body in a settled page, then census matched blocks (by category) and awake count
const {launch,open,arena,record,countFrames,aggregate,durations}=require('./lib/physics');const fs=require('fs');
(async()=>{const f=process.argv[2];const s=fs.readFileSync(f,'utf8');
const TOK=/var\(--[A-Za-z0-9_]+|-?\d+\.?\d*(?:e-?\d+)?|[+*\/]|(?<=\s)-(?=\s)|[a-z]+\(/g;
const blocks=[...s.matchAll(/@container (?:b\d+ )?style\(--([A-Za-z0-9_]+): (\d+)\)\{#L(\d+)\{([^}]*)\}\}/g)].map(m=>({g:m[1],v:+m[2],l:+m[3],t:(m[4].match(TOK)||[]).length,n:m[4].split(';--').length}));
const b=await launch();
const p=await open(b,f,{viewport:{width:1000,height:900}});await p.waitForTimeout(+(process.env.SETTLE||10000));
const {proj}=await arena(p);
const [bx,by]=proj(process.env.TOWER?[70,-145,10]:[-60,-145,0]);await p.mouse.move(bx,by);await p.mouse.down();
for(let k=0;k<40;k++){await p.mouse.move(bx+60*Math.sin(k/6),by+40*Math.cos(k/5)-Math.min(k,40)*2);await p.waitForTimeout(16)}
const {events:ev,result:fr}=await record(p,{},()=>countFrames(p,1500));
const agg=aggregate(ev);console.log(Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,12).map(([k,v])=>k+':'+v.n+'/'+v.t.toFixed(0)).join('  '));const u=durations(ev,'UpdateLayoutTree');u.sort((a,b)=>a-b);
console.log('frames',fr,'passes',u.length,'median',u[u.length>>1].toFixed(1),'max',u[u.length-1].toFixed(1),'sum/frame',(u.reduce((a,b)=>a+b,0)/fr).toFixed(1));
const q={};for(const x of blocks){(q[x.l]=q[x.l]||new Set()).add(x.g)}
const act=await p.evaluate(q=>{const o={};for(const [l,gs] of Object.entries(q)){const el=(document.getElementById(+l?'L'+(l-1):'LT')||document.getElementById('LS'));const c=getComputedStyle(el);for(const g of gs)o[g+'|'+l]=+c.getPropertyValue('--'+g)}
 const ls=getComputedStyle(document.getElementById('LS'));let aw=0;for(let i=0;i<64;i++)if(+ls.getPropertyValue('--aw'+i)==1)aw++;o.__aw=aw;o.__cn=getComputedStyle(document.getElementById('LN')||document.getElementById('L0')).containerName;return o},Object.fromEntries(Object.entries(q).map(([k,v])=>[k,[...v]])));
const cat={};let nb=0;
for(const x of blocks){if(act[x.g+'|'+x.l]!==x.v)continue;nb++;const lc=x.l<2?'L'+x.l:'B';const k=(x.g.replace(/\d+/g,'#')+'@'+lc);const c=cat[k]=cat[k]||{n:0,p:0,t:0};c.n++;c.p+=x.n;c.t+=x.t}
const ms=c=>(c.p*2+c.t*0.4)/1000;let tot=0;
for(const [k,c] of Object.entries(cat).sort((a,b)=>ms(b[1])-ms(a[1])).slice(0,14)){tot+=ms(c);console.log(k.padEnd(16),'blocks',String(c.n).padStart(4),'props',String(c.p).padStart(6),'tok',String(c.t).padStart(7),'model',ms(c).toFixed(2))}
console.log('awake',act.__aw,'names',act.__cn,'matched blocks',nb);await p.mouse.up();await b.close()})();
