// a binary search tree of objects
function insert(t, k) {
  if (t === null) return {k: k, l: null, r: null};
  if (k < t.k) t.l = insert(t.l, k);
  else t.r = insert(t.r, k);
  return t;
}
function walk(t, out) {
  if (t === null) return out;
  walk(t.l, out);
  out.push(t.k);
  return walk(t.r, out);
}
function depth(t) {
  if (t === null) return 0;
  const l = depth(t.l), r = depth(t.r);
  return 1 + (l > r ? l : r);
}
let root = null, ks = [50, 30, 70, 20, 40, 60, 80, 35, 65];
for (let i = 0; i < ks.length; i++) root = insert(root, ks[i]);
const out = walk(root, []);
for (let i = 0; i < out.length; i += 2)
  console.log(out.slice(i, i + 2).join(" "));
console.log("depth " + depth(root));
