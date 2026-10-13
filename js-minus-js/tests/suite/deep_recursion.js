// deep recursion: 1000 frames of 3 words need 3,000 words of stack (the old 1,408-word stack overflowed into the console)
function depth(n) {
  if (n == 0) { return 0; }
  return 1 + depth(n - 1);
}
console.log(depth(1000));
console.log(depth(2000) + depth(500));
