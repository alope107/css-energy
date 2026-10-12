// nested if / else if chains, while with break-free loops, putc, strings with escapes
var x = 0;
while (x < 7) {
  if (x == 0) { putc(65); }
  else if (x == 1) { putc(66); }
  else if (x == 2) { if (x % 2 == 0) { putc(67); } else { putc(68); } }
  else { putc(48 + x); }
  x = x + 1;
}
putc(10);
console.log("a\nb");
var q = 17 / 5 + 17 % 5 * 100 - (3 - 10) * 2;
console.log(q);
console.log((1 + 2) * (3 + 4) / 7 == 3 != 0);
