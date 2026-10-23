// function expressions, nested functions, an IIFE, callbacks
var sq = function(x) { return x * x }
console.log(sq(5), typeof sq)
var myObj = { myFunc: function() { return "Hello!" }, n: 2 }
console.log(myObj.myFunc, myObj)
myObj.other = function() { return 1 }
console.log(myObj.other)
function outer(a) {
  function inner(b) { return b + 1 }
  var tw = function(c) { return c * 3 }
  return tw(inner(a)) * 10
}
console.log(outer(5))
var r = (function(){
  var temporary = 5; window.permanent = 10; return temporary + 1
})();
console.log(r, permanent)
function apply(f, v) { return f(v) }
console.log(apply(function(x) { return x + "!" }, "hi"))
console.log([function(){}][0], (function(a, b) { return b })(1))
