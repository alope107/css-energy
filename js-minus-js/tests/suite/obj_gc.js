// garbage collection: many short-lived objects, a few kept
var keep = null;
var s = 0;
for (var i = 0; i < 900; i++) {
  var t = {a: i, b: {c: i % 7}};
  s += t.b.c;
  if (i % 100 == 0) keep = {v: i, next: keep};
}
var n = 0;
while (keep) { n += keep.v; keep = keep.next; }
console.log(s, n);
