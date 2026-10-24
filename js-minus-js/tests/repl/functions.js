function sq(x) {
  return x * x
}
sq(9)
sq
var add = (a, b) => a + b
add(2, 3)
(function () { return "iife" })()
[1, 2, 3]
function Pt(x, y) { this.x = x; this.y = y }
new Pt(1, 2).y
var mk = function (n) {
  return function () { return n + 1 }
}
mk(41)()
var p = {
  name: "p",
  hi: function () { return "hi " + this.name }
}
p.hi()
