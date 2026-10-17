let x = 3;
console.log(x > 2 ? true : false);
console.log(x > 5 ? 1 > 0 : 2 < 1);
console.log(x == 3 ? "s" : "t", x == 3 ? "s" : 0);
console.log("x is " + (x % 2 ? "odd" : "even"));
let s = x > 1 ? "big" : "small";
console.log(s, x < 1 ? "neg" : x < 3 ? "low" : "high");
let k = x > 0 ? x : 0;
console.log(k, x ? 0 : 1, x > 0 ? false : x < 9);
