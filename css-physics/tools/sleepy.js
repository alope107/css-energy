// node tools/sleepy.js page.html N [seconds] : every 0.5 s print how many of the N bodies are asleep (SC > 45), with the awake indices once 6 or fewer remain
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||undefined,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1000,height:800}});await p.goto(require('url').pathToFileURL(require('path').resolve(process.argv[2])).href);
const N=+process.argv[3],S=+process.argv[4]||15;const out=[];
for(let t=0;t<S*2;t++){await p.waitForTimeout(500);out.push(await p.evaluate(N=>{const c=getComputedStyle(document.getElementById('LS'));let a=0;const aw=[];for(let i=0;i<N;i++){if(+c.getPropertyValue('--SC'+i)>45)a++;else aw.push(i)}return a+(aw.length<=6?'['+aw.join(',')+']':'')},N))}
console.log(process.argv[2],out.join(' '));await b.close()})();
