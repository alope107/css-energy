function isPrime(n) {
  if (n < 2) return false;
  for (var i = 2; i * i <= n; i++)
    if (n % i == 0) return false;
  return true;
}
for (var k = 0; k < 12; k++) console.log(k, isPrime(k));
