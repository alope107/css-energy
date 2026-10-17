var s = 0, i = 0;
do {
  let j = 0;
  do { s += j; j++; } while (j < i)
  i++;
} while (i < 4);
console.log(s);
if (s > 5) do s--; while (s > 5) else s = 0;
console.log(s);
if (s) do s++; while (s < 8)
else s = 99
console.log(s);
for (i = 0; i < 2; i++) do s += 100; while (false);
console.log(s);
while (s > 200) do { s -= 50; } while (s % 7 != 0)
console.log(s);
{ do s = 1; while (0) }
console.log(s)
do do s += 2; while (s < 5); while (s < 20)
console.log(s)
