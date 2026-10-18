function name(n) {
  switch (n) {
    case 1: return "one"
    case 2:
    case 3: return "few"
    default: return "many"
  }
}
for (let i = 1; i < 5; i++) console.log(name(i))
let t = 0
for (let i = 0; i < 6; i++) {
  switch (i % 3) {
    case 0: t += 1; break
    case 1: t += 10
    case 2: t += 100; continue
  }
  t += 1000
}
console.log(t)
switch ("b") { default: console.log("d"); case "a": putc(65) }
switch (5) {}
switch (2) { case 1: console.log("x") }
switch (1 + 1) { case 2: { let q = 4; console.log(q) } }
console.log("end")
