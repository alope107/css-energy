var a = [4, 2, 5, 1, 3];
for (var i = 0; i < 5; i++) {
  for (var j = 0; j < 4 - i; j++) {
    if (a[j] > a[j + 1]) {
      var t = a[j]; a[j] = a[j + 1]; a[j + 1] = t;
    }
  }
}
for (var k = 0; k < 5; k++) { console.log(a[k]); }
