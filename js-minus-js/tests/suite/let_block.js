let x = 1;
{ let x = 2; console.log(x); }
console.log(x);
if (x) { const x = 3; console.log(x) } else { let x = 4 }
console.log(x);
for (let x = 10; x < 12; x++) console.log(x);
console.log(x);
var t = 0;
for (let i = 0; i < 3; i++) {
  let x = i * 2; t += x; var w = x;
}
console.log(t, w, x);
function f(x) {
  let r = x;
  { let x = 7; r += x; }
  while (r < 20) { let x = 5; r += x; }
  return r + x;
}
console.log(f(100), f(1));
let s = 0;
{ { let s = 5; } s += 1; }
console.log(s);
