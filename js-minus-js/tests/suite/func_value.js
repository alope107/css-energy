// a function's name is a value: printed as Node prints it
function myFunction(thing) { return thing + 1 }
var f = myFunction
console.log(myFunction, f === myFunction, typeof f)
console.log([f], {g: f}, typeof myFunction)
var fs = [myFunction, myFunction]
console.log(fs[0] === fs[1], f != null, !f)
