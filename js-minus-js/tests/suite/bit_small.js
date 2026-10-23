// bitwise: the machine's fast path and the library's (32 bits)
var a = 12, b = 10
console.log(a & b, a | b, a ^ b, ~a, a << 3, -a >> 2)
console.log(-1 >>> 28, 3 << 30, 1.5 | 0, true ^ 1)
a &= 7; a <<= 2
console.log(a)
