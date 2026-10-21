// the empty string is false; any other string is true
var e = "", s = "x";
if (e) console.log("bad"); else console.log("empty is false");
if (s) console.log("x is true");
console.log(!e, !s, e ? 1 : 2, s ? 3 : 4);
console.log(e || "default", s || "no", e && "no", s && "yes");
var t = "abc";
var n = 0;
while (t) { t = t.slice(1); n++; }
console.log(n, t.length, "[" + t + "]");
function first(a) {
  for (var i = 0; i < a.length; i++) if (a[i]) return a[i];
  return "none";
}
console.log(first(["", "", "z"]), first(["", 0]));
var words = ["a", "", "b"];
var out = [];
for (var i = 0; i < words.length; i++)
  if (!words[i]) out.push(i);
console.log(out.join());
