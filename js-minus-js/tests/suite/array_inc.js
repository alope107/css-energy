let c = [0, 5, 0];
c[1]++; c[2]--
c[0]++
for (let i = 0; i < 3; i++) c[i]++
let h = [0, 0, 0, 0]
const d = [1, 3, 3, 0, 3]
for (let i = 0; i < 5; i++) { h[d[i]]++ }
if (c[0] > 1) c[0]--
console.log(c[0], c[1], c[2], h[0], h[1], h[3])
