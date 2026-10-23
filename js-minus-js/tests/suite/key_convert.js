// keys that are arrays or booleans are strings; a["0"] is a[0]
var p = {}
p.bc = 2
var a = [5, 6]
a["1"] = 7
console.log(p[ ["bc"] ], a["0"], a, "abc"["2"])
console.log(p[true], {true: 1}[true])
