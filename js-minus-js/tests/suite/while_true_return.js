function find(t) {
  var i = 0;
  while (true) {
    if (i * i >= t) return i;
    i++;
  }
}
console.log(find(50));
