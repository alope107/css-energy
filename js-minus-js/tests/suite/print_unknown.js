function show(x) { console.log("[" + x + "]", x); }
show(-5);
show("str");
show(12);

var a = [3, -4];
console.log(a[0], a[1], later(), later() + "!");
function later() { return "late"; }
var v = later();
console.log(v);
var n = 4;
console.log(n + " items", 1 + n + "x", "y" + 1 + n);
function name(k) { if (k) return "ann"; return "bob"; }
console.log(name(1) + " & " + name(0) + "!");
