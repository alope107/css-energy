// console.log in an async function: its arguments print after
// every await among them
async function f(p, q) {
  console.log("a", await p, "b", await q);
  console.log("x" + 1, [1, 2], await p + "!");
  console.log(await p);
  return "f";
}
f(Promise.resolve(1), 2).then(v => console.log("done", v));
Promise.resolve().then(() => console.log("m1"))
  .then(() => console.log("m2")).then(() => console.log("m3"));
console.log("sync", 1, 2);
