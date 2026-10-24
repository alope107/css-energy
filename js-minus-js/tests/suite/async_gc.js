// collections while awaits wait: frames and promises survive
// collections: galloc
async function worker(id) {
  let mine = [id, id * 2];
  let s = "w" + id;
  for (let r = 0; r < 3; r++) {
    await null;
    mine.push(r);
    s = s + r;
    for (let k = 0; k < 40; k++) { const t = [k]; }
  }
  return s + ":" + mine.join(",");
}
const ps = [];
for (let i = 0; i < 4; i++) ps.push(worker(i));
for (let i = 0; i < 4; i++) ps[i].then(v => console.log(v));
