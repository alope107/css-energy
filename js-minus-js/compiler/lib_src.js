// runtime library (jsc dialect). Values: numbers; strings are tagged pointers (address - 262144; string data lives
// at 4352..4607, each string preceded by its tag word); booleans are 0/1. Cell 4096 (the first global slot, a hot
// cache line) holds the tag constant 262144, so untagging is one read (a constant that large needs SHL13, which
// traps). The compiler types values statically and calls printNum, printBool or puts; each one also checks the
// value at run time where that is free or cheap, so a wrong static guess still prints correctly (printNum looks
// for a string only among negative values; puts takes a non-negative value for a number; printBool prints a
// value other than 0 / 1 as what it is). None of them prints a separator: the ...Ln entries
// add a newline, other separators are emitted by the caller.
// addc(a, b): a + b inside a console.log argument when the types are not known to be numbers: if either is a
// string, print both and return DONE (the tag of 4352, never a string), which printNum skips; else the sum.
function printNum(n) {
  if (n < 0) {
    var p = n + peek(4096);
    if (p >= 4352) { if (p < 4608) { if (p == 4352) { return 0; } return puts(n); } }
    putc(45); n = 0 - n;
  }
  if (n >= 10) { printNum((n - n % 10) / 10); }
  putc(48 + n % 10);
  return 0;
}
function puts(s) {
  if (s < 0) { s = s + peek(4096); while (s[0] != 0) { putc(s[0]); s++; } return 0; }
  return printNum(s);
}
function printBool(b) {
  if (b == 0) { putc(102); putc(97); putc(108); putc(115); putc(101); return 0; }
  if (b == 1) { putc(116); putc(114); putc(117); putc(101); return 0; }
  return printNum(b);
}
function addc(a, b) {
  var k = peek(4096); var s = 0;
  if (a < 0) { if (a + k >= 4352) { if (a + k < 4608) { s = 1; } } }
  if (b < 0) { if (b + k > 4352) { if (b + k < 4608) { s = 1; } } }
  if (s) { printNum(a); printNum(b); return 4352 - k; }
  return a + b;
}
// newline-terminated entries (console.log's last argument): one CALL word at the call site
function printNumLn(n) { printNum(n); putc(10); return 0; }
function putsLn(s) {
  if (s < 0) { s = s + peek(4096); while (s[0] != 0) { putc(s[0]); s++; } putc(10); return 0; }
  printNum(s); putc(10); return 0;
}
function printBoolLn(b) {
  if (b == 0) { putc(102); putc(97); putc(108); putc(115); putc(101); putc(10); return 0; }
  if (b == 1) { putc(116); putc(114); putc(117); putc(101); putc(10); return 0; }
  printNum(b); putc(10); return 0;
}
