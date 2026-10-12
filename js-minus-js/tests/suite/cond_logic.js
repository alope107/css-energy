var n = 0;
for (var x = -2; x <= 2; x++)
  for (var y = -2; y <= 2; y++)
    if ((x > 0 && y > 0) || (x < 0 && y < 0)) n++;
console.log(n);
if (!(n > 100) && n != 0) console.log("ok");
