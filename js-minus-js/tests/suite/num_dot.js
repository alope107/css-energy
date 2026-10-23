// a number's trailing dot is part of it: 1. is 1 (so 1.x is a
// syntax error, as in JavaScript: suite_err/num_dot_id)
var a = 1.;
console.log(a + 2., [3.][0], 4. * 2);
var o = {n: 5};
console.log(o.n, [6, 7][1] + 8., "9." + 1);
for (var i = 0.; i < 2.; i++) console.log(i);
