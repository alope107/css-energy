function name(d) {
  if (d == 0) return "zero";
  else if (d == 1) return "one";
  else if (d == 2) return "two";
  else if (d == 3) { return "three"; }
  else if (d == 4) return "four";
  else if (d == 5) return "five";
  else if (d == 6) return "six";
  else if (d == 7) { return "seven"; }
  else if (d == 8) return "eight";
  else if (d == 9) return "nine";
  else return "many";
}
for (var i = 0; i < 11; i++) console.log(i, name(i));
var x = 5, s = 0;
if (x == 1) s = 1; else if (x == 2) s = 2;
else if (x == 3) s = 3;
else if (x == 4) s = 4; else if (x == 5) s = 5; else s = 9;
console.log(s);
