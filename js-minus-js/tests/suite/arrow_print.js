// console.log as an arrow's body or a return's value: undefined
const say = (s) => console.log("say " + s);
const r = say("hi");
console.log(r);
function shout(s) { return console.log(s.toUpperCase()); }
console.log(shout("loud"));
function last() { return console.log("x") + 1 }
console.log(last());
const mk = (i) => () => console.log("f" + i);
var fs = [];
for (let i = 0; i < 3; i++) fs.push(mk(i));
for (var j = 0; j < fs.length; j++) fs[j]();
setTimeout(() => console.log("later"), 10);
setTimeout(() => console.log("sooner", 1, 2), 5);
const twice = (f) => { f(); f(); };
twice(() => console.log("tw"));
const nested = a => b => console.log(a + b);
nested(1)(2);
