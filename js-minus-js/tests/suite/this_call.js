// this in methods, call / apply / bind (learnxinyminutes)
var myObj = { myString: "Hello world!",
  myFunc: function () { return this.myString; } };
console.log(myObj.myFunc());
var myFunc = myObj.myFunc;
console.log(myFunc());
var other = function () { return this.myString.toUpperCase(); };
myObj.myOtherFunc = other;
console.log(myObj.myOtherFunc());
var another = function (s) { return this.myString + s; };
console.log(another.call(myObj, " And Hello Moon!"));
console.log(another.apply(myObj, [" And Hello Sun!"]));
var boundFunc = another.bind(myObj);
console.log(boundFunc(" And Hello Saturn!"));
var product = function (a, b) { return a * b; };
var doubler = product.bind(this, 2);
console.log(doubler(8), product.bind(null, 3, 4)());
var c = { n: 5, inc: function () { this.n++; return this.n; } };
console.log(c.inc(), c.inc(), c["inc"](), c.n);
var o2 = { v: 3, get: function () { return (() => this.v)() } };
console.log(o2.get(), typeof this, this === globalThis);
function Top() { return this === globalThis; }
console.log(Top(), Top.call(c));
