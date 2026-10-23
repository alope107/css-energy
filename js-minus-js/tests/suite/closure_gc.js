// closures through garbage collections (env cells move)
function counter(start) {
  var n = start
  return function(d) { n = n + d; return n }
}
var keep = []
for (var i = 0; i < 300; i++) {
  var c = counter(i)
  c(1)
  if (i % 50 == 0) keep.push(c)
  var junk = {a: [i, i + 1], b: "x" + i}
}
var s = 0
for (var j = 0; j < keep.length; j++) s += keep[j](100)
console.log(keep.length, s)
