// runtime library (jsc dialect). Values: numbers; strings are tagged pointers (address - 262144; string data lives
// at 4352..4607, each string preceded by its tag word); booleans are 0/1. Cell 4096 (the first global slot, a hot
// cache line) holds the tag constant 262144, so untagging is one read (a constant that large needs SHL13, which
// traps). Printing is the machine's PRINT instruction family (machine/uarch.py), serviced by CSS on the page: it
// tells a string from a number at run time, and the compiler emits it inline, so nothing here prints by itself.
// addc(a, b): a + b inside a console.log argument when the types are not known to be numbers: if either is a
// string, print both (prn: the machine's PRINT, no separator) and return DONE (the tag of 4352, never a string),
// which PRINT prints as nothing; else the sum.
function addc(a, b) {
  var k = peek(4096); var s = 0;
  if (a < 0) { if (a + k >= 4352) { if (a + k < 4608) { s = 1; } } }
  if (b < 0) { if (b + k > 4352) { if (b + k < 4608) { s = 1; } } }
  if (s) { prn(a); prn(b); return 4352 - k; }
  return a + b;
}
