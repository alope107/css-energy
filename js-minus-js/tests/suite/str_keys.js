// strings built at run time as object keys
var text = "the cat and the hat and the bat";
var words = text.split(" ");
var count = {};
for (var i = 0; i < words.length; i++) {
  var w = words[i];
  count[w] = (count[w] || 0) + 1;
}
console.log(count.the, count["and"], count["c" + "at"]);
var o = {};
for (var i = 0; i < 3; i++) o["k" + i] = i * 10;
console.log(o.k0, o.k1, o["k" + 2]);
var name = "x";
o[name + "y"] = 5;
o.xy += 1;
console.log(o.xy, o["x" + "y"]);
var keys = ["red", "green"];
var colors = {red: 1, green: 2};
var r = keys[0].slice(0, 3);
console.log(colors[keys[0]] + colors[keys[1]], colors[r]);
var big = {};
for (var i = 0; i < 40; i++) big["n" + (i % 5)] = i;
console.log(big.n0, big.n4, big["n" + 3]);
