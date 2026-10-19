const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  for(const args of [[],['--enable-features=FractionalScrollOffsets']]){
    const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox',...args]});
    const p=await b.newPage();
    await p.goto('file://'+__dirname+'/frac.html');
    const out=[];
    for(const v of [500.4, 1000.75, 999999.3, 524288.3]){
      await p.evaluate(v=>{document.getElementById('s').scrollTop=v},v);
      await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
      out.push(v+'->'+await p.evaluate(()=>document.getElementById('s').scrollTop+'/'+getComputedStyle(document.getElementById('o')).width));
    }
    // scrollBy accumulation
    await p.evaluate(()=>{const s=document.getElementById('s');s.scrollTop=0;for(let i=0;i<10;i++)s.scrollBy(0,0.3)});
    await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    out.push('10x scrollBy(0.3)->'+await p.evaluate(()=>document.getElementById('s').scrollTop+'/'+getComputedStyle(document.getElementById('o')).width));
    console.log(args.join(' ')||'(default)', out.join(' | '));
    await b.close();
  }
})();
