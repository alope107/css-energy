const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  for(const mode of process.argv.slice(2)){
    await p.goto('file://'+__dirname+'/anchor3.html');
    const r=await p.evaluate((mode)=>new Promise(res=>{
      const s=document.getElementById('s'),g=document.getElementById('g');
      s.scrollTop=start=1000;
      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        document.body.className=mode;
        const t0=performance.now();const samples=[];
        function f(){const t=performance.now()-t0;samples.push([Math.round(t),s.scrollTop,Math.round(parseFloat(getComputedStyle(g).height))]);
          if(t<4200)requestAnimationFrame(f);else res(samples);}
        requestAnimationFrame(f);
      }));
    }),mode);
    // print every ~250ms
    const pr=[];let next=0;for(const [t,st,gh] of r){if(t>=next){pr.push(`${t}:${st}/${gh}`);next+=250;}}
    console.log(mode, 'frames', r.length, '\n  ', pr.join(' '));
  }
  await b.close();
})();
