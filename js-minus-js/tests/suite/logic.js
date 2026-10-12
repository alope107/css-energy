var a = 1;
var b = 0;
if (a && !b) { console.log(1); }
if (a || b) { console.log(2); }
if (b && a) { console.log(3); }
if (!a || b) { console.log(4); }
