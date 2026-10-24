// var and function declarations are hoisted; var ignores blocks
console.log(a, typeof a);
var a = 1;
console.log(sq(4));
function sq(n) { return n * n; }
var t = later;
var later = "set";
console.log(t, later);
if (true) {
  var i = 5;
}
console.log(i);
for (var j = 0; j < 2; j++) { var y; console.log(y); y = 5; }
var a2 = [1, a2];
console.log(a2[1], typeof a2[1]);
function f() { return late2 + 1; }
console.log(f());
var late2 = 1;
console.log(f(), 0.5 + 0.25);
