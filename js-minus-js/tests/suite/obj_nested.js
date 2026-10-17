// nested objects and chains of properties
var o = {a: {b: {c: 3}}, d: {e: 4}};
console.log(o.a.b.c, o.d.e);
o.a.b.c = 30;
o.a.b.f = {g: 7};
o.d = {e: 40, h: {i: 8}};
console.log(o.a.b.c, o.a.b.f.g, o.d.e, o.d.h.i);
o.a.b.f.g *= 3;
o.d.h.i++;
console.log(o.a.b.f.g, o.d.h.i);
var t = o.a.b;
t.c = t.c + o.d.e;
console.log(o.a.b.c);
function depth(n) {
  if (n == 0) return {leaf: 1};
  return {kid: depth(n - 1), n: n};
}
var d = depth(4);
console.log(d.n, d.kid.n, d.kid.kid.kid.kid.leaf);
