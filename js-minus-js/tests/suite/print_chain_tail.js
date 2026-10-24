// a + chain in console.log past its pieces: a string piece
// takes the rest of the chain
var a = 1, b = "B", c = 3;
console.log(a + ":" + b + ">" + c + "<" + a + b);
console.log(a + ":" + b + ">" + c * 2 + "!" + (a + c));
console.log("x" + a + b + c + 1 + 2);
console.log(a + "-" + b + "-" + c - 1);
console.log(1, a + "y" + b + "z" + c + a, 2);
console.log(a + ":" + b + ">" + (c > 2 ? "big" : "no") + a);
console.log(a + ":" + b + ">" + c + "<" + a + b + "." + c + 5);
var s = a + ":" + b + ">" + c + "<" + a;
console.log(s, a + b + c + "-" + a + c);
