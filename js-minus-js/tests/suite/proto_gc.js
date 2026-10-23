// prototype links (and a chunk that starts with one) survive
// the GC
// collections: gcnew
var base = {kind: "base",
  hello: function () { return "hi " + this.name; }};
var bare = Object.create(base);
var named = Object.create(base);
named.name = "n1";
function P(x) { this.x = x; }
P.prototype.get = function () { return this.x * 2; };
var p = new P(7), lost = new P(8);
lost = Object.create(lost);
var e = 0;
for (var j = 0; j < 94; j++) { e = {}; e = {}; e = {}; e = {}; }
console.log(bare.kind, bare.hello(), named.hello());
console.log(named.kind, p.get(), p.hasOwnProperty("x"));
console.log(p.hasOwnProperty("get"));
console.log(bare.hasOwnProperty("kind"));
console.log(bare.__proto__ === base);
var q = new P(3);
console.log(q.get(), Object.create(bare).kind, lost.get());
for (var k in named) console.log(k);
