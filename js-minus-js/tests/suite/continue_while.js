var i = 0;
var s = 0;
while (i < 10) {
  i++;
  if (i % 3 == 0) { continue; }
  s += i;
}
console.log(s);
