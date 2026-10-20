// run-time string keys survive garbage collections
var o = {};
for (var i = 0; i < 12; i++) o["key" + i] = "v" + i;
var junk = 0;
for (var j = 0; j < 400; j++) {
  var t = [j, "s" + j, {a: j}];
  junk += t[0] % 3;
}
var s = "";
for (var i = 0; i < 12; i += 3) s += o["key" + i] + ",";
console.log(s, junk);
o["key" + 5] += "!";
console.log(o.key5, o["ke" + "y11"], o.key0 + o.key1);
