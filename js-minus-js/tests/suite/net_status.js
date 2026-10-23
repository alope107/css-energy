// a missing file is 404 with an empty body; a URL outside the
// gateway's files fails with -1. A string variable is a URL.
var u = "/data/lines.txt", missing = "nope.txt";
console.log(fetch(missing), read());
console.log(fetch("http://x/"));
if (fetch(u) === 200) {
  var n = 0, c = read();
  while (c >= 0) { if (c == 10) n++; c = read(); }
  console.log("lines", n);
}
