const {launch,open}=require('./lib/physics');
(async()=>{const b=await launch();
const p=await open(b,process.argv[2],{viewport:{width:1000,height:900}});await p.waitForTimeout(+process.argv[4]||1500);
const ar=await p.locator('.arena').boundingBox();await p.screenshot({path:process.argv[3],clip:{x:ar.x,y:ar.y,width:ar.width,height:ar.height}});
console.log(await p.evaluate(()=>{const w=document.querySelector('[id$=w0]');const c=getComputedStyle(w);return 'w0 Rx='+c.getPropertyValue('--Rx')+' Ry='+c.getPropertyValue('--Ry')+' transform='+c.transform.slice(0,80)+' anim='+w.getAnimations().map(a=>a.timeline&&a.timeline.constructor.name).join(',')}));await b.close()})();
