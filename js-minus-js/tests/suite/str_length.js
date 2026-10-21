// .length of strings, also of one first seen as a property name
var o = {name: 1, ab: 2};
var s = "hello";
console.log(s.length, "".length, "x\ny".length);
var k = "name";
console.log(k.length, o[k], "ab".length);
var t = 'it\'s';
console.log(t.length, t);
