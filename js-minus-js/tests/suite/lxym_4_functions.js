// learnxinyminutes 4: functions, scope and closures
function myFunction(thing) { return thing.toUpperCase(); }
console.log(myFunction("foo"));
function myFunction2() {
  return // <- semicolon automatically inserted here
  {thisIsAn: 'object literal'};
}
console.log(myFunction2());
function myFunction3() { console.log("later"); }
setTimeout(myFunction3, 5000);
setTimeout(function () { console.log("anon later"); }, 5000);
if (true) { var i = 5; }
console.log(i);
(function () {
  var temporary = 5;
  window.permanent = 10;
})();
console.log(typeof temporary, permanent);
function sayHelloInFiveSeconds(name) {
  var prompt = "Hello, " + name + "!";
  function inner() { alert(prompt); }
  setTimeout(inner, 5000);
}
sayHelloInFiveSeconds("Adam");
