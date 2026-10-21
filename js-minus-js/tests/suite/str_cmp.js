// strings compare by their characters
var a = "ab" + "c";
var b = "a" + "bc";
console.log(a === b, a == "abc", a !== b, a != "abd");
console.log("abc" < "abd", "ab" < "abc", "b" > "abc", a <= b);
console.log("Z" < "a", "" < "a", "10" < "9", a >= "abd");
function same(x, y) { return x === y; }
console.log(same(a, "abc"), same(a, b), same("1", 1));
var k = "f" + "oo";
switch (k) {
  case "bar": console.log("bar"); break;
  case "foo": console.log("foo!"); break;
  default: console.log("none");
}
var words = ["pear", "apple", "fig"];
var best = words[0];
for (var i = 1; i < 3; i++)
  if (words[i] < best) best = words[i];
console.log(best);
