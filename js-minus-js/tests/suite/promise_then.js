// new Promise, then chains, and the order of microtasks
const p = new Promise((resolve, reject) => {
  console.log("exec");
  resolve(1);
  resolve(2);
});
p.then(v => {
  console.log("a", v);
  return v + 1;
}).then(v => console.log("b", v));
p.then(v => console.log("c", v));
const q = new Promise(r => r(10));
q.then(function (v) { console.log("d", v); });
console.log("sync");
Promise.resolve(5).then(x => x * 2).then(v => console.log(v));
var s = Promise.resolve("s");
console.log(Promise.resolve(s) === s);
s.then(v => v + "!").then(v => console.log(v));
