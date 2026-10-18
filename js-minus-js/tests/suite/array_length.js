var a = [3, 1, 4, 1, 5], e = []
console.log(a.length, e.length)
function sum(x) {
  let s = 0
  for (let i = 0; i < x.length; i++) s += x[i]
  return s
}
console.log(sum(a), sum([1, 2]))
let n = a.length - 1
console.log(a[n], [7, 8, 9].length, a[a.length - 2])
const o = {v: [1, 2, 3, 4]};
console.log(o.v.length)
let length = 2
console.log(length + a.length)
