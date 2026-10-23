// a grown array's raw block starts with a negative number, then
// collections (the collector once walked from-space by headers)
var a = [];
for (var i = 0; i < 6; i++) a.push(-5);
var s = 0;
for (var j = 0; j < 1000; j++) {
  var t = [j, j % 9, j, j];
  s += t[1];
}
console.log(a[0], a.length, s, a.join());
