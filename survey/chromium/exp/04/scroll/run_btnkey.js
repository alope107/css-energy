const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{
  const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
  const p=await b.newPage({viewport:{width:800,height:400}});
  await p.goto('file://'+__dirname+'/btn.html?w=1');
  await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  await p.mouse.click(520,40);
  const sl=()=>p.evaluate(()=>document.getElementById('s').scrollLeft);
  const r=[await sl()];
  for(let i=0;i<5;i++){await p.keyboard.press('Enter');r.push(await sl());}
  for(let i=0;i<3;i++){await p.keyboard.press(' ');r.push(await sl());}
  // keydown with repeat flag: send raw CDP key events with autoRepeat
  const c=await p.context().newCDPSession(p);
  for(let i=0;i<5;i++){await c.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,autoRepeat:i>0});}
  await c.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  r.push(await sl());
  // Tab focus order: is the button reachable by Tab from body?
  console.log(r.join(' '));
  await b.close();
})();
