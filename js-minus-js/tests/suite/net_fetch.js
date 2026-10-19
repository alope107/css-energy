// fetch(url) GETs a file through the network gateway (from
// tests/net/ here) and returns the HTTP status; read() then
// returns the body's bytes, -1 at its end
var st = fetch("hello.txt");
console.log(st);
var c = read();
while (c >= 0) { putc(c); c = read(); }
console.log(read());
