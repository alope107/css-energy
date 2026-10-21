// array literals hold any values; each evaluation: a new array
var n = 3;
var a = [n, n * 2, "s", [1, 2], {k: 5}, -n];
console.log(a.length, a[0], a[1], a[2], a[3][1], a[4].k, a[5]);
var e = [];
console.log(e.length, [].length, [1, 2, 3,].length);
function mk(x) { return [x, x + 1]; }
var p = mk(1), q = mk(1);
p[0] = 9;
console.log(p[0], q[0], p === q, p === p);
var m = [[1, 2], [3, 4]];
console.log(m[1][0], m[0][1] + m[1][1], m.length, m[0].length);
var b = a;
b[0] = 100;
console.log(a[0], b.length, b[5]);
