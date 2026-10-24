// promises printed as Node prints them
const a = Promise.resolve(42);
const b = Promise.reject("no");
b.catch(e => e);
const c = new Promise(r => setTimeout(() => r([1, "x"]), 1));
const d = Promise.resolve("str");
console.log(a);
console.log(b);
console.log(c);
console.log(d, typeof d);
console.log([a, { p: a }]);
c.then(() => console.log(c));
async function f() { return 7; }
const e = f();
console.log(e);
const g = new Promise(r => r(a));
console.log(g);
setTimeout(() => console.log(g), 5);
