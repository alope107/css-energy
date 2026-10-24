// microtasks run before timers, after each task
setTimeout(() => console.log("t1"), 0);
Promise.resolve().then(() => console.log("m1"));
setTimeout(() => {
  console.log("t2");
  Promise.resolve().then(() => console.log("m3"));
}, 0);
setTimeout(() => console.log("t3"), 0);
async function a() {
  console.log("a1"); await 0; console.log("a2");
}
a();
new Promise(r => setTimeout(() => r("late"), 5))
  .then(v => console.log(v));
const p1 = Promise.resolve(1);
const p2 = new Promise(r => r(p1));
p2.then(() => console.log("p2"));
p1.then(() => console.log("p1")).then(() => console.log("p1b"))
  .then(() => console.log("p1c"));
console.log("main");
