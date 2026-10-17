let g = 3;
const c = 4;
function f(g) { var c = g + 1; return c * 10; }
function h() { let g = 9; { let g = 1; } return g + c; }
console.log(f(5), h(), g, c);
{ let g = 50; console.log(f(g)); }
console.log(g);
