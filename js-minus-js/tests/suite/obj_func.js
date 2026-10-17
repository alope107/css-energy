// objects through functions; x[k] on parameters (arrays too)
function get(o, k) { return o[k]; }
function put(o, k, v) { o[k] = v; }
function pt(x, y) { return {x: x, y: y}; }
function add(a, b) { return pt(a.x + b.x, a.y + b.y); }
var p = add(pt(1, 2), pt(10, 20));
console.log(p.x, p.y);
var arr = [5, 6, 7];
console.log(get(arr, 1), get(p, "y"));
put(arr, 2, 70);
put(p, "x", 11);
put(p, "w", 9);
console.log(arr[2], p.x, get(p, "w"));
function bump(o, k) { o[k] += 1; o[k]++; }
bump(p, "x");
bump(arr, 0);
console.log(p.x, arr[0]);
