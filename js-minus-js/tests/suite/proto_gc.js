// prototype links (and chunks starting with one) survive the GC
var base = {kind: "base",
  hello: function () { return "hi " + this.name; }};
var keep = [];
for (var i = 0; i < 200; i++) {
  var o = Object.create(base);
  o.name = "n" + i;
  if (i % 50 === 0) keep.push(o);
}
for (var j = 0; j < keep.length; j++) {
  console.log(keep[j].hello(), keep[j].kind);
}
function P(x) { this.x = x; }
P.prototype.get = function () { return this.x * 2; };
var ps = [];
for (var k = 0; k < 150; k++) {
  var p = new P(k);
  if (k % 40 === 0) ps.push(p);
}
for (var m = 0; m < ps.length; m++) {
  var q = ps[m];
  console.log(q.get(), q.hasOwnProperty("x"));
  console.log(q.hasOwnProperty("get"));
}
