const isEven = (number) => {
    return number % 2 === 0;
};
console.log(isEven(7), isEven(8));
const add = (firstNumber, secondNumber) => {
    return firstNumber + secondNumber;
};
console.log(add(1, 8));
const sq = x => x * x;
const three = () => 3;
var twice = (f, x) => f(f(x));
console.log(sq(5), three(), twice(sq, 3));
const adder = a => b => a + b;
console.log(adder(2)(40));
var o = {f: x => x + 1, g: (a, b) => a * b};
console.log(o.f(1), o.g(6, 7), typeof sq);
console.log((n => n - 1)(10), ((a) => a)("p"))
