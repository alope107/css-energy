// the towers of Hanoi: every move for 4 disks
let moves = 0;
function hanoi(n, from, to, via) {
  if (n == 0) return;
  hanoi(n - 1, from, via, to);
  moves++;
  if (n >= 3) console.log(n + ":" + from + ">" + to);
  hanoi(n - 1, via, to, from);
}
hanoi(4, "A", "C", "B");
console.log(moves + " moves");
