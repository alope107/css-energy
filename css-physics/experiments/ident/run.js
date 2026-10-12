// node experiments/ident/run.js experiments/ident/ident.html : does var(ident(...)) resolve? (-99 = no)
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox','--no-zygote']});
const p=await b.newPage();await p.goto(require('url').pathToFileURL(require('path').resolve(process.argv[2])).href);
console.log(await p.evaluate(()=>{const c=getComputedStyle(document.getElementById('x'));return ['--op','--op3'].map(n=>n+'='+c.getPropertyValue(n)).join(' ')+' ua='+navigator.userAgent.match(/Chrome\/[\d.]+/)}));await b.close()})();
