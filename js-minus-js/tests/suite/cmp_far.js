// comparisons of numbers far apart (their 20-bit difference overflows)
var a = 300000, b = -300000;
console.log(a < b, a > b, b < a);
console.log(a <= b, b >= a, a >= b);
console.log(500000 > -500000, -500000 < 400000);
var o = {n: 1};
console.log(o === o, 7 < -400000);
