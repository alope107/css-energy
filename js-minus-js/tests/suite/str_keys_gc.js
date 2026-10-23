// run-time string keys survive garbage collections, both ways.
// Empty objects fill each half of the heap cheaply (a line per
// chunk); each collection comes in the array literal's ALLOC,
// with its elements on the stack.
// collections: galloc galloc
var o = {};
for (var i = 0; i < 12; i++) o["key" + i] = "v" + i;
var junk = 0, e = 0;
for (var r = 0; r < 2; r++) {
  for (var k = 0; k < (r ? 278 : 300); k++) e = {};
  for (var j = 0; j < 25; j++) {
    var t = [j, "s" + j, {a: j}];
    junk += t[0] % 3;
  }
}
var s = "";
for (var i = 0; i < 12; i += 3) s += o["key" + i] + ",";
console.log(s, junk);
o["key" + 5] += "!";
console.log(o.key5, o["ke" + "y11"], o.key0 + o.key1);
