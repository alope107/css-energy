// a grown array's raw block starts with a negative number, then
// collections (the collector once walked from-space by headers)
// collections: gcnew gcnew
var a = [];
for (var i = 0; i < 6; i++) a.push(-5);
var s = 0, e = 0;
for (var j = 0; j < 210; j++) {
  var t = {v: j % 9};
  s += t.v;
  e = {}; e = {}; e = {};
}
console.log(a[0], a.length, s, a.join());
