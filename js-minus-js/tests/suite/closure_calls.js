// calls of inner functions through values: the env goes along
function mk(n) {
  var k = n * 10;
  function add(a, b) { return k + a + b; }
  function who() { return this.name + k; }
  var fact = function (m) { return m < 2 ? k : m * fact(m - 1) }
  return [add, who, fact, (x) => x + k, (() => k)];
}
var fs = mk(2), add = fs[0], who = fs[1], fact = fs[2];
console.log(add(1, 2), add(1), add(1, 2, 3), fact(4));
var o = {name: "o", who: who, add: add};
console.log(o.who(), o.add(5, 5), who.call({name: "c"}));
console.log(add.apply(null, [3, 4]), add.call(o, 1, 1));
var b = add.bind(null, 100);
console.log(b(1), fs[3](7), fs[4](), fs[3]());
function counter() {
  var c = 0;
  return {inc: function () { c++; return c; },
          get: () => c};
}
var c1 = counter(), c2 = counter();
c1.inc(); c1.inc(); c2.inc();
console.log(c1.get(), c2.get(), c1.inc(), c2.inc());
