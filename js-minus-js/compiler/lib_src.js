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

// a + chain inside console.log keeps its pieces on the stack: the ROM's pnK prints them (PRINT without a separator: an array
// or object as its string, pval); catnK joins them when an operator other than + follows. b2s: a boolean piece

function catn2(a, b) { return cat(a, b, 0); }
function catn3(a, b, c) { return cat(cat(a, b, 0), c, 0); }
function catn4(a, b, c, d) { return cat(catn3(a, b, c), d, 0); }
function catn5(a, b, c, d, e) { return cat(catn4(a, b, c, d), e, 0); }
function catn6(a, b, c, d, e, f) { return cat(catn5(a, b, c, d, e), f, 0); }
function catn7(a, b, c, d, e, f, g) { return cat(catn6(a, b, c, d, e, f), g, 0); }
function catn8(a, b, c, d, e, f, g, h) { return cat(catn7(a, b, c, d, e, f, g), h, 0); }

// ---------------- kinds
function isstr(v) { var a = v + __STRTAG__; if (a >= __STR_LO__) { if (a < __HEAP_HI__) { return 1; } } return 0; }
function isarr(v) { var a = v - __ARRTAG__; if (a >= __HEAP0__) { if (a < __HEAP_HI__) { return 1; } } return 0; }
function isobj(v) { var a = v + __OBJTAG__; if (a >= __HEAP0__) { if (a < __HEAP_HI__) { return 1; } } return 0; }
function rnd8(n) { return n + (8 - n % 8) % 8; }

// ---------------- allocation and the collector
function getfp() { return __fp(); }
// n words (a multiple of 8) -> a raw address; collects when the space is full (the stack up to this frame is the roots)
function halloc(n) {
  var hp = peek(__HP__);
  if (hp + n - 8 >= peek(__GCLIM__) + __H__ - 7) { gc(getfp(), n); hp = peek(__HP__); }
  poke(__HP__, hp + n);
  return hp + __HEAP0__;
}
// Cheney's copying collector between the two semi-spaces. HP / GCLIM are offsets from HEAP0: the next free word and the
// current space's start (0: space A, as RAM starts). The roots: the globals, the routines' value cells, the stack from SP0
// to gcsp. Then need more words must fit, or the program stops (out of memory).
function gc(gcsp, need) {
  var from = __HEAP0__; var to = __HEAP0__ + __H__; var p = 0; var e = 0;
  if (1) {
    if (peek(__GCLIM__)) { from = __HEAP0__ + __H__; to = __HEAP0__; }
    poke(__G_FLO__, from); poke(__G_FREE__, to);
    p = __DB__ + 1; e = __DB__ + peek(__INIT__ - 1);
    while (p < e) { poke(p, fwd(peek(p))); p++; }
    poke(__S_V__, fwd(peek(__S_V__))); poke(__S_K__, fwdkey(peek(__S_K__)));
    p = __SP0__;
    while (p < gcsp) { poke(p, fwd(peek(p))); p++; }
    p = to;
    while (p < peek(__G_FREE__)) { p = p + scan(p); }
    poke(__HP__, peek(__G_FREE__) - __HEAP0__); poke(__GCLIM__, to - __HEAP0__);
  }
  if (peek(__HP__) + need - 8 >= peek(__GCLIM__) + __H__ - 7) { oom(); }
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
  if (x % 8 == 1) { n = peek(s + 2); i = 0; while (i < n) { poke(s + 4 + i, fwd(peek(s + 4 + i))); i++; } }
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
function fwdkey(k) { if (isheap(k - __STRTAG__)) { return fwd(k - __STRTAG__) + __STRTAG__; } return k; }
function fwdobj(w, a, b) {
  var k = peek(b); var n = 0; var i = 0;
  if (k == 0 - 1) { return peek(b + 1) + a - b - __OBJTAG__; }
  if (k < 0) { return w; }
  n = peek(__G_FREE__); poke(__G_FREE__, n + 8);
  while (i < 8) { poke(n + i, peek(b + i)); i++; }
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
  if (kind == 0) { nw = x - kind; while (i < nw) { poke(n + i, peek(b + i)); i++; } }
  else {
    cap = peek(b + 1); len = peek(b + 2); p = peek(b + 3); nw = rnd8(cap + 4);
    poke(n, 0 - 3 - nw); poke(n + 1, cap); poke(n + 2, len); poke(n + 3, n + 4);
    while (i < len) { poke(n + 4 + i, peek(p + i)); i++; }
  }
  poke(__G_FREE__, n + nw); poke(b, 0 - 1); poke(b + 1, n);
  return n + w - b;
}

// ---------------- strings
// a new string of n bytes (its NUL written), uninitialised bytes -> its value
function newstr(n) {
  var nw = rnd8(n + 3); var b = halloc(nw);
  poke(b, 0 - 2 - nw); poke(b + 1, n); poke(b + 2 + n, 0);
  return b + 2 - __STRTAG__;
}
function slen(s) { return peek(s + __STRTAG__ - 1); }
// the decimal form of n: its length; written at p
function nlen(n) {
  var l = 1;
  if (n < 0) { l = 2; n = 0 - n; }
  while (n >= 10) { n = n / 10; l++; }
  return l;
}
function nput(n, p) {
  var e = p + nlen(n) - 1; var go = 1;
  if (n < 0) { poke(p, 45); n = 0 - n; }
  while (go) { poke(e, 48 + n % 10); n = n / 10; e = e - 1; if (n == 0) { go = 0; } }
  return 0;
}
// v as a string: a string is itself; a boolean (b: its static type is boolean) true / false; an array its elements
// joined by commas; an object [object Object]; a number its decimal form
function tostr(v, b) {
  var r = 0; var p = 0;
  if (isstr(v)) { return v; }
  if (isarr(v)) { return join(v, 0); }
  if (isobj(v)) {
    r = newstr(15); p = r + __STRTAG__;
    poke(p, 91); poke(p + 1, 111); poke(p + 2, 98); poke(p + 3, 106); poke(p + 4, 101); poke(p + 5, 99); poke(p + 6, 116);
    poke(p + 7, 32); poke(p + 8, 79); poke(p + 9, 98); poke(p + 10, 106); poke(p + 11, 101); poke(p + 12, 99); poke(p + 13, 116); poke(p + 14, 93);
    return r;
  }
  if (b) {                                      // (the string area's first strings, cc_ref SEED)
    if (v == 1) { return __TRUEV__; }
    if (v == 0) { return __FALSEV__; }
  }
  r = newstr(nlen(v)); nput(v, r + __STRTAG__);
  return r;
}
// a + b with a string on either side; fl: 1 a's static type is boolean, 2 b's
function cat(a, b, fl) {
  var la = 0; var lb = 0; var r = 0; var p = 0; var q = 0; var i = 0;
  if (isstr(a) == 0) { a = tostr(a, fl % 2); }
  if (isstr(b) == 0) { b = tostr(b, fl / 2); }
  la = slen(a); lb = slen(b);
  r = newstr(la + lb);
  p = r + __STRTAG__; q = a + __STRTAG__;
  while (i < la) { p[i] = q[i]; i++; }
  p = p + la; q = b + __STRTAG__; i = 0;
  while (i < lb) { p[i] = q[i]; i++; }
  return r;
}
// two strings: -1, 0, 1 (by character codes, as JavaScript compares them)
function scmp(a, b) {
  var la = slen(a); var lb = slen(b); var p = a + __STRTAG__; var q = b + __STRTAG__; var i = 0; var r = 2;
  if (a == b) { return 0; }
  while (r == 2) {
    if (i == la) { if (i == lb) { r = 0; } else { r = 0 - 1; } }
    else if (i == lb) { r = 1; }
    else if (p[i] < q[i]) { r = 0 - 1; }
    else if (p[i] > q[i]) { r = 1; }
    i++;
  }
  return r;
}
// DYN's slow path (== / != on two strings; the others with a string, array or object operand): op = the binary opcode
// + 64 * (a boolean on the left) + 128 * (on the right). Comparisons: arrays and objects as their strings; two strings by
// their characters, a string and a number as numbers (parseInt: 0 where JavaScript has NaN)
function dynop(a, b, op) {
  var f = op % 64; var c = 0;
  if (f == __OP_ADD__) { return cat(a, b, op / 64); }
  if (isarr(a) + isobj(a)) { a = tostr(a, 0); }
  if (isarr(b) + isobj(b)) { b = tostr(b, 0); }
  if (isstr(a) * isstr(b)) { c = scmp(a, b); }
  else {
    if (isstr(a)) { a = parseint(0, a); }
    if (isstr(b)) { b = parseint(0, b); }
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
  if (k >= slen(s)) { return 0; }
  c = peek(s + __STRTAG__ + k); r = newstr(1); poke(r + __STRTAG__, c);
  return r;
}

// ---------------- arrays
// a new array of capacity cap and length len (its elements uninitialised: the caller fills them before allocating again)
function newarr(cap, len) {
  var nw = 0; var b = 0;
  if (cap < 4) { cap = 4; }
  nw = rnd8(cap + 4); b = halloc(nw);
  poke(b, 0 - 3 - nw); poke(b + 1, cap); poke(b + 2, len); poke(b + 3, b + 4);
  return b + 3 + __ARRTAG__;
}
// room for need elements: a data block of twice the capacity (or need), the elements copied
function grow(x, need) {
  var a = x - __ARRTAG__; var cap = peek(a - 2) * 2; var d = 0; var p = 0; var n = 0; var i = 0;
  if (cap < need) { cap = need; }
  if (cap < 4) { cap = 4; }
  d = halloc(rnd8(cap));
  a = x - __ARRTAG__; p = peek(a); n = peek(a - 1);
  while (i < n) { d[i] = p[i]; i++; }
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
  if (isarr(x) == 0) { return 0; }
  if (n >= peek(a - 2)) { grow(x, n + 1); a = x - __ARRTAG__; }
  p = peek(a); p[n] = v; poke(a - 1, n + 1);
  return n + 1;
}
function pop(x) {
  var a = x - __ARRTAG__; var n = peek(a - 1); var p = peek(a);
  if (isarr(x) == 0) { return 0; }
  if (n == 0) { return 0; }
  poke(a - 1, n - 1);
  return p[n - 1];
}
// the elements as strings joined by sep (0: a comma)
function join(x, sep) {
  var a = x - __ARRTAG__; var n = peek(a - 1); var i = 0; var r = 0; var e = 0;
  if (sep == 0) { sep = newstr(1); poke(sep + __STRTAG__, 44); }
  r = newstr(0);
  while (i < n) {
    if (i > 0) { r = cat(r, sep, 0); }
    a = x - __ARRTAG__; e = peek(peek(a) + i);
    r = cat(r, e, 0); i++;
  }
  return r;
}

// ---------------- dynamic x[k] (the ROM's GETX / SETX call these for anything but an object)
function getx(x, k) {
  if (isstr(x)) { return charat(x, k); }
  if (isarr(x)) { return 0; }
  return peek(x + k);
}
function setx(x, k, v) {
  if (isarr(x)) { aset(x, k, v); return 0; }
  if (isstr(x) == 0) { poke(x + k, v); }
  return 0;
}

// ---------------- methods: (receiver, arguments) -> the result. A string's and an array's length both sit in the word
// before the value's address (the tags are multiples of 32768, and peek masks addresses to 15 bits): peek(x - 1)
function eqv(a, b) {                       // a === b (strings by their characters)
  if (a == b) { return 1; }
  if (isstr(a) * isstr(b)) { return scmp(a, b) == 0; }
  return 0;
}
// the first index i >= from (step 1) or <= from (step -1) where t occurs in s (a string) or equals an element; -1
function find(x, t, from, step) {
  var n = peek(x - 1); var p = 0; var q = 0; var m = 0; var j = 0; var ok = 0;
  if (isarr(x)) {
    while (from >= 0) { if (from >= n) { return 0 - 1; } if (eqv(peek(peek(x) + from), t)) { return from; } from = from + step; }
    return 0 - 1;
  }
  if (isstr(x) * isstr(t) == 0) { return 0 - 1; }
  p = x + __STRTAG__; q = t + __STRTAG__; m = peek(t - 1);
  if (step < 0) { if (from > n - m) { from = n - m; } }
  while (from >= 0) {
    if (from > n - m) { return 0 - 1; }
    ok = 1; j = 0;
    while (j < m) { if (p[from + j] != q[j]) { ok = 0; j = m; } j++; }
    if (ok) { return from; }
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
  var n = peek(x - 1); var r = 0; var p = 0; var q = 0; var i = 0;
  a = cidx(a, n); b = cidx(b, n);
  if (b < a) { b = a; }
  if (isstr(x)) { r = newstr(b - a); p = r + __STRTAG__; q = x + __STRTAG__ + a; while (i < b - a) { p[i] = q[i]; i++; } return r; }
  if (isarr(x) == 0) { return 0; }
  r = newarr(b - a, b - a); p = peek(r); q = peek(x) + a;
  while (i < b - a) { p[i] = q[i]; i++; }
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
  var n = 0; var m = 1; var r = 0; var p = 0; var i = 0;
  if (isarr(x) == 0) { return cat(x, y, 0); }
  n = peek(x - 1);
  if (isarr(y)) { m = peek(y - 1); }
  r = newarr(n + m, n + m); p = peek(r);
  while (i < n) { p[i] = peek(peek(x) + i); i++; }
  if (isarr(y)) { i = 0; while (i < m) { p[n + i] = peek(peek(y) + i); i++; } }
  else { p[n] = y; }
  return r;
}
function reverse(x) {
  var n = peek(x - 1); var p = peek(x); var i = 0; var t = 0;
  if (isarr(x) == 0) { return x; }
  while (i < n / 2) { t = p[i]; p[i] = p[n - 1 - i]; p[n - 1 - i] = t; i++; }
  return x;
}
function fill(x, v) {
  var n = peek(x - 1); var p = peek(x); var i = 0;
  if (isarr(x) == 0) { return x; }
  while (i < n) { p[i] = v; i++; }
  return x;
}
function shift(x) {
  var n = peek(x - 1); var p = peek(x); var i = 1; var v = 0;
  if (isarr(x) == 0) { return 0; }
  if (n == 0) { return 0; }
  v = p[0];
  while (i < n) { p[i - 1] = p[i]; i++; }
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
  if (isstr(s) == 0) { return 0; } if (k < 0) { return 0; } if (k >= peek(s - 1)) { return 0; }
  return peek(s + __STRTAG__ + k);
}
function fromcc(d, c) { var r = newstr(1); poke(r + __STRTAG__, c); return r; }
// a copy of s with letters lo .. lo + 25 moved by d
function chcase(s, lo, d) {
  var n = peek(s - 1); var r = newstr(n); var p = r + __STRTAG__; var q = s + __STRTAG__; var i = 0; var c = 0;
  while (i < n) { c = q[i]; if (c >= lo) { if (c < lo + 26) { c = c + d; } } p[i] = c; i++; }
  return r;
}
function upper(s) { if (isstr(s) == 0) { return s; } return chcase(s, 97, 0 - 32); }
function lower(s) { if (isstr(s) == 0) { return s; } return chcase(s, 65, 32); }
function isblank(c) { return (c == 32) + (c == 9) + (c == 10) + (c == 13); }
function trim(s) {
  var p = s + __STRTAG__; var a = 0; var b = peek(s - 1); var go = 1;
  if (isstr(s) == 0) { return s; }
  while (go) { go = 0; if (a < b) { if (isblank(p[a])) { a++; go = 1; } } }
  go = 1;
  while (go) { go = 0; if (b > a) { if (isblank(p[b - 1])) { b = b - 1; go = 1; } } }
  return slice(s, a, b);
}
function startswith(s, t) { if (isstr(s) * isstr(t) == 0) { return 0; } if (peek(t - 1) > peek(s - 1)) { return 0; } return find(s, t, 0, 0 - 1) == 0; }
function endswith(s, t) {
  var k = peek(s - 1) - peek(t - 1);
  if (isstr(s) * isstr(t) == 0) { return 0; } if (k < 0) { return 0; }
  return find(s, t, k, 0 - 1) == k;
}
function repeat(s, n) {
  var r = newstr(0);
  if (isstr(s) == 0) { return r; }
  while (n > 0) { r = cat(r, s, 0); n = n - 1; }
  return r;
}
// s.split(sep): the pieces between the occurrences of sep (sep "": the characters) as an array
function split(s, sep) {
  var r = newarr(0, 0); var i = 0; var j = 0; var m = 0;
  if (isstr(s) * isstr(sep) == 0) { push(r, s); return r; }
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
  if (isstr(s) == 0) { return s; }
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
function puts(s) { var p = s + __STRTAG__; var n = peek(s - 1); var i = 0; while (i < n) { putc(p[i]); i++; } return 0; }
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
function insel(v, d) { if (isstr(v)) { return qstr(v); } return ins(v, d); }
function ins(v, d) {
  var n = 0; var i = 0;
  if (isarr(v)) {
    n = peek(v - 1);
    if (n == 0) { putc(91); putc(93); return 0; }
    if (d > 2) { putc(91); putc(65); putc(114); putc(114); putc(97); putc(121); putc(93); return 0; }
    putc(91); putc(32);
    while (i < n) { if (i) { putc(44); putc(32); } insel(peek(peek(v) + i), d + 1); i++; }
    putc(32); putc(93); return 0;
  }
  if (isobj(v)) { return insobj(v, d); }
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
        if (isstr(k - __STRTAG__) == pass) {
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
  if (ok) { return puts(s); }
  return qstr(s);
}

// ---------------- string keys built at run time: o[k] for a string k that isn't the program's own (a heap string, or one of
// the string area's first ones, SEED) uses the program's literal or name with those characters if there is one (from
// STRP0 the string area holds [len][bytes][0] each, up to the end the compiler left at STREND), else one of the object's
// keys with them, else k itself (GETX / SETX call this before they look the key up)
function isheap(k) { var a = k + __STRTAG__; if (a >= __HEAP0__) { if (a < __HEAP_HI__) { return 1; } } return 0; }
function notown(k) { var a = k + __STRTAG__; if (isstr(k)) { if (a < __STRP0__) { return 1; } return a >= __HEAP0__; } return 0; }
function seq(p, q, n) { var i = 0; while (i < n) { if (p[i] != q[i]) { return 0; } i++; } return 1; }
function okey(o, k) {
  var p = __STRP0__; var e = peek(__STREND__); var n = 0; var c = 0; var key = 0; var go = 1;
  if (notown(k) == 0) { return k; }
  n = peek(k - 1);
  while (p < e) { if (peek(p) == n) { if (seq(p + 1, k + __STRTAG__, n)) { return p + 1 - __STRTAG__; } } p = p + peek(p) + 2; }
  c = o + __OBJTAG__;
  while (go) {
    key = peek(c);
    if (key == 0) { go = 0; }
    else if (key < 0) { c = key + __OBJTAG__; }
    else {
      if (notown(key - __STRTAG__)) { if (peek(key - 1) == n) { if (seq(key, k + __STRTAG__, n)) { return key - __STRTAG__; } } }
      c = c + 2;
    }
  }
  return k;
}
// ---------------- the network (net/device.py has the protocol). NET's words: 256 + byte appends a URL byte, 512 GETs the
// URL (the HTTP status, -1 if it failed), 768 is the body's next byte (-1 past its end). Bit 12 alternates (the cell
// NETSEQ), so on the page consecutive words always differ: the modem tells a new request from the last, and its answer
// carries the bit (machine/gen_css.py). fetch(url) / read() are called like parseInt (cc_ref GLOBALS): d is a dummy.
function netw(x) { var s = 4096 - peek(__NETSEQ__); poke(__NETSEQ__, s); return __op(__W_NET__, x + s); }
function fetch(d, u) {
  if (isstr(u) == 0) { u = tostr(u, 0); }
  var p = u + __STRTAG__; var c = peek(p);
  while (c) { netw(256 + c); p++; c = peek(p); }
  return netw(512);
}
function read(d) { return netw(768); }
