function sum(arr, n) {
  var s = 0;
  for (var i = 0; i < n; i++) { s = s + arr[i]; }
  return s;
}
var a = [1, 2, 3, 4];
console.log(sum(a, 4));
