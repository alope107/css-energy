// node tools/xcheck.js page.html [ms] [browser[:noif]...] : do other engines compute what Chrome computes?
// Snapshots the state registers in Chromium (XFROM=webkit|firefox: there) at ms (default 1500), bakes them in as exact constants (out/xcheck_<page>),
// loads that frozen copy in Chromium and in each browser named (default: webkit firefox), and compares every custom
// property and container name on every level (#TS … #L<last>) against Chromium's. ":noif" runs a copy with if( renamed
// iff(, as a browser without if() sees it (Safari before 27.x; it takes the @supports fallback), against Chromium on
// the same copy; so is a browser without if() on the original. Then the fallback itself: Chromium's next state on the
// noif copy against the original's (register offsets). A value differs if it's off by 1e-2 relative to max(1, |value|)
// (XTOL); exit 1 if over 0.1% of them do. Rounding differs between engines (var() of a registered number keeps 6
// significant digits in Chrome and Firefox, 6 decimal places in WebKit, where 1e-8 is 0) and contacts amplify it, to
// about 1e-3 on 16-body piles, and where it flips a gate (a box corner just touching) a few values move by up to 5%;
// a wrong formula is off by O(1) in thousands (Firefox's hypot: 14,000 of 168,000). PLAIN single-engine builds only.
// Real time doesn't matter: the state is static.
const {launchers,open,vars,pollUntil,registerNames,bakeRegisters}=require('./lib/physics');const fs=require('fs'),path=require('path');
// skipped: what follows the clock, not the state; and the pointer, whose resting marker sits a fraction of a pixel apart
// in each engine (#RB passes it on only while grabbing)
const CLOCKED=/^(now2?|raw|avail|NTP|NDB|tk|ffk|TP|DB|sx|sy)$/;
const TOL=+process.env.XTOL||1e-2,FRAC=0.001;
(async()=>{const [f,ms='1500',...bs]=process.argv.slice(2);const specs=bs.length?bs:['webkit','firefox'];
const s0=fs.readFileSync(f,'utf8');const names=registerNames(s0);
const props=[...new Set([...s0.matchAll(/(?:@property |[{;])--([A-Za-z0-9_]+)[{:]/g)].map(m=>m[1]))].filter(n=>!CLOCKED.test(n));
let b=await launchers[process.env.XFROM||'chromium']();let p=await open(b,f,{viewport:{width:1000,height:760}});await p.waitForTimeout(+ms);
const vals=await vars(p,'#LS',names);await b.close();
// (and the clock's own registers out: with TP = 0, DB = 0 the bank is full and every pass steps, --live = 1; read
// from r0 as on a live page, --live and every gate under it flipped from pass to pass with the frame timing)
const frozen=bakeRegisters(s0,names,vals,true).replace('</style>','#LT{animation-name:clk;--TP:0;--DB:0}</style>');
const clockReg=(s0.match(/#(r\d+)\{[^}]*var\(--NTP\)/)||[])[1];
const copy=(tag,s)=>{const o=path.join(path.dirname(f),`xcheck${tag}_${path.basename(f)}`);fs.writeFileSync(o,s);return o};
const pages={'':copy('',frozen),noif:copy('_noif',frozen.replaceAll('if(','iff('))};
const read=async spec=>{const [br,v='']=spec.split(':');const b=await launchers[br]();const p=await open(b,pages[v],{viewport:{width:1000,height:760}});
 // (the frozen state steps once the clock passes half a step (--live): wait for it, however loaded the machine)
 const t=await pollUntil(p,()=>p.evaluate(()=>+getComputedStyle(document.getElementById('LT')).getPropertyValue('--now')>0.3),{interval:200,timeout:60000});
 if(!t.value)throw new Error(`${spec}: the clock didn't start in 60 s`);await p.waitForTimeout(200);const ifs=await p.evaluate(()=>CSS.supports('width: if(style(--x: 1): 1px; else: 2px)'));
 const r=await p.evaluate(props=>Object.fromEntries([...document.querySelectorAll('.lv[id]')].map(e=>{const c=getComputedStyle(e);
  return [e.id,{'container-name':c.containerName,...Object.fromEntries(props.map(n=>['--'+n,c.getPropertyValue('--'+n).trim()]))}]})),props);
 // the next state as written back: each register's offset in its scroller (an undeclared N* leaves it at its static
 // position, which encodes the range's top: the named path relies on it for a sleeping body's sleep counter)
 const regs=await p.evaluate(()=>Object.fromEntries([...document.querySelectorAll('.regs i[id]')].map(e=>{const a=e.getBoundingClientRect(),
  c=e.parentElement.getBoundingClientRect();return [e.id,[a.top-c.top,a.left-c.left]]})));
 const ver=`${br} ${b.version()}`;await b.close();return {ver,r,regs,noif:v==='noif'||!ifs}};
// two values differ by the largest relative difference (to max(1, |x|)) between their numbers, if the text between the
// numbers matches (a '*'-syntax property holds substituted text, `calc(73.2102)`); Infinity if the text differs
const NUM=/[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi;
const differ=(a,c)=>{a=a.replace(/\s+/g,' ');c=String(c).replace(/\s+/g,' ');if(a.replace(NUM,'#')!==c.replace(NUM,'#'))return Infinity;
 const x=a.match(NUM)||[],y=c.match(NUM)||[];return Math.max(0,...x.map((v,i)=>Math.abs(v-y[i])/Math.max(1,Math.abs(v),Math.abs(y[i]))))};
const refs={};let bad=0;
console.log(`${f}: state at ${ms} ms, ${props.length} custom properties on the levels`);
for(const spec of specs){const o=await read(spec);const v=o.noif?'noif':'';const ref=refs[v]=refs[v]||await read('chromium'+(v?':'+v:''));
 const tol=TOL;const diffs=[];let n=0,max=0;
 for(const [lv,ps] of Object.entries(ref.r))for(const [k,a] of Object.entries(ps)){n++;const d=differ(a,o.r[lv]?.[k]);max=Math.max(max,d);if(d>tol)diffs.push([d,lv,k,a,o.r[lv]?.[k]])}
 const fail=diffs.length>n*FRAC;bad+=fail;
 console.log(`${fail?'FAIL':'PASS'} ${spec} (${o.ver}) against ${ref.ver}${v?' on the noif copy':''}: ${n} values, largest difference ${max.toPrecision(2)}, ${diffs.length} beyond ${tol}`);
 for(const [d,lv,k,a,c] of diffs.sort((u,v)=>v[0]-u[0]).slice(0,20))console.log(`  #${lv} ${k}: chromium ${JSON.stringify(a.slice(0,60))} ${spec} ${JSON.stringify(String(c).slice(0,60))}`)}
// the fallback itself: on the noif copy Chromium must write back the original's next state (register offsets, px)
if(refs.noif){const o=refs.noif.regs,r=(refs['']||await read('chromium')).regs;const diffs=[];let max=0;
 for(const [k,a] of Object.entries(r))if(k!==clockReg)for(const j of [0,1]){const d=Math.abs(a[j]-o[k][j]);max=Math.max(max,d);if(d>1)diffs.push([k,j,a[j],o[k][j]])}
 bad+=diffs.length>0;console.log(`${diffs.length?'FAIL':'PASS'} chromium: the noif copy's next state against the original's: ${(Object.keys(r).length - 1) * 2} registers, largest difference ${max.toPrecision(2)} px, ${diffs.length} beyond 1 px`);
 for(const [k,j,a,c] of diffs.slice(0,10))console.log(`  #${k} ${j?'left':'top'}: original ${a} noif ${c}`)}
process.exit(bad?1:0)})();
