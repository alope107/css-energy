let i = 0;
do { i++; } while (i < 3);
console.log(i);
do i += 10; while (i < 5);
console.log(i);
let n = 0;
do {
  n++;
  if (n == 2) continue;
  if (n > 4) break;
  console.log(n);
} while (n < 9)
console.log("end", n);
do console.log("once"); while (false)
let k = 3
do k--
while (k > 0)
console.log(k)
function f(x) { do x = x * 2; while (x < 50); return x; }
console.log(f(3), f(100))
