// an async function's variables while it waits: closures
async function counter() {
  let n = 0;
  const inc = () => { n = n + 1; return n; };
  setTimeout(inc, 0);
  console.log("before", n);
  await new Promise(r => setTimeout(r, 10));
  console.log("after", n, inc());
  return () => n;
}
counter().then(get => console.log("got", get()));
let total = 0;
async function add(x) {
  const s = [x];
  await null;
  s.push(x * 2);
  total += s[0] + s[1];
  return s;
}
Promise.resolve().then(() => console.log("total", total));
add(1); add(2).then(s => console.log(s, total));
