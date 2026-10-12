// census of matched blocks by category for a (frozen or live) page: node cen.js page.html waitms
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const f=process.argv[2];const s=fs.readFileSync(f,'utf8');
const TOK=/var\(--[A-Za-z0-9_]+|-?\d+\.?\d*(?:e-?\d+)?|[+*\/]|(?<=\s)-(?=\s)|[a-z]+\(/g;
const blocks=[...s.matchAll(/@container (?:b\d+ )?style\(--([A-Za-z0-9_]+): (\d+)\)\{#L(\d+)\{([^}]*)\}\}/g)].map(m=>({g:m[1],v:+m[2],l:+m[3],t:(m[4].match(TOK)||[]).length,n:m[4].split(';--').length}));
const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:800}});await p.goto(require('url').pathToFileURL(require('path').resolve(f)).href);await p.waitForTimeout(+process.argv[3]||1000);
const q={};for(const x of blocks){(q[x.l]=q[x.l]||new Set()).add(x.g)}
const act=await p.evaluate(q=>{const o={};for(const [l,gs] of Object.entries(q)){const el=document.getElementById(+l?'L'+(l-1):'LT');const c=getComputedStyle(el);for(const g of gs)o[g+'|'+l]=+c.getPropertyValue('--'+g)}return o},Object.fromEntries(Object.entries(q).map(([k,v])=>[k,[...v]])));
const cat={};let tot=0,nb=0;
for(const x of blocks){if(act[x.g+'|'+x.l]!==x.v)continue;nb++;const lc=x.l<2?'L'+x.l:'B';const k=(x.g.replace(/\d+/g,'#')+'@'+lc);const c=cat[k]=cat[k]||{n:0,p:0,t:0};c.n++;c.p+=x.n;c.t+=x.t}
const ms=c=>(c.p*2+c.t*0.4)/1000;
for(const [k,c] of Object.entries(cat).sort((a,b)=>ms(b[1])-ms(a[1])).slice(0,20)){tot+=ms(c);console.log(k.padEnd(16),'blocks',String(c.n).padStart(4),'props',String(c.p).padStart(6),'tok',String(c.t).padStart(7),'model',ms(c).toFixed(2))}
console.log('matched blocks',nb,'of',blocks.length);await b.close()})();
