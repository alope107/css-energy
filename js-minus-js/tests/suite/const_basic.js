const n = 5, m = 2;
const a = [3, 1, 4];
a[0] = 9;
a[1] += n;
console.log(n * m, a[0], a[1], a[2]);
function sq(x) {
  const y = x * x;
  return y;
}
const big = sq(n) + 100;
console.log(big);
for (let i = 0; i < 3; i++) {
  const k = i * m;
  console.log(k);
}
