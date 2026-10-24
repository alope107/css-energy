// prototypes, new, Object.create (learnxinyminutes)
var MyConstructor = function () { this.myNumber = 5; };
var myNewObj = new MyConstructor();
console.log(myNewObj.myNumber);
var myObj = { myString: "Hello world!" };
var myPrototype = { meaningOfLife: 42,
  myFunc: function () { return this.myString.toLowerCase(); } };
myObj.__proto__ = myPrototype;
console.log(myObj.meaningOfLife, myObj.myFunc());
myPrototype.__proto__ = { myBoolean: true };
console.log(myObj.myBoolean);
myPrototype.meaningOfLife = 43;
console.log(myObj.meaningOfLife);
for (var x in myObj) { console.log(myObj[x]); }
for (var x in myObj) {
  if (myObj.hasOwnProperty(x)) { console.log(myObj[x]); } }
var myObj2 = Object.create(myPrototype), p2 = myObj2.__proto__;
console.log(myObj2.meaningOfLife, p2 === myPrototype);
MyConstructor.prototype = { myNumber: 5,
  getMyNumber: function () { return this.myNumber; } };
var myNewObj2 = new MyConstructor();
console.log(myNewObj2.getMyNumber());
myNewObj2.myNumber = 6;
console.log(myNewObj2.getMyNumber(), myObj, myObj2);
