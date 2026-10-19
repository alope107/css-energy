const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage();
  await p.goto('file://'+__dirname+'/big.html');
  const r=await p.evaluate(()=>{const s=document.getElementById('s');const out={scrollHeight:s.scrollHeight};
    for(const v of [1000000.4,1000000.6,1000001,16777215,16777217,16777219,20000001,20000003,33554400,33554500,40000000]){s.scrollTop=v;out[v]=s.scrollTop;}
    s.scrollTop=0; s.scrollBy(0,0.4); out.by04=s.scrollTop; s.scrollBy(0,0.6); out.by04_06=s.scrollTop;
    return out;});
  console.log(JSON.stringify(r));
  await b.close();
})();
