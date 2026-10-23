var a = ["Hello", 45, true, null, undefined];
console.log(a);
console.log([32, false, "js", 12].join(";"));
console.log([null, 1, undefined].join("-"));
var o = {k: 1};
console.log(o.k, o.missing, a[9], typeof o.missing);
var u;
console.log(u, typeof u, typeof 1, typeof "s", typeof true);
console.log(typeof null, typeof [1], typeof o, typeof nope);
console.log("13" + !0, 13 + !0, true + 1, null + 1);
console.log(-0, 0 * -1, 1 < 2, [1 < 2], !"", !"a");
console.log(undefined + 1, NaN, Infinity, -Infinity);
function f() {}
function g() { return; }
console.log(f(), g(), "x" + null + undefined);
var b = 1 > 2;
if (!b) console.log("not", b);
console.log(NaN === NaN, 0 === -0, null === null);
