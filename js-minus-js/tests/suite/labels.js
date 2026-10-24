// labeled loops: break / continue a named one
outer:
for (var i = 0; i < 10; i++) {
    for (var j = 0; j < 10; j++) {
        if (i == 5 && j ==5) {
            break outer;
        }
    }
}
console.log(i, j)
var n = 0
rows: for (var r = 0; r < 4; r++) {
  var c = 0
  while (c < 4) {
    c++
    if (c == 2) continue rows
    if (r == 3) break
    n++
  }
}
console.log(r, c, n)
k: do { n++; if (n > 10) break k } while (true)
console.log(n)
