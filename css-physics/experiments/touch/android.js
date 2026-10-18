// Gestures on handles.html (the touch input without the engine) in Chromium on the Android emulator
// (../../../shared/android: start.sh with SERVE_DIR=<repo root> and this page's URL), kernel-level touches.
//   node experiments/touch/android.js [slow quick diag fling tap pressdrag ...]
// Per scenario: the page's events, when --att rose, how long after touchend it dropped, the largest drag, the body
// index, the frames with :active (show-press) and the rAF count.
const {execFileSync}=require('child_process');
const TOUCH=require('path').join(__dirname,'../../../shared/android/touch.py');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const touch=(...a)=>execFileSync('python3',['-I',TOUCH,...a.map(String)],{stdio:'inherit'});
(async()=>{const ts=(await (await fetch('http://127.0.0.1:9222/json/list')).json()).filter(t=>t.type==='page'&&t.url.includes('handles.html'));
 const ws=new WebSocket(ts[0].webSocketDebuggerUrl);let id=0;const pend=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(pend.has(m.id)){pend.get(m.id)(m);pend.delete(m.id)}};
 await new Promise(r=>ws.onopen=r);
 const ev=x=>new Promise(res=>{const i=++id;pend.set(i,m=>res(m.result&&m.result.result&&m.result.result.value));ws.send(JSON.stringify({id:i,method:'Runtime.evaluate',params:{expression:x,returnByValue:true}}))});
 await ev(`window.ACT=[];(function f(){ACT.push([Math.round(performance.now()-t1),document.querySelectorAll(':active').length,[...document.querySelectorAll(':hover')].map(e=>e.id).filter(Boolean).join('/')]);if(ACT.length>2000)ACT.splice(0,1000);requestAnimationFrame(f)})();1`);
 // calibration: a tap at a known screen point, read back as client coordinates (the browser's toolbar offsets the page)
 await ev(`window.CAL=[];addEventListener('touchstart',e=>CAL.push([e.touches[0].clientX,e.touches[0].clientY]),{capture:true,once:true});1`);
 touch('tap',360,300);await sleep(1500);const cal=(await ev('CAL'))[0];const dpr=await ev('devicePixelRatio');
 const ox=360/dpr-cal[0],oy=300/dpr-cal[1];console.log(`calibration: page offset ${ox.toFixed(1)}, ${oy.toFixed(1)} css px at DPR ${dpr}`);
 const scr=(x,y)=>[Math.round((x+ox)*dpr),Math.round((y+oy)*dpr)];
 const rect=id=>ev(`(()=>{const r=document.getElementById('${id}').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()`);
 const SC={
  slow:async([x,y])=>touch('swipe',...scr(x,y),...scr(x+60,y+40),1000,'--hold-ms',300,'--release-hold-ms',600),
  quick:async([x,y])=>touch('swipe',...scr(x,y),...scr(x+60,y+40),700,'--release-hold-ms',600),
  diag:async([x,y])=>touch('swipe',...scr(x,y),...scr(x+60,y+4),500,'--release-hold-ms',400),
  fling:async([x,y])=>touch('swipe',...scr(x,y),...scr(x+70,y+45),150),
  tap:async([x,y])=>touch('tap',...scr(x,y)),
  pressdrag:async([x,y])=>touch('swipe',...scr(x,y),...scr(x+60,y+40),800,'--hold-ms',700,'--release-hold-ms',500),
 };
 for(const sc of (process.argv.slice(2).length?process.argv.slice(2):Object.keys(SC))){
  await sleep(2500);const c=await rect('d1');await ev('LOG.length=0;ACT.length=0');const t0=await ev('performance.now()-t1');
  await SC[sc](c);await sleep(2500);
  const L=await ev('LOG'),A=await ev('ACT');
  const ends=L.filter(l=>/touchend/.test(l[1])).map(l=>l[0]);const tEnd=ends[0];
  const st=L.filter(l=>/sd=/.test(l[1]));
  const firstAtt=st.find(l=>/att=1/.test(l[1])),drop=tEnd&&st.find(l=>l[0]>=tEnd&&/att=0/.test(l[1]));
  const maxsd=st.reduce((m,l)=>{const v=l[1].match(/sd=(-?[\d.]+),(-?[\d.]+)/);return v?[Math.min(m[0],+v[1]),Math.min(m[1],+v[2])]:m},[0,0]);
  const act=A.filter(a=>a[1]>0);
  console.log(`${sc}: ${L.filter(l=>!/sd=/.test(l[1])).map(l=>l[1]+'@'+Math.round(l[0]-t0)).join(' ')}`);
  console.log(`   att=1 from ${firstAtt?Math.round(firstAtt[0]-t0):'never'} ms; drop ${drop?Math.round(drop[0]-tEnd)+' ms after touchend':'none'}; max drag ${maxsd}; gi ${[...new Set(st.map(l=>(l[1].match(/gi=([\d.]+)/)||[])[1]))]}; :active frames ${act.length} (${act.length?Math.round(act[0][0]-t0)+'..'+Math.round(act[act.length-1][0]-t0):''}); hover after ${A[A.length-1][2]}; rAF frames ${A.length}`);
 }
 ws.close()})();
