function five() { return 5 }
function nothing() { return }
var x = 0
if (five() > 3) { x = 1 } else { x = 2 }
nothing()
console.log(x)
var c = 0
for (var i = 0; i < 5; i++) { if (i % 2) c++ }
console.log(c)
while (c < 10) { if (c < 4) c += 3; else c++ }
console.log(c)
{ var z }
z = 3
console.log(z)
