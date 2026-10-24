// calls of values: any arguments; not a function: TypeError
function add(a, b) { return a + b }
function three() { return 3 }
var f = add, g = three
console.log(f(1, 2), g(), f(5), g(1, 2), [f][0](10, 20))
var fs = [add, three]
console.log(fs[1]() + fs[0](4, 5), (f)(7, 8))
function mk() { return add }
console.log(mk()(2, 2))
var n = 5
n(1)
