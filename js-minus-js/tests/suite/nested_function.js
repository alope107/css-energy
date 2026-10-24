// a function declared inside a function
function f() { function g() { return 1; } return g() + 1; }
console.log(f());
