// console.log of arrays and objects: Node's one-line form
var a = [1, "it's", [2, [3, [4, [5]]]]];
console.log(a);
console.log([], {}, [""], ["a\tb", "q\"r"]);
var o = {name: "n", list: [1, 2], o: {p: {q: {}}}};
console.log(o);
console.log({k: 1, "a b": [], 7: "x"}, [{x: [1]}]);
var s = [];
for (var i = 0; i < 4; i++) s.push(i * 3);
console.log(s, s.length);
function show(v) { console.log("v=" + v, v); }
show([3, 4]);
show({x: 1});
show("s");
