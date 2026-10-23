// names without var are globals; window.x is x
someOtherVar = 10;
grade = 'B';
function f() {
  window.permanent = 10; counter = 3; return later + 1
}
var later = 5;
console.log(f(), permanent, counter, someOtherVar, grade)
var someOtherVar;
console.log(someOtherVar, window.grade, typeof nothing)
function g() { return early }
early = "e"
console.log(g(), window.later + 1)
