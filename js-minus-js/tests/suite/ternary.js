let a = 5, b = 9;
console.log(a > b ? a : b, a < b ? a : b);
let m = a > 3 ? 100 : 200;
console.log(m);
console.log(a == 5 ? "five" : "other", a ? true : false);
function sign(x) { return x < 0 ? -1 : x > 0 ? 1 : 0; }
console.log(sign(-7), sign(0), sign(3));
function g(x) { return x > 9 ? x > 99 ? 3 : 2 : 1; }
console.log(g(5), g(50), g(500));
let t = 0;
for (let i = 0; i < 6; i++) t += i % 2 ? i : -i;
console.log(t);
let c = a > 1 && b > 1 ? a + b : a * b || 7;
console.log(c, (a > b ? a : b) * 2, 1 + (a ? 2 : 3));
const arr = [10, 20, 30];
console.log(arr[a > 4 ? 2 : 0], sign(a - b) ? "ne" : "eq");
if (a > 4 ? b > 8 : false) console.log("yes");
let w = a ?
  b
  : 0
console.log(w); putc(a > 4 ? 65 : 66); putc(10)
