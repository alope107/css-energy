// the sieve of Eratosthenes
const n = 60;
let sieve = [];
for (let i = 0; i <= n; i++) sieve.push(true);
for (let p = 2; p * p <= n; p++) {
  if (!sieve[p]) continue;
  for (let m = p * p; m <= n; m += p) sieve[m] = false;
}
let row = "";
for (let i = 2; i <= n; i++) {
  if (!sieve[i]) continue;
  if (row.length + String(i).length > 7) {
    console.log(row);
    row = "";
  }
  row += (row == "" ? "" : " ") + i;
}
console.log(row);
