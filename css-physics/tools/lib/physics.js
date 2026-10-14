// physics.js — what css-physics's tools share (harness only): the browser profile, page probes, the camera
// projection and the BODYINFO comment of PLAIN builds.
//   const {launch,open,arena,bodyInfo,countFrames}=require('./lib/physics');
// The camera constants must match gen3d.py (PERSP, TILT, CAM_TY, CAM_DIST) and ui3d.css; change them together.
const {profile,fileUrl,envArgs}=require('../../../shared/js/browser.js');const B=profile('physics');
const {countFrames,vars,pollUntil}=require('../../../shared/js/page.js');
const trace=require('../../../shared/js/trace.js');
const {CLOCK_CSS,CLOCK_ANIMATION,wobble,constant}=require('../../../shared/js/freeze.js');
const [PERSP,TILT,TY,DIST,VW]=[1500,-28,95,-260,900];

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
function bakeRegisters(s,names,vals){
s=s.replace(/#LS\{\s*animation-name:[^;]*;\s*animation-duration:[^;]*;\s*animation-iteration-count:[^;]*;\s*animation-timing-function:[^;]*;\s*animation-fill-mode:[^;]*;\s*animation-timeline:[^;]*;/,'#LS{'+CLOCK_ANIMATION+';');
if(!s.includes('#LS{animation:clk2'))throw new Error('LS pattern');
const asleep=new Set();names.forEach((n,i)=>{const m=n.match(/^SC(\d+)$/);if(m&&+vals[i]>45&&process.env.ONLYAWAKE)asleep.add(m[1])});
const consts=names.map((n,i)=>{if(n==='TP'||n==='DB')return '';const bi=(n.match(/^[A-Z]+(\d+)$/)||[])[1];if(/^(SC\d+|GI|GT|GYP)$/.test(n)||(bi!==undefined&&asleep.has(bi)))return constant(n,vals[i]);return wobble(n,vals[i])}).join('');
s=s.replace(/(#LS\{animation:clk2[^}]*)\}/,`$1;${consts}}`);
s=s.replace('<style>','<style>'+CLOCK_CSS);
return s.replace(/(#w\d+\{)animation-name:[^;]*;animation-timeline:[^;]*;/g,'$1')}

module.exports={launch:B.launch,open:B.open,profile:B,fileUrl,envArgs,countFrames,vars,pollUntil,...trace,CAM:{PERSP,TILT,TY,DIST,VW},projector,arena,bodyInfo,registerNames,bakeRegisters};
