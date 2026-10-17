// objects that grow past one chunk (3 pairs) and dictionaries
var o = {a: 1, b: 2, c: 3, d: 4, e: 5};
console.log(o.a, o.c, o.e);
o.f = 6; o.g = 7;
o.a = 10; o.g += 70;
console.log(o.a, o.f, o.g);
var sq = {};
for (var i = 0; i < 12; i++) sq[i] = i * i;
var t = 0;
for (var j = 0; j < 12; j++) t += sq[j];
console.log(sq[3], sq[11], t);
sq[5] = -1;
console.log(sq[4], sq[5], sq[6]);
