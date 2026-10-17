// arrays holding objects
var a = [0, 0, 0];
for (var i = 0; i < 3; i++) a[i] = {n: i, sq: i * i};
console.log(a[2].sq, a[1].n);
a[1].n = 50;
a[2].sq += 5;
console.log(a[1].n, a[2].sq);
var b = {list: [1, 2, 3], o: {arr: [4, 5]}};
console.log(b.list[2], b.o.arr[1]);
b.list[0] = 10;
console.log(b.list[0] + b.o.arr[0]);
