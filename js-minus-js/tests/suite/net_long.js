// read() buffers what one round trip brings (8 bytes on the
// page); a body of 62 bytes ends mid-buffer, and read() past
// the end keeps returning -1
var st = fetch("long.txt"), n = 0, sum = 0, c = read();
while (c >= 0) { n++; sum = (sum * 7 + c) % 10007; c = read(); }
console.log(st, n, sum, read(), read());
console.log(fetch("hello.txt"), String.fromCharCode(read()));
