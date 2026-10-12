const a = [5, 3, 8, 1, 9, 2];
const n = 6;
for (let i = 0; i < n; i++)
  for (let j = 0; j + 1 < n - i; j++)
    if (a[j] > a[j + 1]) {
      let t = a[j]; a[j] = a[j + 1]; a[j + 1] = t;
    }
for (let i = 0; i < n; i++)
  console.log("a[" + i + "] = " + a[i]);
