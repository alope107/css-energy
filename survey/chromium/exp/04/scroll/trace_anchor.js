const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs=require('fs');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  const mode=process.argv[2];
  await p.goto('file://'+__dirname+'/anchor3.html');
  await p.evaluate(()=>{document.getElementById('s').scrollTop=1000});
  await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  await b.startTracing(p,{path:__dirname+'/trace_'+mode+'.json',categories:['disabled-by-default-blink.debug','blink']});
  await p.evaluate(m=>{document.body.className=m},mode);
  await p.waitForTimeout(1600);
  await b.stopTracing();
  await b.close();
  const t=JSON.parse(fs.readFileSync(__dirname+'/trace_'+mode+'.json'));
  const ev=(t.traceEvents||t).filter(e=>/ScrollAnchor|FindAnchor|ComputeAdjustment|^Adjust$/.test(e.name)||(e.args&&e.args.data&&0));
  const names={};for(const e of ev){const k=e.name+' '+JSON.stringify(e.args).slice(0,90);names[k]=(names[k]||0)+1;}
  const rows=Object.entries(names).sort((a,b)=>b[1]-a[1]).slice(0,25);for(const [k,v] of rows)console.log(v,k);
})();
