// arrays grow: push, writes past the end, pop, shift, unshift
var a = [];
for (var i = 0; i < 20; i++) a.push(i * i);
console.log(a.length, a[19], a[7]);
var b = [1];
b[4] = 5;
console.log(b.length, b[0], b[4]);
var s = 0;
while (a.length > 15) s += a.pop();
console.log(s, a.length, a[14]);
console.log(a.shift(), a.shift(), a.length, a[0]);
a.unshift(-1);
console.log(a[0], a[1], a.length);
var c = [];
c[c.length] = "x";
c[c.length] = "y";
console.log(c.length, c[0] + c[1], c.push("z"), c.pop());
function fill(n) {
  var r = [];
  for (var i = 0; i < n; i++) r.push(i);
  return r;
}
var f = fill(40);
console.log(f.length, f[39] + f[20]);
