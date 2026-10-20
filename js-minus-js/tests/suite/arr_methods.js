// array methods
var a = [5, 3, 8, 1];
console.log(a.join(), a.join(" - "), a.join(""));
console.log(a.indexOf(8), a.indexOf(9), a.includes(3));
console.log(a.lastIndexOf(5), a.lastIndexOf(2));
var b = a.slice(1, 3);
console.log(b.join(), a.slice(-2).join(), a.slice().length);
var c = a.concat([9, 7]).concat(6);
console.log(c.join(), c.length, a.length);
console.log(c.reverse().join(), c[0]);
var w = ["b", "a"];
console.log(w.indexOf("a"), w.includes("c"), ["x" + 1][0]);
var f = [0, 0, 0].fill(7);
console.log(f.join(), [1, [2, 3]].join(";"), [].join() === "");
console.log(String([1, 2]), [3, 4].toString(), "" + ["p", "q"]);
