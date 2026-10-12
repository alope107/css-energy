function pos(x) { return x > 0; }
function both(a, b) { return pos(a) && pos(b); }
console.log(both(1, 2));
console.log(both(1, -2));
