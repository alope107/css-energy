for (var n = 2; n < 30; n++) {
  var p = 1;
  for (var d = 2; d * d <= n; d++) {
    if (n % d == 0) { p = 0; }
  }
  if (p) { console.log(n); }
}
