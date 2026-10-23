// arrays and strings that live across collections
// collections: gccat
var keep = [];
for (var i = 0; i < 60; i++) {
  var junk = [i, i + 1, i + 2, "x" + i];
  if (i % 10 == 0) keep.push(junk);
}
console.log(keep.length, keep[5][0], keep[5][3], keep[2][2]);
var big = [];
for (var i = 0; i < 300; i++) big.push(i);
var s = 0;
for (var i = 0; i < big.length; i++) s += big[i];
console.log(big.length, s);
var str = "";
for (var i = 0; i < 40; i++) str = str + (i % 10);
console.log(str.length, str.slice(30));
var o = {list: [], name: "n"};
for (var i = 0; i < 50; i++) o.list.push({v: i});
console.log(o.list.length, o.list[49].v, o.name + o.list[7].v);
