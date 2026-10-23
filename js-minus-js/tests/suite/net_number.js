// parse a number from a response body, digit by digit
function getnum(url) {
  if (fetch(url) != 200) return -1;
  var v = 0, c = read();
  while (c >= 48 && c <= 57) {
    v = v * 10 + c - 48; c = read();
  }
  return v;
}
var x = getnum("n.txt");
console.log(x + 1, getnum("none"));
