const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
const raf=p=>p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  for(const cls of ['', 'snap']){
    await p.goto('file://'+__dirname+'/marker.html');
    await p.evaluate(c=>document.body.className=c,cls);await raf(p);
    const res=[];
    for(const off of [0,49,50,51,99,100,149,150,151,199,200,1500,1550,1600]){
      await p.evaluate(o=>{document.getElementById('s').scrollLeft=o},off);await raf(p);
      const r=await p.evaluate(()=>({sl:document.getElementById('s').scrollLeft,...cur()}));
      res.push(`${off}->${r.sl}:cur${r.cur}/bef${r.before}`);
    }
    console.log('['+cls+'] set scrollLeft:', res.join(' '));
    // click markers: marker i at x = i*30+10, y=10
    await p.evaluate(()=>{document.getElementById('s').scrollLeft=0});await raf(p);
    const cl=[];
    for(const i of [5,2,15,19,0]){
      await p.mouse.click(i*30+10,10);await raf(p);await p.waitForTimeout(100);await raf(p);
      const r=await p.evaluate(()=>({sl:document.getElementById('s').scrollLeft,...cur()}));
      cl.push(`click${i}->sl${r.sl}:cur${r.cur}`);
    }
    // after a click on 19 (unreachable), cur is pinned; then a non-targeted scroll
    console.log('['+cls+'] clicks:', cl.join(' '));
    await p.mouse.click(19*30+10,10);await raf(p);await p.waitForTimeout(100);
    const a=await p.evaluate(()=>({sl:document.getElementById('s').scrollLeft,...cur()}));
    await p.evaluate(()=>{document.getElementById('s').scrollLeft-=1});await raf(p);await raf(p);
    const c=await p.evaluate(()=>({sl:document.getElementById('s').scrollLeft,...cur()}));
    console.log('['+cls+'] pinned click19:',JSON.stringify(a),' after scrollLeft-=1:',JSON.stringify(c));
  }
  await b.close();
})();
