// rejection: catch, then's second handler, async functions
const r = Promise.reject("bad");
r.catch(e => console.log("caught", e));
r.then(v => console.log("no"), e => console.log("then2", e));
new Promise((res, rej) => rej(7))
  .then(v => console.log("skipped", v))
  .catch(e => { console.log("late catch", e); return e * 2; })
  .then(v => console.log("recovered", v));
async function f() {
  const v = await Promise.reject("x");
  console.log("never", v);
}
f().catch(e => console.log("f rejected", e));
async function g() { return Promise.reject("y"); }
g().then(null, e => console.log("g rejected", e));
const ok = new Promise((res, rej) => {
  res("first"); rej("second");
});
ok.then(v => console.log("ok", v),
  e => console.log("no", e));
