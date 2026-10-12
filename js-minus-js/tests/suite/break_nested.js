for (var i = 0; i < 4; i++) {
  for (var j = 0; j < 4; j++) {
    if (j > i) break;
    putc(48 + j);
  }
  putc(10);
}
