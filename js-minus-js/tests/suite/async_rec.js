// recursion through await, loops of awaits, a timer sleep
async function fact(n) {
  if (n <= 1) return 1;
  return n * await fact(n - 1);
}
fact(10).then(v => console.log("fact", v));
const sleep = (ms, v) =>
  new Promise(r => setTimeout(r.bind(null, v), ms));
async function race() {
  let s = "";
  let i = 0;
  while (i < 4) {
    s += await sleep(10 - 2 * i, i);
    i++;
  }
  return s;
}
race().then(s => console.log("race", s));
async function both() {
  const x = sleep(30, "slow"), y = sleep(5, "fast");
  console.log(await x, await y);
}
both();
sleep(20, "mid").then(v => console.log(v));
