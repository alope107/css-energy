var n = 0;
function inc() { n = n + 1; return 1; }
if (0 && inc()) { }
if (1 || inc()) { }
console.log(n);
