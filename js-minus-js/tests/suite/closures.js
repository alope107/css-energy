// closures: inner functions share their outer frame's variables
function counter() {
  var n = 0
  return function() { n++; return n }
}
var c1 = counter(), c2 = counter()
console.log(c1(), c1(), c2(), c1())
function sayHello(name) {
  var prompt = "Hello, " + name + "!";
  function inner() { return prompt; }
  return inner;
}
console.log(sayHello("Adam")())
function adder(a) {
  var f = function(b) { return a + b }
  a = a * 10
  return f
}
function mk(k) {
  var x = k; var g = function() { x = x + 1; return x }
  g(); g(); return x
}
console.log(adder(2)(3), mk(5))
