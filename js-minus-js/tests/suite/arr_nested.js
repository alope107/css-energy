// arrays of arrays: a grid, compound assignment, counts
var g = [];
for (var r = 0; r < 4; r++) {
  g.push([]);
  for (var c = 0; c < 4; c++) g[r].push(r * c);
}
console.log(g[3][2], g[2][3], g.length, g[1].length);
g[1][1] += 10;
g[2][2]++;
g[0][3] = g[3][3] * 2;
console.log(g[1][1], g[2][2], g[0][3]);
var t = 0;
for (var r = 0; r < 4; r++)
  for (var c = 0; c < 4; c++) t += g[r][c];
console.log(t);
var rows = [];
for (var r = 0; r < 3; r++) rows.push(g[r].join(""));
console.log(rows.join("/"));
var cnt = [0, 0, 0];
var xs = [2, 0, 2, 1, 2];
for (var i = 0; i < xs.length; i++) cnt[xs[i]]++;
console.log(cnt.join());
