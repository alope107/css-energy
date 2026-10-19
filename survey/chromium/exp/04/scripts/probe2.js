const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
const p=await b.newPage();await p.goto('file://'+process.argv[2]);await p.waitForTimeout(300);
const r=await p.evaluate(process.argv[3]);
console.log(JSON.stringify(r));await b.close()})();
