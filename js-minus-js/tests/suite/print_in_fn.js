function show(n) {
  console.log(n)
  return n + 1
}
function twice(n) {
  let k = n * 2
  let m = show(k)
  return k + m
}
console.log(twice(3))
for (let i = 0; i < 3; i++) console.log(show(i))
function noargs() { console.log(); return 7 }
console.log(noargs())
