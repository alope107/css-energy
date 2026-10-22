// runtime library (jsc dialect: jsc.js; libbuild.js fills in the upper-case constants between double underscores (compiler/rtlib.py consts)).
// No globals and no string literals here: jsc would put them in the data area, which is the program's. Locals live in
// stack frames, which the collector scans (a frame's tagged values are roots and are updated when their block moves);
// a raw address must not be held across anything that allocates.
//
// Values: numbers; a string is its first byte's address - STRTAG, a literal in the string area or a heap string; an
// array its ptr word's address + ARRTAG; an object its chunk's address - OBJTAG; booleans 0 / 1.
// Heap blocks are 8-aligned, a multiple of 8 words: object chunks [k0 v0 k1 v1 k2 v2 L pad] (k0 >= 0), strings
// [hdr len bytes... 0], arrays [hdr cap len ptr elements...] (ptr: the elements, inline until the array grows past cap,
// then a data block of its own); hdr = -2 - words - kind (kind 0 string, 1 array); a block the collector moved has -1 and
// its copy's address in its first two words.

// Work on memory is the machine's primitives (machine/uarch.py RTOPS, docs/ARCHITECTURE.md §3.5), a cache line per execution
// where a loop here takes a chain level per instruction: __op(__KSTR__, v) etc. test a kind (KIND), __op(__ASTR__, n)
// allocates (ALLOC, which collects when the heap is full), __op(__MCOPY__, d, s, n) copies (MCPY; __NPUT__ writes a number's
// digits), __op(__MCMP__, p, q, n) compares (MCMP; __MFREF__, __MFEQ__ and __MWALK__ search), __op(__W_CAT__, a, b)
// concatenates (CAT). Addresses are masked to 15 bits and the tags are multiples of 32768, so a string's or an array's value
// is its address as far as peek, poke and the primitives go (peek(x - 1): its length).

// a + chain inside console.log keeps its pieces on the stack: the ROM's pnK prints them (PRINT without a separator: an array
// or object as its string, pval); catnK joins them when an operator other than + follows. b2s: a boolean piece

function catn2(a, b) { return cat(a, b, 0); }
function catn3(a, b, c) { return cat(cat(a, b, 0), c, 0); }
function catn4(a, b, c, d) { return cat(catn3(a, b, c), d, 0); }
function catn5(a, b, c, d, e) { return cat(catn4(a, b, c, d), e, 0); }
function catn6(a, b, c, d, e, f) { return cat(catn5(a, b, c, d, e), f, 0); }
function catn7(a, b, c, d, e, f, g) { return cat(catn6(a, b, c, d, e, f), g, 0); }
function catn8(a, b, c, d, e, f, g, h) { return cat(catn7(a, b, c, d, e, f, g), h, 0); }

function rnd8(n) { return n + (8 - n % 8) % 8; }

// ---------------- allocation and the collector
// ALLOC found the heap full (the ROM's galloc): collect with the stack below gcsp as roots; ALLOC's n is its top word
function gca(gcsp) { gc(gcsp, rnd8(peek(gcsp - 1))); return 0; }
// the same for CAT: its operands' characters, the length word and the NUL
function clen(x) { if (__op(__KSTR__, x)) { return peek(x - 1); } return __op(__KNLEN__, x); }
function gcat(gcsp) { gc(gcsp, rnd8(clen(peek(gcsp - 2)) + clen(peek(gcsp - 1)) + 3)); return 0; }
// Cheney's copying collector between the two semi-spaces. HP / GCLIM are offsets from HEAP0: the next free word and the
// current space's start (0: space A, as RAM starts). The roots: the globals, the routines' value cells, the stack from SP0
// to gcsp. Then need more words must fit, or the program stops (out of memory).
function gc(gcsp, need) {
  var from = __HEAP0__; var to = __HEAP0__ + __H__; var p = 0; var e = 0;
  if (1) {
    if (peek(__GCLIM__)) { from = __HEAP0__ + __H__; to = __HEAP0__; }
    poke(__G_FLO__, from); poke(__G_FREE__, to);
    fwdrange(__DB__ + 1, __DB__ + peek(__INIT__ - 1));
    poke(__S_V__, fwd(peek(__S_V__))); poke(__S_K__, fwdkey(peek(__S_K__)));
    fwdrange(__SP0__, gcsp);
    p = to;
    while (p < peek(__G_FREE__)) { p = p + scan(p); }
    poke(__HP__, peek(__G_FREE__) - __HEAP0__); poke(__GCLIM__, to - __HEAP0__);
  }
  if (peek(__HP__) + need - 8 >= peek(__GCLIM__) + __H__ - 7) { oom(); }
  return 0;
}
// forward the references in [p, e): MCMP 1 finds the next word that refers into from-space, a line per execution
function fwdrange(p, e) {
  var flo = peek(__G_FLO__);
  while (p < e) {
    p = p + __op(__MFREF__, p, flo, e - p);
    if (p < e) { poke(p, fwd(peek(p))); p++; }
  }
  return 0;
}
function oom() {
  putc(10); putc(111); putc(117); putc(116); putc(32); putc(111); putc(102); putc(32);
  putc(109); putc(101); putc(109); putc(111); putc(114); putc(121); putc(10); halt();
  return 0;
}
// a copied block's references: an object's values up to its first free pair (and its link if all three are used), an
// array's elements up to its length. -> the block's size
function scan(s) {
  var h = peek(s); var i = 0; var go = 1; var x = 0; var n = 0;
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
  if (x % 8 == 1) { fwdrange(s + 4, s + 4 + peek(s + 2)); }
  return x - x % 8;
}
// a value -> the same value after the collection: a from-space object, string or array is copied (once). A root may point
// into an object's chunk (a SCANI cursor); anything else that only looks like a pointer (a number in a tag range, a stale
// word in a frame) is left as it is
function fwd(w) {
  var flo = peek(__G_FLO__); var a = w + __OBJTAG__;
  if (a >= flo) { if (a < flo + __H__) { return fwdobj(w, a, a - (a - flo) % 8); } }
  a = w + __STRTAG__;
  if (a >= flo + 2) { if (a < flo + __H__) { return fwdblk(w, a - 2, 0, flo); } }
  a = w - __ARRTAG__;
  if (a >= flo + 3) { if (a < flo + __H__) { return fwdblk(w, a - 3, 1, flo); } }
  return w;
}
// an object's key (a value + KBIAS): a heap string's (its address) moves with it
function fwdkey(k) { if (__op(__KHEAP__, k - __STRTAG__)) { return fwd(k - __STRTAG__) + __STRTAG__; } return k; }
function fwdobj(w, a, b) {
  var k = peek(b); var n = 0; var i = 0;
  if (k == 0 - 1) { return peek(b + 1) + a - b - __OBJTAG__; }
  if (k < 0) { return w; }
  n = peek(__G_FREE__); poke(__G_FREE__, n + 8);
  __op(__MCOPY__, n, b, 8);
  poke(b, 0 - 1); poke(b + 1, n);
  return n + a - b - __OBJTAG__;
}
// a string (kind 0, the value 2 words in) or an array (kind 1, 3 words in) at block b. An array is copied with its
// elements inline whether or not they were (its data block, if any, is garbage now)
function fwdblk(w, b, kind, flo) {
  var h = peek(b); var x = 0 - 2 - h; var n = 0; var i = 0; var cap = 0; var len = 0; var p = 0; var nw = 0;
  if ((b - flo) % 8) { return w; }
  if (h == 0 - 1) { return peek(b + 1) + w - b; }
  if (h > 0 - 10) { return w; }
  if (x % 8 != kind) { return w; }
  n = peek(__G_FREE__);
  if (kind == 0) { nw = x - kind; __op(__MCOPY__, n, b, nw); }
  else {
    cap = peek(b + 1); len = peek(b + 2); p = peek(b + 3); nw = rnd8(cap + 4);
    poke(n, 0 - 3 - nw); poke(n + 1, cap); poke(n + 2, len); poke(n + 3, n + 4);
    __op(__MCOPY__, n + 4, p, len);
  }
  poke(__G_FREE__, n + nw); poke(b, 0 - 1); poke(b + 1, n);
  return n + w - b;
}

// ---------------- strings
// a new string of n bytes (its NUL written), uninitialised bytes -> its value
function newstr(n) {
  var b = __op(__ASTR__, n + 3);
  poke(b + 1, n); poke(b + 2 + n, 0);
  return b + 2 - __STRTAG__;
}
// v as a string: a string is itself; a boolean (b: its static type is boolean) true / false; an array its elements
// joined by commas; an object [object Object]; a number its decimal form
function tostr(v, b) {
  var r = 0; var p = 0;
  if (__op(__KSTR__, v)) { return v; }
  if (__op(__KARR__, v)) { return join(v, 0); }
  if (__op(__KOBJ__, v)) {
    r = newstr(15); p = r;
    poke(p, 91); poke(p + 1, 111); poke(p + 2, 98); poke(p + 3, 106); poke(p + 4, 101); poke(p + 5, 99); poke(p + 6, 116);
    poke(p + 7, 32); poke(p + 8, 79); poke(p + 9, 98); poke(p + 10, 106); poke(p + 11, 101); poke(p + 12, 99); poke(p + 13, 116); poke(p + 14, 93);
    return r;
  }
  if (b) {                                      // (the string area's first strings, cc_ref SEED)
    if (v == 1) { return __TRUEV__; }
    if (v == 0) { return __FALSEV__; }
  }
  r = newstr(__op(__KNLEN__, v)); __op(__NPUT__, r, v);
  return r;
}
// a + b with a string on either side; fl: 1 a's static type is boolean, 2 b's
// (CAT takes strings and numbers: a boolean, an array or an object is made a string first)
function cat(a, b, fl) {
  if (__op(__KAO__, a) + fl % 2) { a = tostr(a, fl % 2); }
  if (__op(__KAO__, b) + fl / 2) { b = tostr(b, fl / 2); }
  return __op(__W_CAT__, a, b);
}
// two strings: -1, 0, 1 (by character codes, as JavaScript compares them)
function scmp(a, b) {
  var la = peek(a - 1); var lb = peek(b - 1); var m = la; var i = 0; var c = 0; var d = 0;
  if (a == b) { return 0; }
  if (lb < m) { m = lb; }
  i = __op(__MCMP__, a, b, m);
  if (i < m) { c = peek(a + i); d = peek(b + i); return (c > d) - (c < d); }
  return (la > lb) - (la < lb);
}
// DYN's slow path (== / != on two strings; the others with a string, array or object operand): op = the binary opcode
// + 64 * (a boolean on the left) + 128 * (on the right). Comparisons: arrays and objects as their strings; two strings by
// their characters, a string and a number as numbers (parseInt: 0 where JavaScript has NaN)
function dynop(a, b, op) {
  var f = op % 64; var c = 0;
  if (f == __OP_ADD__) { return cat(a, b, op / 64); }
  if (__op(__KAO__, a)) { a = tostr(a, 0); }
  if (__op(__KAO__, b)) { b = tostr(b, 0); }
  if (__op(__KSTR__, a) * __op(__KSTR__, b)) { c = scmp(a, b); }
  else {
    if (__op(__KSTR__, a)) { a = parseint(0, a); }
    if (__op(__KSTR__, b)) { b = parseint(0, b); }
    c = (a > b) - (a < b);
  }
  if (f == __OP_EQ__) { return c == 0; }
  if (f == __OP_NE__) { return c != 0; }
  if (f == __OP_LT__) { return c < 0; }
  if (f == __OP_GT__) { return c > 0; }
  if (f == __OP_LE__) { return c <= 0; }
  return c >= 0;
}
// s[k]: a one-character string, or 0 past the end (JavaScript: undefined)
function charat(s, k) {
  var c = 0; var r = 0;
  if (k < 0) { return 0; }
  if (k >= peek(s - 1)) { return 0; }
  c = peek(s + k); r = newstr(1); poke(r, c);
  return r;
}

// ---------------- arrays
// a new array of capacity cap and length len (its elements uninitialised: the caller fills them before allocating again)
function newarr(cap, len) {
  var nw = 0; var b = 0;
  if (cap < 4) { cap = 4; }
  b = __op(__AARR__, cap + 4);
  if (len) { poke(b + 2, len); }
  return b + 3 + __ARRTAG__;
}
// room for need elements: a data block of twice the capacity (or need), the elements copied
function grow(x, need) {
  var a = x - __ARRTAG__; var cap = peek(a - 2) * 2; var d = 0; var p = 0; var n = 0; var i = 0;
  if (cap < need) { cap = need; }
  if (cap < 4) { cap = 4; }
  d = __op(__ARAW__, cap);
  a = x - __ARRTAG__; p = peek(a); n = peek(a - 1);
  __op(__MCOPY__, d, p, n);
  poke(a, d); poke(a - 2, cap);
  return 0;
}
// x[k] = v outside the length (STOREX stores inside it): the array grows to k + 1, any gap filled with 0
function aset(x, k, v) {
  var a = x - __ARRTAG__; var n = peek(a - 1); var p = 0;
  if (k < 0) { return 0; }
  if (k < n) { p = peek(a); p[k] = v; return 0; }
  if (k >= peek(a - 2)) { grow(x, k + 1); a = x - __ARRTAG__; }
  p = peek(a);
  while (n < k) { p[n] = 0; n++; }
  p[k] = v; poke(a - 1, k + 1);
  return 0;
}
function push(x, v) {
  var a = x - __ARRTAG__; var n = peek(a - 1); var p = 0;
  if (__op(__KARR__, x) == 0) { return 0; }
  if (n >= peek(a - 2)) { grow(x, n + 1); a = x - __ARRTAG__; }
  p = peek(a); p[n] = v; poke(a - 1, n + 1);
  return n + 1;
}
function pop(x) {
  var a = x - __ARRTAG__; var n = peek(a - 1); var p = peek(a);
  if (__op(__KARR__, x) == 0) { return 0; }
  if (n == 0) { return 0; }
  poke(a - 1, n - 1);
  return p[n - 1];
}
// the elements as strings joined by sep (0: a comma): their lengths, then one string. An array or object element is made a
// string first, in a copy of the elements (t); a number's digits are written in place
function join(x, sep) {
  var n = peek(x - 1); var i = 0; var r = 0; var e = 0; var t = 0; var ls = 1; var tot = 0; var k = 0;
  if (sep != 0) { ls = peek(sep - 1); }
  while (i < n) {
    e = peek(peek(x) + i); k = __op(__KCODE__, e);
    if (k > 1) {
      if (t == 0) { t = newarr(n, n); __op(__MCOPY__, peek(t), peek(x), n); }
      e = tostr(e, 0); poke(peek(t) + i, e);
    }
    if (k) { tot = tot + peek(e - 1); } else { tot = tot + __op(__KNLEN__, e); }
    i++;
  }
  if (n) { tot = tot + ls * (n - 1); }
  if (t == 0) { t = x; }
  r = newstr(tot); k = r; i = 0;
  while (i < n) {
    if (i) { if (sep != 0) { __op(__MCOPY__, k, sep, ls); } else { poke(k, 44); } k = k + ls; }
    e = peek(peek(t) + i);
    if (__op(__KSTR__, e)) { __op(__MCOPY__, k, e, peek(e - 1)); k = k + peek(e - 1); }
    else { __op(__NPUT__, k, e); k = k + __op(__KNLEN__, e); }
    i++;
  }
  return r;
}

// ---------------- dynamic x[k] (the ROM's GETX / SETX call these for anything but an object)
function getx(x, k) {
  if (__op(__KSTR__, x)) { return charat(x, k); }
  if (__op(__KARR__, x)) { return 0; }
  return peek(x + k);
}
function setx(x, k, v) {
  if (__op(__KARR__, x)) { aset(x, k, v); return 0; }
  if (__op(__KSTR__, x) == 0) { poke(x + k, v); }
  return 0;
}

// ---------------- methods: (receiver, arguments) -> the result. A string's and an array's length both sit in the word
// before the value's address (the tags are multiples of 32768, and peek masks addresses to 15 bits): peek(x - 1)
function eqv(a, b) {                       // a === b (strings by their characters)
  if (a == b) { return 1; }
  if (__op(__KSTR__, a) * __op(__KSTR__, b)) { return scmp(a, b) == 0; }
  return 0;
}
// the first index i >= from (step 1) or <= from (step -1) where t occurs in s (a string) or equals an element; -1
function find(x, t, from, step) {
  var n = peek(x - 1); var m = 0; var p = 0;
  if (__op(__KARR__, x)) {
    p = peek(x);
    if (__op(__KSTR__, t)) {
      while (from >= 0) { if (from >= n) { return 0 - 1; } if (eqv(peek(p + from), t)) { return from; } from = from + step; }
    }
    if (step > 0) { if (from < n) { from = from + __op(__MFEQ__, p + from, t, n - from); } if (from < n) { return from; } return 0 - 1; }
    while (from >= 0) { if (from >= n) { return 0 - 1; } if (peek(p + from) == t) { return from; } from = from + step; }
    return 0 - 1;
  }
  if (__op(__KSTR__, x) * __op(__KSTR__, t) == 0) { return 0 - 1; }
  m = peek(t - 1);
  if (step < 0) { if (from > n - m) { from = n - m; } }
  while (from >= 0) {
    if (from > n - m) { return 0 - 1; }
    if (step > 0) { if (m) { from = from + __op(__MFEQ__, x + from, peek(t), n - m + 1 - from); if (from > n - m) { return 0 - 1; } } }
    if (__op(__MCMP__, x + from, t, m) == m) { return from; }
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
  if (__op(__KSTR__, x)) { r = newstr(b - a); __op(__MCOPY__, r, x + a, b - a); return r; }
  if (__op(__KARR__, x) == 0) { return 0; }
  r = newarr(b - a, b - a); __op(__MCOPY__, peek(r), peek(x) + a, b - a);
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
  var n = 0; var m = 1; var r = 0; var p = 0;
  if (__op(__KARR__, x) == 0) { return cat(x, y, 0); }
  n = peek(x - 1);
  if (__op(__KARR__, y)) { m = peek(y - 1); }
  r = newarr(n + m, n + m); p = peek(r);
  __op(__MCOPY__, p, peek(x), n);
  if (__op(__KARR__, y)) { __op(__MCOPY__, p + n, peek(y), m); }
  else { poke(p + n, y); }
  return r;
}
function reverse(x) {
  var n = peek(x - 1); var p = peek(x); var i = 0; var t = 0;
  if (__op(__KARR__, x) == 0) { return x; }
  while (i < n / 2) { t = p[i]; p[i] = p[n - 1 - i]; p[n - 1 - i] = t; i++; }
  return x;
}
function fill(x, v) {
  var n = peek(x - 1); var p = peek(x); var i = 0;
  if (__op(__KARR__, x) == 0) { return x; }
  while (i < n) { p[i] = v; i++; }
  return x;
}
function shift(x) {
  var n = peek(x - 1); var p = peek(x); var v = 0;
  if (__op(__KARR__, x) == 0) { return 0; }
  if (n == 0) { return 0; }
  v = p[0];
  __op(__MCOPY__, p, p + 1, n - 1);
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
  if (__op(__KSTR__, s) == 0) { return 0; } if (k < 0) { return 0; } if (k >= peek(s - 1)) { return 0; }
  return peek(s + k);
}
function fromcc(d, c) { var r = newstr(1); poke(r, c); return r; }
function upper(s) { var r = 0; if (__op(__KSTR__, s) == 0) { return s; } r = newstr(peek(s - 1)); __op(__MUPPER__, r, s, peek(s - 1)); return r; }
function lower(s) { var r = 0; if (__op(__KSTR__, s) == 0) { return s; } r = newstr(peek(s - 1)); __op(__MLOWER__, r, s, peek(s - 1)); return r; }
function isblank(c) { return (c == 32) + (c == 9) + (c == 10) + (c == 13); }
function trim(s) {
  var p = s + __STRTAG__; var a = 0; var b = peek(s - 1); var go = 1;
  if (__op(__KSTR__, s) == 0) { return s; }
  while (go) { go = 0; if (a < b) { if (isblank(p[a])) { a++; go = 1; } } }
  go = 1;
  while (go) { go = 0; if (b > a) { if (isblank(p[b - 1])) { b = b - 1; go = 1; } } }
  return slice(s, a, b);
}
function startswith(s, t) {
  var m = peek(t - 1);
  if (__op(__KSTR__, s) * __op(__KSTR__, t) == 0) { return 0; } if (m > peek(s - 1)) { return 0; }
  return __op(__MCMP__, s, t, m) == m;
}
function endswith(s, t) {
  var m = peek(t - 1); var k = peek(s - 1) - m;
  if (__op(__KSTR__, s) * __op(__KSTR__, t) == 0) { return 0; } if (k < 0) { return 0; }
  return __op(__MCMP__, s + k, t, m) == m;
}
function repeat(s, n) {
  var r = 0; var m = 0; var i = 0;
  if (__op(__KSTR__, s) == 0) { return newstr(0); }
  if (n < 0) { n = 0; }
  m = peek(s - 1); r = newstr(m * n);
  while (i < n) { __op(__MCOPY__, r + m * i, s, m); i++; }
  return r;
}
// s.split(sep): the pieces between the occurrences of sep (sep "": the characters) as an array
function split(s, sep) {
  var r = newarr(0, 0); var i = 0; var j = 0; var m = 0;
  if (__op(__KSTR__, s) * __op(__KSTR__, sep) == 0) { push(r, s); return r; }
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
  var n = 0; var p = s + __STRTAG__; var m = 0; var i = 0; var g = 1; var neg = 0;
  if (__op(__KSTR__, s) == 0) { return s; }
  m = peek(s - 1);
  while (i < m) { if (isblank(p[i])) { i++; } else { m = 0 - m; } }
  if (m < 0) { m = 0 - m; }
  if (i < m) { if (p[i] == 45) { neg = 1; i++; } else if (p[i] == 43) { i++; } }
  while (g) { g = 0; if (i < m) { if (p[i] >= 48) { if (p[i] <= 57) { n = n * 10 + p[i] - 48; i++; g = 1; } } } }
  if (neg) { return 0 - n; }
  return n;
}
function tostringb(d, v) { return tostr(v, 1); }

// ---------------- console.log of an array or object (PRINT traps into the ROM's pval): Node's one-line form
// [ 1, 'a', [ 2 ] ], { k: 1, 'a b': [] }; below depth 2 [Array] / [Object]. op: the PRINT instruction (its separator; none:
// a piece of a + chain, printed as its string)
function pval(v, ret, op) {
  // a piece of a + chain (op 0: the PRINT is in ROM, which reads as 0: pnK's, a piece's)
  if ((op == __OP_PRINT__) + (op == __OP_PRINTB__) + (op == 0)) { prn(tostr(v, 0)); return ret; }
  ins(v, 0);
  if ((op == __OP_PRINTSP__) + (op == __OP_PRINTBSP__)) { putc(32); }
  if ((op == __OP_PRINTLN__) + (op == __OP_PRINTBLN__)) { putc(10); }
  return ret;
}
// a string as Node quotes it: 'x', or "x" if it holds a ' and no ", with \\ \n \t and the quote escaped
function qstr(s) {
  var p = s + __STRTAG__; var n = peek(s - 1); var i = 0; var q = 39; var c = 0;
  while (i < n) { if (p[i] == 39) { q = 34; } i++; }
  i = 0; while (i < n) { if (p[i] == 34) { q = 39; } i++; }
  putc(q); i = 0;
  while (i < n) {
    c = p[i];
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
function insel(v, d) { if (__op(__KSTR__, v)) { return qstr(v); } return ins(v, d); }
function ins(v, d) {
  var n = 0; var i = 0;
  if (__op(__KARR__, v)) {
    n = peek(v - 1);
    if (n == 0) { putc(91); putc(93); return 0; }
    if (d > 2) { putc(91); putc(65); putc(114); putc(114); putc(97); putc(121); putc(93); return 0; }
    putc(91); putc(32);
    while (i < n) { if (i) { putc(44); putc(32); } insel(peek(peek(v) + i), d + 1); i++; }
    putc(32); putc(93); return 0;
  }
  if (__op(__KOBJ__, v)) { return insobj(v, d); }
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
        if (__op(__KSTR__, k - __STRTAG__) == pass) {
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
  var p = s + __STRTAG__; var n = peek(s - 1); var i = 0; var ok = n > 0;
  while (i < n) { if (isid(p[i], i == 0) == 0) { ok = 0; } i++; }
  if (ok) { prn(s); return 0; }
  return qstr(s);
}

// ---------------- string keys built at run time: o[k] for a string k that isn't the program's own (a heap string, or one of
// the string area's first ones, SEED) uses the object's key with those characters if it has one; a key it doesn't have is
// stored (add: SETX) as the program's literal or name with them if there is one (from STRP0 the string area holds
// [len][bytes][0] each, up to the end the compiler left at STREND), else as k itself. So a key is the literal whenever one
// exists, and a lookup needs only the object's keys (GETX / SETX call this before they look the key up)
function okey(o, k, add) {
  var p = __STRP0__; var e = peek(__STREND__); var n = 0; var c = o + __OBJTAG__; var key = 0; var go = 1;
  if (__op(__KOWN__, k) == 0) { return k; }
  n = peek(k - 1);
  while (go) {
    key = peek(c);
    if (key == 0) { go = 0; }
    else if (key < 0) { c = key + __OBJTAG__; }
    else {
      if (__op(__KSTR__, key - __STRTAG__)) { if (peek(key - 1) == n) { if (__op(__MCMP__, key, k, n) == n) { return key - __STRTAG__; } } }
      c = c + 2;
    }
  }
  if (add == 0) { return k; }
  while (p < e) {
    p = p + __op(__MWALK__, p, e, n);
    if (p < e) { if (__op(__MCMP__, p + 1, k, n) == n) { return p + 1 - __STRTAG__; } p = p + n + 2; }
  }
  return k;
}
