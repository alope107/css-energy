// counting words with string keys
function word(i) { return i % 3 ? i % 2 ? "b" : "c" : "a"; }
var c = {};
for (var i = 0; i < 9; i++) {
  var k = word(i);
  c[k] = (c[k] || 0) + 1;
}
console.log(c.a, c.b, c.c, c["a"]);
var n = {};
for (var j = 0; j < 9; j++) n[j % 4] = (n[j % 4] || 0) + j;
console.log(n[0], n[1], n[2], n[3]);
