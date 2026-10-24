// timers run after the program, by due time, then in order set
function later() { console.log("later"); }
setTimeout(later, 50);
setTimeout(function () { console.log("first"); }, 10);
setTimeout(() => { console.log("zero"); });
var n = 0;
var id = setInterval(function () {
  n++;
  console.log("tick", n);
  if (n === 3) {
    clearInterval(id);
    setTimeout(() => alert("done at " + n), 5);
  }
}, 20);
var t = setTimeout(function () { console.log("never"); }, 30);
clearTimeout(t);
function sayHello(name) {
  var prompt = "Hello, " + name + "!";
  function inner() { alert(prompt); }
  setTimeout(inner, 25);
}
sayHello("Adam");
console.log("main done");
