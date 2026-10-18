var i = 0, a = [5, 6, 7];
console.log(i++, i, ++i, i)
console.log(i--, --i, i)
let s = 0;
while (i < 3) s += a[i++];
console.log(s, i)
function f(n) {
  let k = n
  let m = k-- + --k
  return m * 100 + k
}
console.log(f(10))
var j = 5;
var b = j++ * 2 + ++j;
console.log(b, j)
let n = 3, t = 0
while (n--) t += n
console.log(t, n)
let y = n++
++y
console.log(y, -n++, n)
