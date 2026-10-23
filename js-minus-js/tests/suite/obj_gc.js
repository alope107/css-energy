// garbage collection: many short-lived objects, a few kept
// across two collections (the heap's halves both ways)
// collections: gcnew gcnew
var keep = null;
var s = 0, e = 0;
for (var i = 0; i < 140; i++) {
  var t = {a: i, b: {c: i % 7}};
  s += t.b.c;
  e = {}; e = {}; e = {}; e = {};
  if (i % 25 == 0) keep = {v: i, next: keep};
}
var n = 0;
while (keep) { n += keep.v; keep = keep.next; }
console.log(s, n);
