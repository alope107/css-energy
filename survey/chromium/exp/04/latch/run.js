const {chromium}=require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
const p=await b.newPage();await p.goto('file://'+process.argv[2]);await p.waitForTimeout(500);
const r=await p.evaluate(async()=>{const g=(id,n)=>getComputedStyle(document.getElementById(id)).getPropertyValue(n);const o=[];
 for(let i=0;i<12;i++){await new Promise(r=>requestAnimationFrame(r));o.push([g('P','--k'),g('P','--w'),g('C','--L'),g('E','--M'),g('F','--r2'),g('G','--N'),getComputedStyle(document.getElementById('G')).transition].join(' '));}return o});
console.log(r.join('\n'));await b.close()})();
