// for loops, arrays, a[i] = e, ++/--, && || !, unary minus
var a = [5, -3, 8, 1, 0, 7];
var i = 0;
var s = 0;
for (i = 0; i < 6; i++) { s = s + a[i]; }
console.log(s);
for (var j = 0; j < 6; j++) { a[j] = a[j] * 2 + 1; }
console.log(a[2]);
var k = 10; k--; k--;
console.log(k);
console.log(!0 + !5 * 10);
console.log(-k + 3 * -2);
if (k > 3 && k < 9 || !k) { console.log("yes"); } else { console.log("no"); }
var t = 0;
while (t < 100000) { t = t + 25000; }
console.log(t);
console.log(70000 + 1);
