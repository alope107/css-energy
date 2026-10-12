const {chromium}=require('playwright');
(async()=>{const exe=process.env.CHROME||undefined;
const b=await chromium.launch({executablePath:exe,args:['--no-sandbox','--no-zygote','--disable-setuid-sandbox']});
const p=await b.newPage();await p.goto(require('url').pathToFileURL(require('path').resolve(process.argv[2])).href);await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
console.log(await p.evaluate(()=>[...document.querySelectorAll('.t')].map(d=>{const c=getComputedStyle(d);return [d.style.fontVariationSettings, 'ch',c.getPropertyValue('--ch'),'ic',c.getPropertyValue('--ic'),'ex',c.getPropertyValue('--ex'),'cap',c.getPropertyValue('--cap'),'w',[...d.children].map(s=>s.getBoundingClientRect().width).join(',')].join(' ')}).join('\n')));
await b.close()})();
