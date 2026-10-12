var a = [1, 2, 3];
a[1] += 5;
a[2] *= a[1];
for (var i = 0; i < 3; i++) a[i] -= 1;
console.log(a[0], a[1], a[2]);
