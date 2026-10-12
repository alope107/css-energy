// grab a body in a settled page, then census matched blocks (by category) and awake count
const {chromium}=require('playwright');const fs=require('fs');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
(async()=>{const f=process.argv[2];const s=fs.readFileSync(f,'utf8');
const TOK=/var\(--[A-Za-z0-9_]+|-?\d+\.?\d*(?:e-?\d+)?|[+*\/]|(?<=\s)-(?=\s)|[a-z]+\(/g;
const blocks=[...s.matchAll(/@container (?:b\d+ )?style\(--([A-Za-z0-9_]+): (\d+)\)\{#L(\d+)\{([^}]*)\}\}/g)].map(m=>({g:m[1],v:+m[2],l:+m[3],t:(m[4].match(TOK)||[]).length,n:m[4].split(';--').length}));
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:900}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);await p.waitForTimeout(+(process.env.SETTLE||10000));
const ar=await p.locator('.arena').boundingBox();const sc=ar.width/VW;
const proj=([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
 const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,k=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*k*sc, ar.y+ar.height/2+y3*k*sc]};
const [bx,by]=proj(process.env.TOWER?[70,-145,10]:[-60,-145,0]);await p.mouse.move(bx,by);await p.mouse.down();
for(let k=0;k<40;k++){await p.mouse.move(bx+60*Math.sin(k/6),by+40*Math.cos(k/5)-Math.min(k,40)*2);await p.waitForTimeout(16)}
const cdp=await p.context().newCDPSession(p);const ev=[];cdp.on('Tracing.dataCollected',d=>ev.push(...d.value));
await cdp.send('Tracing.start',{categories:'devtools.timeline',transferMode:'ReportEvents'});
const fr=await p.evaluate(d=>new Promise(r=>{let n=0;const t0=performance.now();(function f(){n++;if(performance.now()-t0<d)requestAnimationFrame(f);else r(n)})()}),1500);
const done=new Promise(r=>cdp.once('Tracing.tracingComplete',r));await cdp.send('Tracing.end');await done;
const agg={};for(const e of ev){if(e.ph!=='X')continue;const a=agg[e.name]=agg[e.name]||{n:0,t:0};a.n++;a.t+=e.dur/1000}console.log(Object.entries(agg).sort((a,b)=>b[1].t-a[1].t).slice(0,12).map(([k,v])=>k+':'+v.n+'/'+v.t.toFixed(0)).join('  '));const u=ev.filter(e=>e.ph==='X'&&e.name==='UpdateLayoutTree').map(e=>e.dur/1000);u.sort((a,b)=>a-b);
console.log('frames',fr,'passes',u.length,'median',u[u.length>>1].toFixed(1),'max',u[u.length-1].toFixed(1),'sum/frame',(u.reduce((a,b)=>a+b,0)/fr).toFixed(1));
const q={};for(const x of blocks){(q[x.l]=q[x.l]||new Set()).add(x.g)}
const act=await p.evaluate(q=>{const o={};for(const [l,gs] of Object.entries(q)){const el=(document.getElementById(+l?'L'+(l-1):'LT')||document.getElementById('LS'));const c=getComputedStyle(el);for(const g of gs)o[g+'|'+l]=+c.getPropertyValue('--'+g)}
 const ls=getComputedStyle(document.getElementById('LS'));let aw=0;for(let i=0;i<64;i++)if(+ls.getPropertyValue('--aw'+i)==1)aw++;o.__aw=aw;o.__cn=getComputedStyle(document.getElementById('L0')).containerName;return o},Object.fromEntries(Object.entries(q).map(([k,v])=>[k,[...v]])));
const cat={};let nb=0;
for(const x of blocks){if(act[x.g+'|'+x.l]!==x.v)continue;nb++;const lc=x.l<2?'L'+x.l:'B';const k=(x.g.replace(/\d+/g,'#')+'@'+lc);const c=cat[k]=cat[k]||{n:0,p:0,t:0};c.n++;c.p+=x.n;c.t+=x.t}
const ms=c=>(c.p*2+c.t*0.4)/1000;let tot=0;
for(const [k,c] of Object.entries(cat).sort((a,b)=>ms(b[1])-ms(a[1])).slice(0,14)){tot+=ms(c);console.log(k.padEnd(16),'blocks',String(c.n).padStart(4),'props',String(c.p).padStart(6),'tok',String(c.t).padStart(7),'model',ms(c).toFixed(2))}
console.log('awake',act.__aw,'names',act.__cn,'matched blocks',nb);await p.mouse.up();await b.close()})();
