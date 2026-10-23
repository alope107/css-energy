// Collatz: the longest chain below 30
let best = 0, arg = 0;
for (let n = 1; n < 30; n++) {
  let x = n, steps = 0;
  while (x != 1) {
    x = x % 2 == 0 ? x / 2 : 3 * x + 1;
    steps++;
  }
  if (steps > best) {
    best = steps;
    arg = n;
    console.log(n + ":" + steps);
  }
}
console.log("max " + arg);
