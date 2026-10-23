// indexOf, includes: === (doubles by value, -0 is 0)
var c = [0, 0.5, NaN, -0, "a"]
console.log(c.indexOf(-0), c.indexOf(0.5), c.indexOf(NaN))
console.log(c.includes(NaN), c.lastIndexOf(0), c.indexOf(1 / 2))
console.log(c.includes(-0), c.indexOf("a"), [1].includes(NaN))
console.log([3].indexOf(3), [-0].indexOf(0))
