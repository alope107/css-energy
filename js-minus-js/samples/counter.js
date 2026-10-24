// closures: each counter keeps its own n
function counter(step) {
  let n = 0;
  return () => { n += step; return n; };
}
const a = counter(1), b = counter(10);
a(); a(); b();
console.log(a(), b());
const add = x => y => x + y;
const inc = add(1);
console.log(inc(41));
// timers run after the program ends
let t = 3;
const id = setInterval(() => {
  console.log("tick " + t);
  t--;
  if (t === 0) clearInterval(id);
}, 100);
setTimeout(() => { console.log("bye"); }, 500);
console.log("go");
