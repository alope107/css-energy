const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  const cases=process.argv.slice(2);
  for(const qs of cases){
    await p.goto('file://'+__dirname+'/btn.html?'+qs);
    await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const out=[];
    for(let i=0;i<6;i++){
      const t0=Date.now();
      await p.mouse.click(520,40);
      // poll until scrollLeft stable for 3 frames
      const r=await p.evaluate(()=>new Promise(res=>{const s=document.getElementById('s');let last=-1,stable=0,frames=0,t0=performance.now(),trace=[];
        function f(){frames++;const v=s.scrollLeft;trace.push(v);if(v===last)stable++;else stable=0;last=v;if(stable>=5||frames>300)res({v,ms:Math.round(performance.now()-t0),frames,trace:trace.slice(0,12)});else requestAnimationFrame(f);}requestAnimationFrame(f);}));
      out.push(r.v+(qs.includes('smooth=1')?` (${r.ms}ms ${JSON.stringify(r.trace)})`:''));
    }
    const dis=await p.evaluate(()=>getComputedStyle(document.getElementById('s'),'::scroll-button(right)').backgroundColor);
    console.log(qs, '=>', out.join(' | '));
  }
  await b.close();
})();
