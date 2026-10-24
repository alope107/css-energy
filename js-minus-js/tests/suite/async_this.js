// async methods, this, nested async functions sharing variables
const o = { n: 5 };
o.get = async function (k) {
  const v = await this.n;
  return v * k;
};
o.get(3).then(v => console.log("get", v));
async function outer(start) {
  let acc = start;
  const step = async x => {
    acc = acc + await x;
    return acc;
  };
  console.log("s1", await step(1));
  console.log("s2", await step(Promise.resolve(10)));
  const p = step(100);
  acc = acc + 1000;
  console.log("s3", await p, acc);
  return acc;
}
outer(0).then(v => console.log("outer", v));
console.log("sync end");
