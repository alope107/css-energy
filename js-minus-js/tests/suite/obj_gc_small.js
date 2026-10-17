// the heap holds 384 chunks: 500 objects need a collection
var keep = {n: 0};
for (var i = 0; i < 500; i++) {
  var t = {v: i};
  keep.n += t.v;
}
console.log(keep.n);
