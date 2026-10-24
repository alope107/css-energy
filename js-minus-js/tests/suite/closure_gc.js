// closures through a GC: the live ones' env cells move, the
// others' are collected
// collections: gcnew
function counter(start) {
  var n = start
  return function(d) { n = n + d; return n }
}
var keep = []
for (var i = 0; i < 8; i++) {
  var c = counter(i * 10)
  c(1)
  if (i % 2 == 0) keep.push(c)
}
var e = 0
for (var j = 0; j < 92; j++) { e = {}; e = {}; e = {}; e = {} }
var s = 0
for (var k = 0; k < keep.length; k++) s += keep[k](100)
console.log(keep.length, s, counter(5)(5))
