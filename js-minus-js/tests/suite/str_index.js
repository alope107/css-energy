// characters: s[i], charAt, charCodeAt, String.fromCharCode
var s = "Hello";
console.log(s[0], s[4], s.charAt(1), s.charCodeAt(1));
var r = "";
for (var i = s.length - 1; i >= 0; i--) r += s[i];
console.log(r);
var n = 0;
for (var i = 0; i < s.length; i++) if (s[i] === "l") n++;
console.log(n);
var c = "";
for (var k = 0; k < 5; k++) c += String.fromCharCode(65 + k);
console.log(c, c.charAt(9) === "", c.charCodeAt(0) + 1);
function rot(t) {
  var o = "";
  for (var i = 0; i < t.length; i++)
    o += String.fromCharCode((t.charCodeAt(i) - 84) % 26 + 97);
  return o;
}
console.log(rot("hello"), rot(rot("abc")));
