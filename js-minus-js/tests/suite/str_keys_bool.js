// keys from String(boolean) and "true" built at run time
var o = {};
o[String(true)] = 1;
o["tr" + "ue"] += 1;
console.log(o["true"], o[String(1 < 2)]);
o.false = 5;
console.log(o[String(1 > 2)]);
