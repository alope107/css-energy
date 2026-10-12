function f(n) {
  for (var i = 0; i < 100; i++) { if (i * i >= n) return i; }
  return -1;
}
console.log(f(50));
console.log(f(1));
