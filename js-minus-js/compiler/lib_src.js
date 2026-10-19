// runtime library (jsc dialect). Values: numbers; strings are tagged pointers (address - 262144; string data lives
// at data_base + 256 .. + 511, each string preceded by its tag word); booleans are 0/1. The first global slot (data_base,
// a hot cache line; __DATA_BASE__ is filled in by libbuild.js from layout.json) holds the tag constant 262144, so
// untagging is one read (a constant that large needs SHL13, which traps). Printing is the machine's PRINT instruction family (machine/uarch.py), serviced by CSS on the page: it
// tells a string from a number at run time, and the compiler emits it inline, so nothing here prints by itself.
// addc(a, b): a + b inside a console.log argument when the types are not known to be numbers: if either is a
// string, print both (prn: the machine's PRINT, no separator) and return DONE (the tag of 4352, never a string),
// which PRINT prints as nothing; else the sum.
function addc(a, b) {
  var k = peek(__DATA_BASE__); var s = 0;
  if (a < 0) { if (a + k >= __DATA_BASE__ + 256) { if (a + k < __DATA_BASE__ + 512) { s = 1; } } }
  if (b < 0) { if (b + k > __DATA_BASE__ + 256) { if (b + k < __DATA_BASE__ + 512) { s = 1; } } }
  if (s) { prn(a); prn(b); return __DATA_BASE__ + 256 - k; }
  return a + b;
}
// fetch(url): send the URL's bytes to the network gateway, one NET word each (256 + byte), then GET it (512): the HTTP
// status, or -1 if it failed. read(): the body's next byte, -1 at its end (768). The protocol: net/device.py.
function fetch(s) {
  var p = s + peek(__DATA_BASE__); var c = peek(p);
  while (c) { net(256 + c); p++; c = peek(p); }
  return net(512);
}
function read() { return net(768); }
