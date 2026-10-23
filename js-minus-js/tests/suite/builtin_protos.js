// wrappers, String.prototype, a polyfill (learnxinyminutes)
var myNumber = 12;
var myNumberObj = new Number(12);
console.log(myNumber == myNumberObj, typeof myNumber);
console.log(typeof myNumberObj, myNumber === myNumberObj);
if (0) { console.log("0 is truthy"); }
if (new Number(0)) { console.log("wrapped numbers: truthy"); }
var w = new String("ab");
console.log(myNumberObj + 1, w + "c", myNumberObj);
String.prototype.firstCharacter = function () {
  return this.charAt(0);
};
var s = "xyz";
console.log("abc".firstCharacter(), s.firstCharacter(), s.no);
if (Object.create === undefined) {
  Object.create = function (proto) {
    var Constructor = function () {};
    Constructor.prototype = proto;
    return new Constructor();
  };
}
console.log(Object.create({a: 1}).a, typeof Object.create);
console.log(new Object(), new String("q"), Math.PI > 3);
