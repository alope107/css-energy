// 700 frames of 4 words: past the old 1,408-word stack
function depth(n) {
  if (n == 0) { return 0; }
  return 1 + depth(n - 1);
}
console.log(depth(700));
