function name(d) {
  if (d == 0) return "zero";
  else if (d == 1) return "one";
  else if (d == 2) return "two";
  return "many";
}
for (var i = 0; i < 4; i++) console.log(i + 0, name(i));
