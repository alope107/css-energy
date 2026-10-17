// objects: literals, reads, writes, new properties
var p = {x: 1, y: 2};
console.log(p.x, p.y);
p.x = 5;
p.z = p.x + p.y;
console.log(p.z);
p.y += 10;
p.y++;
p.z--;
console.log(p.y, p.z);
var e = {};
e.a = 3
e.b = e.a * 2
console.log(e.a + e.b)
var q = p;
q.x = 9;
console.log(p.x, p === q, p === e);
console.log({v: 4}.v + {v: 5, w: 6}.w);
