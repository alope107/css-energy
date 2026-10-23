// a function declared in a block (sloppy mode: hoisted to the function)
if (1) { function f() { return 1; } }
console.log(f());
function g(x) {
  if (x > 0) { function h() { return x * 2; } return h(); }
  return -1;
}
console.log(g(5), g(-1));
