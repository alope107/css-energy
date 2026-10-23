// fetch a file through the network gateway and print it:
// watch the modems on the right: a round trip brings 8 bytes
var st = fetch("hello.txt");
console.log(st);
var c = read();
while (c >= 0) { putc(c); c = read(); }
