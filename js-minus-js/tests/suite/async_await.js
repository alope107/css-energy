// async functions: each await yields to the caller
async function f(x) {
  console.log("f start", x);
  const y = await x;
  console.log("f got", y);
  const z = await g(y);
  console.log("f z", z);
  return z + 1;
}
async function g(v) {
  await null;
  return v * 10;
}
f(4).then(r => console.log("f ->", r));
console.log("after f");
const h = async (a, b) => (await a) + (await b);
h(1, Promise.resolve(2)).then(v => console.log("h", v));
const k = async x => x * 3;
k(7).then(v => console.log("k", v));
(async function () {
  for (let i = 0; i < 3; i++) console.log("i", await i);
})();
