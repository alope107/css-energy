// insertion sort, then a binary search
let a = [42, 7, 19, 3, 88, 25, 61, 14, 50, 9];
for (let i = 1; i < a.length; i++) {
  let x = a[i];
  let j = i - 1;
  while (j >= 0 && a[j] > x) {
    a[j + 1] = a[j];
    j--;
  }
  a[j + 1] = x;
}
function find(v) {
  let lo = 0, hi = a.length - 1;
  while (lo <= hi) {
    const mid = lo + (hi - lo - (hi - lo) % 2) / 2;
    if (a[mid] == v) return mid;
    if (a[mid] < v) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}
for (let i = 0; i < a.length; i += 3)
  console.log(a.slice(i, i + 3).join());
console.log("61 at " + find(61));
