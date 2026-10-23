// a function's parameter shadows a let of an enclosing block
var x = 5;
for (let i = 0; i < 2; i++) {
  let x = {a: i};
  var f = function (x) { return x + 1; };
  var g = function () { var i = 7; return i; };
  console.log(f(i), x.a, g(), i);
}
var y = 2;
{ let y = 1; (function () {})(); console.log(y); }
console.log(x, y);
