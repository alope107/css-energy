var x = 5, y = 0
console.log(x || 2 < 3, y < 1 && x, 2 < 3 && 3 < 4, y || x > 0)
console.log(y > 1 ? 7 : false, y < 1 ? 7 : !x, y ? "s" : x > 9)
function f(a, b, ) { return a + b }
console.log(f(1, 2, ), f(f(1, 1), 3))
