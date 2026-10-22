// physics.js — what css-physics's tools share (harness only): the browser profile, page probes, the camera
// projection and the BODYINFO comment of PLAIN builds.
//   const {launch,open,arena,bodyInfo,countFrames}=require('./lib/physics');
// The camera constants must match gen3d.py (PERSP, TILT, CAM_TY, CAM_DIST) and ui3d.css; change them together.
const {profile,fileUrl,envArgs}=require('../../../shared/js/browser.js');const B=profile('physics');
const {countFrames,vars,pollUntil}=require('../../../shared/js/page.js');
const trace=require('../../../shared/js/trace.js');
const {CLOCK_CSS,CLOCK_ANIMATION,wobble,constant}=require('../../../shared/js/freeze.js');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];
// BROWSER=firefox: Playwright's patched Firefox instead (the Chromium flags are dropped), with the scroll-driven
// animations pref the registers need before Firefox 159. FIREFOX=/path picks the build; without it, if Playwright's own
// isn't installed, the newest one in the devcontainer image's /ms-playwright (don't `npx playwright install` there:
// it garbage-collects the image's other browsers, /usr/local/bin/chromium's included). Evaluate-based tools only:
// the tracing ones (tr.js, …) need Chrome's DevTools protocol.
const FF_PREFS={'layout.css.scroll-driven-animations.enabled':true};
const imageFirefox=()=>{const fs=require('fs');try{return fs.readdirSync('/ms-playwright').filter(d=>/^firefox-\d+$/.test(d))
 .sort((a,b)=>b.split('-')[1]-a.split('-')[1]).map(d=>`/ms-playwright/${d}/firefox/firefox`).find(f=>fs.existsSync(f))}catch(e){return undefined}};
async function launchFirefox(o={}){const {args,extraArgs,...rest}=o;
 const ff=require(require.resolve('playwright',{paths:[require.main.path,__dirname]})).firefox;
 const opts={...rest,executablePath:process.env.FIREFOX||undefined,firefoxUserPrefs:FF_PREFS};
 try{return await ff.launch(opts)}catch(e){const alt=imageFirefox();if(opts.executablePath||!/Executable doesn't exist/.test(e.message)||!alt)throw e;
  console.error(`physics.js: Playwright's own Firefox isn't installed; using ${alt} (set FIREFOX to choose)`);return ff.launch({...opts,executablePath:alt})}}
// BROWSER=webkit: Playwright's WebKit (headless, the WPE MiniBrowser on Linux; the Chromium flags are dropped).
// WEBKIT=/path picks the build (its pw_run.sh); without it, if Playwright's own isn't installed, the newest one in
// /ms-playwright, as for Firefox. Evaluate-based tools only.
const imageWebkit=()=>{const fs=require('fs');try{return fs.readdirSync('/ms-playwright').filter(d=>/^webkit-\d+$/.test(d))
 .sort((a,b)=>b.split('-')[1]-a.split('-')[1]).map(d=>`/ms-playwright/${d}/pw_run.sh`).find(f=>fs.existsSync(f))}catch(e){return undefined}};
async function launchWebkit(o={}){const {args,extraArgs,...rest}=o;
 const wk=require(require.resolve('playwright',{paths:[require.main.path,__dirname]})).webkit;
 const opts={...rest,executablePath:process.env.WEBKIT||undefined};
 try{return await wk.launch(opts)}catch(e){const alt=imageWebkit();if(opts.executablePath||!/Executable doesn't exist/.test(e.message)||!alt)throw e;
  console.error(`physics.js: Playwright's own WebKit isn't installed; using ${alt} (set WEBKIT to choose)`);return wk.launch({...opts,executablePath:alt})}}
const launchers={chromium:B.launch,firefox:launchFirefox,webkit:launchWebkit};
const launch=launchers[process.env.BROWSER]||B.launch;

// world point -> page coordinates of its screen projection, for the arena's bounding box `ar` (yaw: the view's default)
const projector=ar=>{const sc=ar.width/VW;
 return ([x,y,z],yaw=0.25)=>{const c=Math.cos(yaw),s=Math.sin(yaw),ct=Math.cos(TILT*Math.PI/180),st_=Math.sin(TILT*Math.PI/180);
  const x1=x*c+z*s,z1=-x*s+z*c,y3=y*ct-z1*st_+TY,z3=y*st_+z1*ct-DIST,k=PERSP/(PERSP-z3);return [ar.x+ar.width/2+x1*k*sc, ar.y+ar.height/2+y3*k*sc]}};
// the arena's box and its projector
const arena=async p=>{const ar=await p.locator('.arena').boundingBox();return {ar,proj:projector(ar)}};

// the bodies' shapes from a PLAIN single-engine build's <!--BODYINFO--> comment (null if the page has none)
const bodyInfo=src=>{const m=src.match(/<!--BODYINFO (.*?)-->/);return m?JSON.parse(m[1]):null};

// freezing (freeze3.js, freezegrab.js): the state registers are the properties the page's @keyframes q<k> animate on #LS
const registerNames=s=>[...s.matchAll(/@keyframes q\d+\{from\{--([A-Za-z0-9_]+):/g)].map(m=>m[1]);
// page source s with the registers `names` baked in at `vals` (as read from #LS) on a static clock (../../../shared/js/freeze.js):
// wobbling constants, except the sleep counters and grab state, which gate rules and stay exact, and with ONLYAWAKE=1
// every register of a sleeping body; TP and DB (the clock's) are dropped. The register scrollers' timelines are removed.
// exact: every register a constant (nothing recomputes after the first passes: xcheck.js compares engines on it).
function bakeRegisters(s,names,vals,exact=false){
s=s.replace(/#LS\{\s*animation-name:[^;]*;\s*animation-duration:[^;]*;\s*animation-iteration-count:[^;]*;\s*animation-timing-function:[^;]*;\s*animation-fill-mode:[^;]*;\s*animation-timeline:[^;]*;/,'#LS{'+CLOCK_ANIMATION+';');
if(!s.includes('#LS{animation:clk2'))throw new Error('LS pattern');
const asleep=new Set();names.forEach((n,i)=>{const m=n.match(/^SC(\d+)$/);if(m&&+vals[i]>45&&process.env.ONLYAWAKE)asleep.add(m[1])});
const consts=names.map((n,i)=>{if(n==='TP'||n==='DB')return '';const bi=(n.match(/^[A-Z]+(\d+)$/)||[])[1];if(exact||/^(SC\d+|GI|GT|GYP)$/.test(n)||(bi!==undefined&&asleep.has(bi)))return constant(n,vals[i]);return wobble(n,vals[i])}).join('');
s=s.replace(/(#LS\{animation:clk2[^}]*)\}/,`$1;${consts}}`);
s=s.replace('<style>','<style>'+CLOCK_CSS);
return s.replace(/(#w\d+\{)animation-name:[^;]*;animation-timeline:[^;]*;/g,'$1')}

module.exports={launch,launchers,open:B.open,profile:B,fileUrl,envArgs,countFrames,vars,pollUntil,...trace,CAM:{PERSP,TILT,TY,DIST,VW},projector,arena,bodyInfo,registerNames,bakeRegisters};
