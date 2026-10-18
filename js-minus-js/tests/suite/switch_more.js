function sign(x) {
  switch (true) {
    case x < 0: return -1
    case x > 0: return 1
    default: return 0
  }
}
console.log(sign(-5), sign(0), sign(9))
var k = 0, out = 0
while (k < 4) {
  if (k > 1) switch (k) {
    case 2: out += 20; break
    case -1 + 4 ? 3 : 0: out += 300
  } else out += 1
  k++
}
console.log(out)
switch (3) {
  case 1: case 2: console.log("no"); break
  default:
    switch (out % 2) { case 0: console.log("even"); break }
    console.log("dflt")
  case 4: let z = 4; console.log(z)
}
