// bitwise operators: 32-bit integers (ToInt32), precedence, op=
console.log(1 << 2, 5 & 3, 5 | 3, 5 ^ 3, ~5, ~-1, -9 >> 1)
console.log(-9 >>> 28, -1 >>> 0, 1 << 31, 1 << 32, 7 >> 33)
console.log(2.7 | 0, -2.7 | 0, "12" & 6, true << 3, NaN | 0)
console.log(4294967297 | 0, 1e21 | 0, 2147483648 >> 0, ~2.5)
console.log(1 + 2 << 3, 5 & 3 == 3, 1 | 2 ^ 3 & 4, 3 < 1 << 2)
var h = 7
for (var i = 0; i < 6; i++) { h = (h * 31 + i) | 0 }
console.log(h, h >>> 16, h & 65535)
var x = 6
x |= 9; x &= 13; x ^= 3; x <<= 4; x >>= 1; x >>>= 2
console.log(x, typeof (x & 1), ~~"77", -262144 & -1)
var m = 0
for (var b = 0; b < 20; b++) { if (b % 3 == 0) { m |= 1 << b } }
console.log(m, m
  ^ 1, [1, 2] | 0, [5] << 1, null >>> 1)
