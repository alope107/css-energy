// The register machine's runtime library, compiled into ROM by compiler/cc_ref.py (rom mode: rtlib.py fills in the upper-case
// constants between double underscores). The dialect: functions, locals, while / for / if, peek(a) / poke(a, v) and p[i] on raw
// memory, putc, prn(v) (PRINT), halt(), __fp() (this frame's fp), __dadd(a, b) (the + of a string in CSS: the cat class; a
// full heap traps to gccat, which collects), and the machine's primitives (cc_ref.OPN): __kind(v, K) tests a kind,
// __alloc(n, A) allocates (and collects when the heap is full), __mcpy / __mupper / __mlower (d, s, n) copy, __mfill(d, v, n)
// fills, __nput(p, v) writes a number's digits, __mcmp(p, q, n) / __mfeq(p, v, n) / __mfref(p, flo, n) search, __mwalk(p, e, n)
// walks the string area, __apush(x, v) pushes and returns: a cache line per execution where a loop here takes an instruction
// per word. No globals and no string literals (they would land in the program's data area). Locals live in frames, which the
// collector scans; a raw address must not be held across anything that allocates.
//
// Values: numbers; a string is its first byte's address - STRTAG, a literal in the string area or a heap string; an
// array its ptr word's address + ARRTAG; an object its chunk's address - OBJTAG; booleans 0 / 1. Addresses are masked to 15
// bits and the tags are multiples of 32768, so a string's or an array's value is its address as far as peek, poke and the
// primitives go (peek(x - 1): its length; peek(x): an array's element pointer).
// Heap blocks are 8-aligned, a multiple of 8 words: object chunks [k0 v0 k1 v1 k2 v2 L pad] (a key is a value + KBIAS, so
// k0 >= 0; 0 ends the keys; L links an overflow chunk), strings [hdr len bytes... 0], arrays [hdr cap len ptr elements...]
// (ptr: the elements, inline until the array grows past cap, then a raw block of its own); hdr = -2 - words - kind (kind 0
// string, 1 array); a block the collector moved has -1 and its copy's address in its first two words.
//
// The machine calls the routines below its trapping instructions name (cc_ref.TRAPS, CATTRAPS) like functions: dadd ... dne
// for the dynamic operators on an array or object (and == / != of two strings, the others with a string); getx / setx for
// x[k] other than an array inside its length or an object with a number or the program's string as its key; setp when a
// chunk is full; gcnew, galloc and gccat when NEW, ALLOC or a string's + find the heap full; pval to print an array or
// object. The compiler calls the methods, mkarrN (array literals) and parseint / tostring / fromcc directly.

function rnd8(n) { return n + (8 - n % 8) % 8; }

// ---------------- allocation and the collector
// NEW found the heap full: collect; NEW executes again when this returns
function gcnew() { gc(8); return 0; }
// ALLOC found the heap full (nw: its block's words): collect; ALLOC executes again
function galloc(nw) { gc(nw); return 0; }
// a string's + found the heap full: collect, then join (DADDL / DADDR: that side's boolean as its string)
function gccat(a, b) { gc(catw(a, b)); return __dadd(a, b); }
function gccatl(a, b) { a = boolstr(a); gc(catw(a, b)); return __dadd(a, b); }
function gccatr(a, b) { b = boolstr(b); gc(catw(a, b)); return __dadd(a, b); }
function boolstr(v) { if (v == 1) { return __TRUEV__; } if (v == 0) { return __FALSEV__; } return v; }
// v's characters: a string's length, a number's digits
function clen(v) { if (__kind(v, __K_STR__)) { return peek(v - 1); } return __kind(v, __K_NLEN__); }
function catw(a, b) { return rnd8(clen(a) + clen(b) + 3); }
// Cheney's copying collector between the two semi-spaces. HP / GCLIM are offsets from HEAP0: the next free word and the
// current space's start (0: space A, as RAM starts). The roots: the globals, and the stack from SP0 up to this routine's
// frame. Stack words are conservative: a word is a reference only if its block is in the map (MAP, a bit per 8 heap words:
// ALLOC, NEW and a string's + mark the blocks they make, the copies here mark theirs in to-space), so a stale word in a frame
// keeps a dead block alive at worst. The frames' return words (off = the word / 8192) are skipped; MFREF skips the words that
// refer to nothing in from-space a line at a time. Then need more words must fit, or the program stops.
function gc(need) {
  var from = __HEAP0__; var to = __HEAP0__ + __H__; var p = 0; var e = 0; var i = 0; var x = 1;
  if (peek(__GCLIM__)) { from = __HEAP0__ + __H__; to = __HEAP0__; }
  poke(__G_FLO__, from); poke(__G_FREE__, to);
  while (i < 16) { poke(__POWT__ + i, x); x = x * 2; i++; }
  __mfill(__MAP__ + (to - __HEAP0__) / 128, 0, __MAPH__);
  fwdrange(__DB__ + 1, __DB__ + peek(__INIT__ - 1), 0);
  p = __fp(); e = p - peek(p) / 8192;
  while (p > __SP0__) { fwdrange(e + 1, p, 1); p = e; e = p - peek(p) / 8192; }
  p = to;
  while (p < peek(__G_FREE__)) { p = p + scan(p); }
  poke(__HP__, peek(__G_FREE__) - __HEAP0__); poke(__GCLIM__, to - __HEAP0__);
  if (peek(__HP__) + need > peek(__GCLIM__) + __H__) { oom(); }
  return 0;
}
function oom() {
  putc(10); putc(111); putc(117); putc(116); putc(32); putc(111); putc(102); putc(32);
  putc(109); putc(101); putc(109); putc(111); putc(114); putc(121); putc(10); halt();
  return 0;
}
// the block at b in the map (it starts a block made since the space was cleared) / marked in it
function mark(b) { var x = (b - __HEAP0__) / 8; var h = __MAP__ + x / 16; poke(h, peek(h) + peek(__POWT__ + x % 16)); return 0; }
function marked(b) { var x = (b - __HEAP0__) / 8; return (peek(__MAP__ + x / 16) / peek(__POWT__ + x % 16)) % 2; }
// the references in [p, e) forwarded (stk: stack words, which are conservative)
function fwdrange(p, e, stk) {
  var flo = peek(__G_FLO__);
  while (p < e) {
    p = p + __mfref(p, flo, e - p);
    if (p < e) { if (stk) { poke(p, fwdc(peek(p), flo)); } else { poke(p, fwd(peek(p))); } p++; }
  }
  return 0;
}
// a copied block's references: an object's keys and values up to its first free pair (and its link if all three are used), an
// array's elements up to its length. -> the block's size
function scan(s) {
  var h = peek(s); var i = 0; var go = 1; var x = 0;
  if (h >= 0) {
    while (go) {
      if (peek(s + i) == 0) { go = 0; }
      else {
        poke(s + i, fwdkey(peek(s + i))); poke(s + i + 1, fwd(peek(s + i + 1))); i = i + 2;
        if (i == 6) { poke(s + 6, fwd(peek(s + 6))); go = 0; }
      }
    }
    return 8;
  }
  x = 0 - 2 - h;
  if (x % 8 == 1) { fwdrange(s + 4, s + 4 + peek(s + 2), 0); }
  return x - x % 8;
}
// a value -> the same value after the collection: a from-space object, string or array is copied (once); anything else is
// left as it is
function fwd(w) {
  var flo = peek(__G_FLO__); var a = w + __OBJTAG__;
  if (a >= flo) { if (a < flo + __H__) { return fwdobj(w, a); } }
  a = w + __STRTAG__;
  if (a >= flo + 2) { if (a < flo + __H__) { return fwdblk(w, a - 2, 0); } }
  a = w - __ARRTAG__;
  if (a >= flo + 3) { if (a < flo + __H__) { return fwdblk(w, a - 3, 1); } }
  return w;
}
// a stack word: a reference only if it starts a block in the map (MFREF found it in a from-space tag range)
function fwdc(w, flo) {
  var b = w + __OBJTAG__;
  if (b >= flo + __H__) { b = w + __STRTAG__ - 2; if (b >= flo + __H__) { b = w - __ARRTAG__ - 3; } }
  if ((b - flo) % 8) { return w; }
  if (marked(b) == 0) { return w; }
  return fwd(w);
}
// an object's key (a value + KBIAS): a heap string's (its address) moves with it
function fwdkey(k) { if (__kind(k - __STRTAG__, __K_HEAP__)) { return fwd(k - __STRTAG__) + __STRTAG__; } return k; }
function fwdobj(w, b) {
  var n = 0;
  if (peek(b) == 0 - 1) { return peek(b + 1) - __OBJTAG__; }
  if (peek(b) < 0) { return w; }
  n = peek(__G_FREE__); poke(__G_FREE__, n + 8);
  __mcpy(n, b, 8); mark(n);
  poke(b, 0 - 1); poke(b + 1, n);
  return n - __OBJTAG__;
}
// a string (kind 0, the value 2 words in) or an array (kind 1, 3 words in) at block b. An array is copied with its
// elements inline whether or not they were (its data block, if any, is garbage now)
function fwdblk(w, b, kind) {
  var h = peek(b); var x = 0 - 2 - h; var n = 0; var cap = 0; var len = 0; var nw = x;
  if (h == 0 - 1) { return peek(b + 1) + w - b; }
  if (h > 0 - 10) { return w; }
  if (x % 8 != kind) { return w; }
  n = peek(__G_FREE__);
  if (kind == 0) { __mcpy(n, b, peek(b + 1) + 3); }
  else {
    cap = peek(b + 1); len = peek(b + 2); nw = rnd8(cap + 4);
    poke(n, 0 - 3 - nw); poke(n + 1, cap); poke(n + 2, len); poke(n + 3, n + 4);
    __mcpy(n + 4, peek(b + 3), len);
  }
  mark(n); poke(__G_FREE__, n + nw); poke(b, 0 - 1); poke(b + 1, n);
  return n + w - b;
}

// ---------------- strings
// a new string of n bytes (its length and NUL written), the bytes uninitialised -> its value
function newstr(n) { return __alloc(n, __A_STR__); }
// v as a string: a string is itself; a boolean (b: its static type is boolean) true / false; an array its elements
// joined by commas; an object [object Object]; a number its decimal form
function tostr(v, b) {
  var r = 0;
  if (__kind(v, __K_STR__)) { return v; }
  if (__kind(v, __K_ARR__)) { return join(v, 0); }
  if (__kind(v, __K_OBJ__)) {
    r = newstr(15);
    poke(r, 91); poke(r + 1, 111); poke(r + 2, 98); poke(r + 3, 106); poke(r + 4, 101); poke(r + 5, 99); poke(r + 6, 116);
    poke(r + 7, 32); poke(r + 8, 79); poke(r + 9, 98); poke(r + 10, 106); poke(r + 11, 101); poke(r + 12, 99); poke(r + 13, 116); poke(r + 14, 93);
    return r;
  }
  if (b) {                                      // (the string area's first strings, cc_ref SEED)
    if (v == 1) { return __TRUEV__; }
    if (v == 0) { return __FALSEV__; }
  }
  r = newstr(__kind(v, __K_NLEN__)); __nput(r, v);
  return r;
}
// a + b with an array or object on either side (DADD traps here; the cat class joins strings, numbers and booleans): fl 1 a's
// static type is boolean, 2 b's
function cat(a, b, fl) {
  if (__kind(a, __K_AO__) + fl % 2) { a = tostr(a, fl % 2); }
  if (__kind(b, __K_AO__) + fl / 2) { b = tostr(b, fl / 2); }
  return __dadd(a, b);
}
// two strings: -1, 0, 1 (by character codes, as JavaScript compares them)
function scmp(a, b) {
  var la = peek(a - 1); var lb = peek(b - 1); var m = la; var i = 0; var c = 0; var d = 0;
  if (a == b) { return 0; }
  if (lb < m) { m = lb; }
  i = __mcmp(a, b, m);
  if (i < m) { c = peek(a + i); d = peek(b + i); return (c > d) - (c < d); }
  return (la > lb) - (la < lb);
}
// the dynamic operators' slow paths (DADD ... DNE trap here: an array or object on either side for +; a string, array or
// object for the others; for DEQ / DNE two strings). DADDL / DADDR: the left / right operand's static type is boolean (true /
// false when joined to a string). Comparisons: arrays and objects as their strings; two strings by their characters, a
// string and a number as numbers (parseInt: 0 where JavaScript has NaN)
function dadd(a, b) { return cat(a, b, 0); }
function daddl(a, b) { if (__kind(a, __K_REF__) + __kind(b, __K_REF__)) { return cat(a, b, 1); } return a + b; }
function daddr(a, b) { if (__kind(a, __K_REF__) + __kind(b, __K_REF__)) { return cat(a, b, 2); } return a + b; }
function dcmp(a, b) {
  if (__kind(a, __K_AO__)) { a = tostr(a, 0); }
  if (__kind(b, __K_AO__)) { b = tostr(b, 0); }
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) { return scmp(a, b); }
  if (__kind(a, __K_STR__)) { a = parseint(0, a); }
  if (__kind(b, __K_STR__)) { b = parseint(0, b); }
  return (a > b) - (a < b);
}
function dlt(a, b) { return dcmp(a, b) < 0; }
function dgt(a, b) { return dcmp(a, b) > 0; }
function dle(a, b) { return dcmp(a, b) <= 0; }
function dge(a, b) { return dcmp(a, b) >= 0; }
function deq(a, b) {
  var n = 0;
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) {
    if (a == b) { return 1; }
    n = peek(a - 1);
    if (peek(b - 1) != n) { return 0; }
    return __mcmp(a, b, n) == n;
  }
  return a == b;
}
function dne(a, b) { return deq(a, b) == 0; }
// s[k]: a one-character string, or 0 past the end (JavaScript: undefined)
function charat(s, k) {
  var r = 0;
  if (k < 0) { return 0; }
  if (k >= peek(s - 1)) { return 0; }
  r = newstr(1); poke(r, peek(s + k));
  return r;
}

// ---------------- arrays
// a new array of capacity cap and length len (its elements uninitialised: the caller fills them before allocating again)
function newarr(cap, len) {
  var r = 0;
  if (cap < 4) { cap = 4; }
  r = __alloc(cap, __A_ARR__);
  if (len) { poke(r - 1, len); }
  return r;
}
// room for need elements: a raw block of twice the capacity (or need), the elements copied
function grow(x, need) {
  var cap = peek(x - 2) * 2; var d = 0;
  if (cap < need) { cap = need; }
  if (cap < 4) { cap = 4; }
  d = __alloc(cap, __A_RAW__);
  __mcpy(d, peek(x), peek(x - 1));
  poke(x, d); poke(x - 2, cap);
  return 0;
}
// x[k] = v outside the length (SETX stores inside it): the array grows to k + 1, any gap filled with 0
function aset(x, k, v) {
  var n = peek(x - 1); var p = 0;
  if (k < 0) { return 0; }
  if (k < n) { p = peek(x); p[k] = v; return 0; }
  if (k >= peek(x - 2)) { grow(x, k + 1); }
  p = peek(x);
  __mfill(p + n, 0, k - n);
  p[k] = v; poke(x - 1, k + 1);
  return 0;
}
// x.push(v): APUSH pushes onto an array with room and returns; pushs is the rest (no array, or a full one)
function push(x, v) { __apush(x, v); return pushs(x, v); }
function pushs(x, v) {
  var n = peek(x - 1); var p = 0;
  if (__kind(x, __K_ARR__) == 0) { return 0; }
  if (n >= peek(x - 2)) { grow(x, n + 1); }
  p = peek(x); p[n] = v; poke(x - 1, n + 1);
  return n + 1;
}
function pop(x) {
  var n = peek(x - 1);
  if (__kind(x, __K_ARR__) == 0) { return 0; }
  if (n == 0) { return 0; }
  poke(x - 1, n - 1);
  return peek(peek(x) + n - 1);
}
// v's characters (a string's, or a number's digits) at p -> how many
function pput(p, v) {
  var n = 0;
  if (__kind(v, __K_STR__)) { n = peek(v - 1); __mcpy(p, v, n); return n; }
  __nput(p, v);
  return __kind(v, __K_NLEN__);
}
// the elements as strings joined by sep (0: a comma): their lengths, then one string. An array or object element is made a
// string first, in a copy of the elements (t); a number's digits are written in place
function join(x, sep) {
  var n = peek(x - 1); var i = 0; var r = 0; var e = 0; var t = x; var tot = 0; var p = 0; var ls = 1;
  if (__kind(sep, __K_AO__)) { sep = tostr(sep, 0); }
  if (sep != 0) { ls = clen(sep); }
  while (i < n) {
    e = peek(peek(t) + i);
    if (__kind(e, __K_AO__)) {
      if (t == x) { t = newarr(n, n); __mcpy(peek(t), peek(x), n); }
      e = tostr(e, 0); poke(peek(t) + i, e);
    }
    tot = tot + clen(e); i++;
  }
  if (n) { tot = tot + ls * (n - 1); }
  r = newstr(tot); p = r; i = 0;
  while (i < n) {
    if (i) { if (sep != 0) { p = p + pput(p, sep); } else { poke(p, 44); p++; } }
    p = p + pput(p, peek(peek(t) + i)); i++;
  }
  return r;
}

// ---------------- dynamic x[k] (GETX / SETX trap here for anything but an array inside its length, or an object with a
// number or the program's own string as the key, which the machine probes) and properties
// a key: a value + KBIAS (a string key becomes its address); a string built at run time (or SEED's) is first replaced by
// one of the object's keys with those characters, or (stored) by the program's string with them (okey)
function getx(x, k) {
  if (__kind(x, __K_STR__)) { return charat(x, k); }
  if (__kind(x, __K_OBJ__)) { return pget(x, okey(x, k, 0) + __STRTAG__); }
  return 0;
}
function setx(x, k, v) {
  if (__kind(x, __K_ARR__)) { aset(x, k, v); return 0; }
  if (__kind(x, __K_OBJ__)) { pset(x, okey(x, k, 1) + __STRTAG__, v); }
  return 0;
}
// o's value for key (0 if it has none)
function pget(o, key) {
  var c = o + __OBJTAG__; var k = 0;
  while (1) {
    k = peek(c);
    if (k == key) { return peek(c + 1); }
    if (k == 0) { return 0; }
    if (k < 0) { c = k + __OBJTAG__; } else { c = c + 2; }
  }
  return 0;
}
// o.key = v: the key's pair, else the first free pair (the keys end after it), else a new chunk linked from the last
function pset(o, key, v) {
  var c = o + __OBJTAG__; var k = 0; var n = 0;
  while (1) {
    k = peek(c);
    if (k == key) { poke(c + 1, v); return 0; }
    if (k < 0) { c = k + __OBJTAG__; }
    else if (k == 0) {
      if ((c - __HEAP0__) % 8 < 6) { poke(c, key); poke(c + 1, v); poke(c + 2, 0); return 0; }     // (the third pair: L := 0)
      n = __alloc(8, __A_CHUNK__); c = o + __OBJTAG__;
      poke(n, key); poke(n + 1, v); poke(n + 2, 0);
      while (peek(c + 6) < 0) { c = peek(c + 6) + __OBJTAG__; }
      poke(c + 6, n - __OBJTAG__);
      return 0;
    }
    else { c = c + 2; }
  }
  return 0;
}
// SETP / SETX found its chunk full (the key isn't there): a new chunk
function setp(o, key, v) { pset(o, key, v); return 0; }
// array literals: [e1 .. en] (n <= 8): the elements (this frame's arguments) copied in
function mkarr0() { return __alloc(4, __A_ARR__); }
function mkarr1(a) { var r = __alloc(4, __A_ARR__); poke(r - 1, 1); poke(r + 1, a); return r; }
function mkarr2(a, b) { var r = __alloc(4, __A_ARR__); poke(r - 1, 2); __mcpy(r + 1, __fp() + 1, 2); return r; }
function mkarr3(a, b, c) { var r = __alloc(4, __A_ARR__); poke(r - 1, 3); __mcpy(r + 1, __fp() + 1, 3); return r; }
function mkarr4(a, b, c, d) { var r = __alloc(4, __A_ARR__); poke(r - 1, 4); __mcpy(r + 1, __fp() + 1, 4); return r; }
function mkarr5(a, b, c, d, e) { var r = __alloc(5, __A_ARR__); poke(r - 1, 5); __mcpy(r + 1, __fp() + 1, 5); return r; }
function mkarr6(a, b, c, d, e, f) { var r = __alloc(6, __A_ARR__); poke(r - 1, 6); __mcpy(r + 1, __fp() + 1, 6); return r; }
function mkarr7(a, b, c, d, e, f, g) { var r = __alloc(7, __A_ARR__); poke(r - 1, 7); __mcpy(r + 1, __fp() + 1, 7); return r; }
function mkarr8(a, b, c, d, e, f, g, h) { var r = __alloc(8, __A_ARR__); poke(r - 1, 8); __mcpy(r + 1, __fp() + 1, 8); return r; }
// a long array literal past its eighth element: x.push(e) that leaves x
function apush(x, v) { push(x, v); return x; }

// ---------------- methods: (receiver, arguments) -> the result. A string's and an array's length both sit in the word
// before the value's address: peek(x - 1)
function eqv(a, b) {                       // a === b (strings by their characters)
  if (a == b) { return 1; }
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) { return deq(a, b); }
  return 0;
}
// the first index i >= from (step 1) or <= from (step -1) where t occurs in s (a string) or equals an element; -1. Forwards,
// MFEQ finds the next element equal to t (not a string) or the next place t's first character occurs, a line per execution
function find(x, t, from, step) {
  var n = peek(x - 1); var m = 0; var p = 0;
  if (__kind(x, __K_ARR__)) {
    p = peek(x);
    if (__kind(t, __K_STR__) == 0) {
      if (step > 0) {
        if (from >= 0) { if (from < n) { from = from + __mfeq(p + from, t, n - from); } if (from < n) { return from; } }
        return 0 - 1;
      }
    }
    while (from >= 0) { if (from >= n) { return 0 - 1; } if (eqv(peek(p + from), t)) { return from; } from = from + step; }
    return 0 - 1;
  }
  if (__kind(x, __K_STR__) * __kind(t, __K_STR__) == 0) { return 0 - 1; }
  m = peek(t - 1);
  if (step < 0) { if (from > n - m) { from = n - m; } }
  while (from >= 0) {
    if (from > n - m) { return 0 - 1; }
    if (step > 0) { if (m) { from = from + __mfeq(x + from, peek(t), n - m + 1 - from); if (from > n - m) { return 0 - 1; } } }
    if (__mcmp(x + from, t, m) == m) { return from; }
    from = from + step;
  }
  return 0 - 1;
}
function indexof(x, t) { return find(x, t, 0, 1); }
function lastindexof(x, t) { return find(x, t, peek(x - 1) - 1, 0 - 1); }
function includes(x, t) { return find(x, t, 0, 1) >= 0; }
function join0(x) { return join(x, 0); }
// a JavaScript index argument: negative counts from the end; clamped to [0, n]
function cidx(i, n) { if (i < 0) { i = i + n; } if (i < 0) { i = 0; } if (i > n) { i = n; } return i; }
// x.slice(a, b): a new string or array of x's [a, b)
function slice(x, a, b) {
  var n = peek(x - 1); var r = 0;
  a = cidx(a, n); b = cidx(b, n);
  if (b < a) { b = a; }
  if (__kind(x, __K_STR__)) { r = newstr(b - a); __mcpy(r, x + a, b - a); return r; }
  if (__kind(x, __K_ARR__) == 0) { return 0; }
  r = newarr(b - a, b - a); __mcpy(peek(r), peek(x) + a, b - a);
  return r;
}
function slice0(x) { return slice(x, 0, peek(x - 1)); }
function slice1(x, a) { return slice(x, a, peek(x - 1)); }
function substring(x, a, b) {
  var n = peek(x - 1); var t = 0;
  if (a < 0) { a = 0; } if (b < 0) { b = 0; } if (a > n) { a = n; } if (b > n) { b = n; }
  if (a > b) { t = a; a = b; b = t; }
  return slice(x, a, b);
}
function substr1(x, a) { return substring(x, a, peek(x - 1)); }
// a.concat(b): an array of a's elements then b's (or b itself), or the strings joined
function concat(x, y) {
  var n = 0; var m = 1; var r = 0;
  if (__kind(x, __K_ARR__) == 0) { return __dadd(x, y); }
  n = peek(x - 1);
  if (__kind(y, __K_ARR__)) { m = peek(y - 1); }
  r = newarr(n + m, n + m);
  __mcpy(peek(r), peek(x), n);
  if (__kind(y, __K_ARR__)) { __mcpy(peek(r) + n, peek(y), m); } else { poke(peek(r) + n, y); }
  return r;
}
function reverse(x) {
  var n = peek(x - 1); var p = peek(x); var i = 0; var t = 0;
  if (__kind(x, __K_ARR__) == 0) { return x; }
  while (i < n / 2) { t = p[i]; p[i] = p[n - 1 - i]; p[n - 1 - i] = t; i++; }
  return x;
}
function fill(x, v) {
  if (__kind(x, __K_ARR__) == 0) { return x; }
  __mfill(peek(x), v, peek(x - 1));
  return x;
}
function shift(x) {
  var n = peek(x - 1); var p = peek(x); var v = 0;
  if (__kind(x, __K_ARR__) == 0) { return 0; }
  if (n == 0) { return 0; }
  v = p[0];
  __mcpy(p, p + 1, n - 1);
  poke(x - 1, n - 1);
  return v;
}
function unshift(x, v) {
  var n = push(x, 0); var p = peek(x); var i = n - 1;
  while (i > 0) { p[i] = p[i - 1]; i = i - 1; }
  p[0] = v;
  return n;
}
function charat1(s, k) { var r = charat(s, k); if (r == 0) { r = newstr(0); } return r; }
function charcode(s, k) {
  if (__kind(s, __K_STR__) == 0) { return 0; } if (k < 0) { return 0; } if (k >= peek(s - 1)) { return 0; }
  return peek(s + k);
}
function fromcc(d, c) { var r = newstr(1); poke(r, c); return r; }
function upper(s) { var r = 0; if (__kind(s, __K_STR__) == 0) { return s; } r = newstr(peek(s - 1)); __mupper(r, s, peek(s - 1)); return r; }
function lower(s) { var r = 0; if (__kind(s, __K_STR__) == 0) { return s; } r = newstr(peek(s - 1)); __mlower(r, s, peek(s - 1)); return r; }
function isblank(c) { return (c == 32) + (c == 9) + (c == 10) + (c == 13); }
function trim(s) {
  var a = 0; var b = peek(s - 1); var go = 1;
  if (__kind(s, __K_STR__) == 0) { return s; }
  while (go) { go = 0; if (a < b) { if (isblank(peek(s + a))) { a++; go = 1; } } }
  go = 1;
  while (go) { go = 0; if (b > a) { if (isblank(peek(s + b - 1))) { b = b - 1; go = 1; } } }
  return slice(s, a, b);
}
function startswith(s, t) {
  if (__kind(s, __K_STR__) * __kind(t, __K_STR__) == 0) { return 0; } if (peek(t - 1) > peek(s - 1)) { return 0; }
  return __mcmp(s, t, peek(t - 1)) == peek(t - 1);
}
function endswith(s, t) {
  var k = peek(s - 1) - peek(t - 1);
  if (__kind(s, __K_STR__) * __kind(t, __K_STR__) == 0) { return 0; } if (k < 0) { return 0; }
  return __mcmp(s + k, t, peek(t - 1)) == peek(t - 1);
}
// s.repeat(n): one string of the copies, each doubling the copied part
function repeat(s, n) {
  var m = 0; var r = 0; var k = 0; var tot = 0;
  if (__kind(s, __K_STR__) == 0) { return newstr(0); }
  if (n < 0) { n = 0; }
  m = peek(s - 1); tot = m * n;
  r = newstr(tot);
  if (tot) { __mcpy(r, s, m); k = m; }
  while (k < tot) { if (k > tot - k) { __mcpy(r + k, r, tot - k); k = tot; } else { __mcpy(r + k, r, k); k = k + k; } }
  return r;
}
// s.split(sep): the pieces between the occurrences of sep (sep "": the characters) as an array
function split(s, sep) {
  var r = newarr(0, 0); var i = 0; var j = 0; var m = 0;
  if (__kind(s, __K_STR__) * __kind(sep, __K_STR__) == 0) { push(r, s); return r; }
  m = peek(sep - 1);
  if (m == 0) { while (i < peek(s - 1)) { push(r, slice(s, i, i + 1)); i++; } return r; }
  j = find(s, sep, 0, 1);
  while (j >= 0) { push(r, slice(s, i, j)); i = j + m; j = find(s, sep, i, 1); }
  push(r, slice(s, i, peek(s - 1)));
  return r;
}
function tostring(d, v) { return tostr(v, 0); }
function tostring0(v) { return tostr(v, 0); }
// parseInt(s) / Number(s): the decimal integer s starts with (after blanks, a sign); 0 if none (JavaScript: NaN)
function parseint(d, s) {
  var n = 0; var m = 0; var i = 0; var g = 1; var neg = 0; var c = 0;
  if (__kind(s, __K_STR__) == 0) { return s; }
  m = peek(s - 1);
  while (i < m) { if (isblank(peek(s + i))) { i++; } else { m = 0 - m; } }
  if (m < 0) { m = 0 - m; }
  if (i < m) { c = peek(s + i); if (c == 45) { neg = 1; i++; } else if (c == 43) { i++; } }
  while (g) { g = 0; if (i < m) { c = peek(s + i); if (c >= 48) { if (c <= 57) { n = n * 10 + c - 48; i++; g = 1; } } } }
  if (neg) { return 0 - n; }
  return n;
}
function tostringb(d, v) { return tostr(v, 1); }

// ---------------- console.log of an array or object (PRINT traps into pval): Node's one-line form [ 1, 'a', [ 2 ] ],
// { k: 1, 'a b': [] }; below depth 2 [Array] / [Object]. fl: PRINT's flags, its separator * 2 + boolean; no separator: a
// piece of a + chain, printed as its string
// PRINT of an array or an object (cc_ref.TRAPS): pstub's TENTER made this frame at the PRINT's fp + TRAPOFF; its flags (A) and
// value (operand B) are decoded from the PRINT instruction, at the return address - 2
function ptrap() {
  var f = __fp(); var r = peek(f) % 8192; var cf = f - __TRAPOFF__; var w1 = peek(r - 1); var c = (w1 % 1024 + 1024) % 1024;
  var b = (w1 - c) / 1024 + 512; var v = b - 896;
  if (b < 256) { v = peek(__DB__ + b); }
  else if (b < 768) { v = peek(cf + b - 256); }
  pval(v, peek(r - 2) % 8192);
  return 0;
}
// PRINT's trap for an array or an object (fl: 2 * the separator + 8 if it is a piece of a + chain, which prints as a string)
function pval(v, fl) {
  var sp = (fl / 2) % 4;
  if (fl / 8 + (sp == 0)) { prn(tostr(v, 0)); } else { ins(v, 0); }
  if (sp == 1) { putc(32); }
  if (sp == 2) { putc(10); }
  return 0;
}
// a string as Node quotes it: 'x', or "x" if it holds a ' and no ", with \\ \n \t and the quote escaped
function qstr(s) {
  var n = peek(s - 1); var i = 0; var q = 39; var c = 0;
  if (__mfeq(s, 39, n) < n) { q = 34; }
  if (__mfeq(s, 34, n) < n) { q = 39; }
  putc(q);
  while (i < n) {
    c = peek(s + i);
    if (c == 10) { putc(92); putc(110); }
    else if (c == 9) { putc(92); putc(116); }
    else if ((c == 92) + (c == q)) { putc(92); putc(c); }
    else { putc(c); }
    i++;
  }
  putc(q);
  return 0;
}
// an element at depth d: strings quoted, arrays and objects nested
function insel(v, d) { if (__kind(v, __K_STR__)) { return qstr(v); } return ins(v, d); }
function ins(v, d) {
  var n = 0; var i = 0;
  if (__kind(v, __K_ARR__)) {
    n = peek(v - 1);
    if (n == 0) { putc(91); putc(93); return 0; }
    if (d > 2) { putc(91); putc(65); putc(114); putc(114); putc(97); putc(121); putc(93); return 0; }
    putc(91); putc(32);
    while (i < n) { if (i) { putc(44); putc(32); } insel(peek(peek(v) + i), d + 1); i++; }
    putc(32); putc(93); return 0;
  }
  if (__kind(v, __K_OBJ__)) { return insobj(v, d); }
  prn(v);
  return 0;
}
// an object's keys: number keys first, then the names (bare if they are identifiers, else quoted), in insertion order
function insobj(v, d) {
  var c = v + __OBJTAG__; var k = 0; var pass = 0; var first = 1; var go = 1;
  if (peek(c) == 0) { putc(123); putc(125); return 0; }
  if (d > 2) { putc(91); putc(79); putc(98); putc(106); putc(101); putc(99); putc(116); putc(93); return 0; }
  putc(123); putc(32);
  while (pass < 2) {
    c = v + __OBJTAG__; go = 1;
    while (go) {
      k = peek(c);
      if (k == 0) { go = 0; }
      else if (k < 0) { c = k + __OBJTAG__; }
      else {
        if (__kind(k - __STRTAG__, __K_STR__) == pass) {
          if (first == 0) { putc(44); putc(32); }
          first = 0;
          if (pass) { inskey(k - __STRTAG__); } else { putc(39); prn(k - __STRTAG__); putc(39); }
          putc(58); putc(32); insel(peek(c + 1), d + 1);
        }
        c = c + 2;
      }
    }
    pass++;
  }
  putc(32); putc(125);
  return 0;
}
function isid(c, first) {
  if ((c >= 97) * (c <= 122) + (c >= 65) * (c <= 90) + (c == 95) + (c == 36)) { return 1; }
  if (first) { return 0; }
  return (c >= 48) * (c <= 57);
}
function inskey(s) {
  var n = peek(s - 1); var i = 0; var ok = n > 0;
  while (i < n) { if (isid(peek(s + i), i == 0) == 0) { ok = 0; } i++; }
  if (ok) { prn(s); return 0; }
  return qstr(s);
}

// ---------------- string keys built at run time: o[k] for a string k that isn't the program's own (a heap string, or one of
// the string area's first ones, SEED) uses one of the object's keys with those characters if it has one; else, for a key
// being stored (add), the program's literal or name with them if there is one (from STRP0 the string area holds
// [len][bytes][0] each, up to the end the compiler left at STREND: MWALK finds the next of k's length, MCMP compares it);
// else k itself (GETX / SETX call this before they look the key up)
function keyeq(s, k, n) {
  if (__kind(s, __K_STR__)) { if (peek(s - 1) == n) { return __mcmp(s, k, n) == n; } }
  return 0;
}
function okey(o, k, add) {
  var c = o + __OBJTAG__; var key = 0; var n = peek(k - 1); var p = __STRP0__; var e = peek(__STREND__); var go = 1;
  if (__kind(k, __K_NOTOWN__) == 0) { return k; }
  while (go) {
    key = peek(c);
    if (key == 0) { go = 0; }
    else if (key < 0) { c = key + __OBJTAG__; }
    else { if (keyeq(key - __STRTAG__, k, n)) { return key - __STRTAG__; } c = c + 2; }
  }
  if (add) {
    while (p < e) {
      p = p + __mwalk(p, e, n);
      if (p < e) { if (__mcmp(p + 1, k, n) == n) { return p + 1 - __STRTAG__; } p = p + n + 2; }
    }
  }
  return k;
}
