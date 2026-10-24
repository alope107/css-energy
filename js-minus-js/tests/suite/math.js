// Math: methods, constants, min / max as values
console.log(Math.min(42, 6, 27), Math.min([42, 6, 27]));
console.log(Math.min.apply(Math, [42, 6, 27]), Math.max(1, 9));
console.log(Math.floor(2.7), Math.round(-2.5), Math.round(2.5));
console.log(Math.PI, Math.E, Math.sqrt(2), Math.SQRT2);
console.log(Math.pow(2, 10), Math.abs(-3), Math.sign(-0.5));
console.log(Math.ceil(1.1), Math.trunc(-1.9), Math.exp(0));
console.log(Math.max(), Math.min(), typeof Math.min);
console.log(Math.max.call(null, 3, 7), Math.min(NaN, 1));
var mx = Math.max, bound = mx.bind(null, 100);
console.log(mx(4, 5), bound(5), bound(500));
var r = Math.random(), s = Math.random();
console.log(r >= 0 && r < 1, s !== r, Math.floor(10.99) % 3);
