// fetch a file through the network gateway and print it:
// watch the modem on the right, one round trip per byte
var st = fetch("hello.txt");
console.log(st);
var c = read();
while (c >= 0) { putc(c); c = read(); }
