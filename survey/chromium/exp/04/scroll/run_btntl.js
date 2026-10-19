const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  await p.goto('file://'+__dirname+'/btntl.html');
  await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  await p.evaluate(()=>{window.log=[];const s=document.getElementById('s'),o=document.getElementById('o');
    s.addEventListener('scroll',()=>log.push('scroll ev sl='+s.scrollLeft));
    document.addEventListener('click',()=>log.push('click(capture-doc) sl='+s.scrollLeft+' w='+getComputedStyle(o).width),true);
    let n=0;function f(){log.push(`raf${n} sl=${s.scrollLeft} w=${getComputedStyle(o).width}`);if(++n<4)requestAnimationFrame(f);}window.go=()=>{n=0;requestAnimationFrame(f)};});
  for(let i=0;i<3;i++){await p.mouse.click(520,40);await p.evaluate(()=>{go();return new Promise(r=>setTimeout(r,150))});}
  console.log((await p.evaluate(()=>log)).join('\n'));
  await b.close();
})();
