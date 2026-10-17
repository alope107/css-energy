// mixed key types: names, strings, numbers, computed keys
var o = {name: "box", 1: "one", "two words": 2, 30: 3};
console.log(o.name, o[1], o["two words"], o[30]);
o[2] = "two";
o["name"] = "crate";
var k = "name";
console.log(o[k], o.name, o[1 + 1]);
var s = "z";
o[s] = 26;
console.log(o.z, o["z"], o[s]);
for (var i = 0; i < 3; i++) o[i * 10] = i;
console.log(o[0], o[10], o[20], o[30], o[1]);
console.log("ab" === "ab", k === "name", k === s);
var m = {};
m[k] = 1; m[s] = 2; m.name += 10;
console.log(m.name, m.z);
