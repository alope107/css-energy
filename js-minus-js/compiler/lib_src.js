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

// ROM address 0 (the first routine): a call of a function that is never declared, and a read of an implicit global that is never
// assigned (cc_ref.NIMP), land here, since the page's undefined labels are 0. JavaScript's ReferenceError, uncaught: the
// program stops. (The m_ routines print the messages: rtlib.py makes them from its MSGS, a putc per character)
function refstub() { m_uncaught(); m_referr(); putc(10); halt(); return 0; }


function rnd8(n) { return n + (8 - n % 8) % 8; }

// ---------------- allocation and the collector
// NEW found the heap full: collect; NEW executes again when this returns
function gcnew() { gc(8); return 0; }
// ALLOC found the heap full (nw: its block's words): collect; ALLOC executes again
function galloc(nw) { gc(nw); return 0; }
// a string's + found the heap full: collect, then join
function gccat(a, b) { gc(catw(a, b)); return __dadd(a, b); }
// a special (true, false, null, undefined, NaN, +-Infinity, -0) as its name, as a string's + joins it (-0 as "0"): the
// built-in strings (cc_ref BSTRS), twelve words apart; anything else as it is
function catv(v) {
  if (__kind(v, __K_SPECIAL__) == 0) { return v; }
  if (v == __MZERO__) { return __S_ZERO__; }
  return __BSTRV0__ + 12 * (v - __SPV0__);
}
// v's characters: a string's (or a special's name's) length, a number's digits
function clen(v) { v = catv(v); if (__kind(v, __K_STR__)) { return peek(v - 1); } return __kind(v, __K_NLEN__); }
// a JavaScript boolean from 0 / 1 (the ROM's own tests stay raw)
function jsb(c) { return __FALSE__ - c; }
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
  a = w + __DBLTAG__;
  if (a >= flo + 4) { if (a < flo + __H__) { return fwdblk(w, a - 4, 2); } }
  return w;
}
// a stack word: a reference only if it starts a block in the map (MFREF found it in a from-space tag range)
function fwdc(w, flo) {
  var b = w + __OBJTAG__;
  if ((b < flo) + (b >= flo + __H__)) { b = w + __STRTAG__ - 2; }
  if ((b < flo) + (b >= flo + __H__)) { b = w - __ARRTAG__ - 3; }
  if ((b < flo) + (b >= flo + __H__)) { b = w + __DBLTAG__ - 4; }
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
  else if (kind == 2) { __mcpy(n, b, 8); nw = 8; }
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
// v as a string: a string is itself; a special its name (-0 "0"); an array its elements joined by commas; an object
// [object Object]; a number its decimal form
function tostr(v) {
  var r = 0;
  if (__kind(v, __K_STR__)) { return v; }
  if (__kind(v, __K_SPECIAL__)) { return catv(v); }
  if (__kind(v, __K_DBL__)) { return numstr(v); }
  if (__kind(v, __K_ARR__)) { return join(v, 0); }
  if (__kind(v, __K_OBJ__)) {
    r = newstr(15);
    poke(r, 91); poke(r + 1, 111); poke(r + 2, 98); poke(r + 3, 106); poke(r + 4, 101); poke(r + 5, 99); poke(r + 6, 116);
    poke(r + 7, 32); poke(r + 8, 79); poke(r + 9, 98); poke(r + 10, 106); poke(r + 11, 101); poke(r + 12, 99); poke(r + 13, 116); poke(r + 14, 93);
    return r;
  }
  r = newstr(__kind(v, __K_NLEN__)); __nput(r, v);
  return r;
}
// an array or object as a primitive (its string); anything else as it is
function prim(v) { if (__kind(v, __K_AO__)) { return tostr(v); } return v; }
// two strings: -1, 0, 1 (by character codes, as JavaScript compares them)
function scmp(a, b) {
  var la = peek(a - 1); var lb = peek(b - 1); var m = la; var i = 0; var c = 0; var d = 0;
  if (a == b) { return 0; }
  if (lb < m) { m = lb; }
  i = __mcmp(a, b, m);
  if (i < m) { c = peek(a + i); d = peek(b + i); return (c > d) - (c < d); }
  return (la > lb) - (la < lb);
}
// The dynamic operators' slow paths: DADD ... DNE trap here (cc_ref.dyn_fast: whatever isn't two integers, or for + a string
// the cat class joins; DEQ / DNE two strings); their frame is at TRAPDEF and the machine moves the value into the
// instruction's destination. + : arrays and objects as their strings, then a string on either side joins; otherwise numbers
// (ToNumber: true 1, false and null 0, undefined NaN, a string's integer)
function dadd(a, b) {
  a = prim(a); b = prim(b);
  if (__kind(a, __K_STR__) + __kind(b, __K_STR__)) {
    if (__kind(a, __K_DBL__)) { a = numstr(a); }                // (the cat class joins strings, integers and specials)
    if (__kind(b, __K_DBL__)) { b = numstr(b); }
    return __dadd(a, b);
  }
  return arith(0, a, b);
}
function dsub(a, b) { return arith(1, a, b); }
function dmul(a, b) { return arith(2, a, b); }
function ddiv(a, b) { return arith(3, a, b); }
function dmod(a, b) { return arith(4, a, b); }
function dneg(a, b) { return arith(5, a, 0); }
// ToNumber for the operators: a number (an integer of the machine's range, NaN, +-Infinity, -0 or a double); objects as their
// strings, booleans 1 / 0, null 0, undefined NaN
function tonum(v) {
  v = prim(v);
  if (__kind(v, __K_STR__)) { return strnum(v); }
  if (__kind(v, __K_NUM__)) { return v; }
  if (v == __TRUE__) { return 1; }
  if ((v == __FALSE__) + (v == __NULL__)) { return 0; }
  return __NAN__;
}
// op 0 + 1 - 2 * 3 / 4 % 5 unary - of two values as numbers, in the FPU (IEEE doubles, as JavaScript computes)
function arith(op, a, b) {
  a = tonum(a); b = tonum(b);
  if (op == 0) { __fl(__FL_FADD__, __F0__, a, b); }
  else if (op == 1) { __fl(__FL_FSUB__, __F0__, a, b); }
  else if (op == 2) { __fl(__FL_FMUL__, __F0__, a, b); }
  else if (op == 3) { __fl(__FL_FDIV__, __F0__, a, b); }
  else if (op == 4) { __fl(__FL_FMOD__, __F0__, a, b); }
  else { __fl(__FL_FMUL__, __F0__, a, 0 - 1); }
  return fbox();
}
// DBIT's trap: the bitwise operator in its instruction's A (A's 1024s: 0 & 1 | 2 ^ 3 << 4 >> 5 >>>; the return word holds the
// instruction's address / 2) of two values as numbers, in the FPU (32-bit integers, as JavaScript computes)
function dbit(a, b) {
  var k = peek(2 * (peek(__fp()) % 8192)) % 8192 / 1024;
  a = tonum(a); b = tonum(b);
  if (k == 0) { __fl(__FL_FAND__, __F0__, a, b); }
  else if (k == 1) { __fl(__FL_FOR__, __F0__, a, b); }
  else if (k == 2) { __fl(__FL_FXOR__, __F0__, a, b); }
  else if (k == 3) { __fl(__FL_FSHL__, __F0__, a, b); }
  else if (k == 4) { __fl(__FL_FSHR__, __F0__, a, b); }
  else { __fl(__FL_FUSHR__, __F0__, a, b); }
  return fbox();
}

// ---------------- numbers. The FPU (cc_ref FLOPS / FVOPS): __fl(K, d, a, b) makes the number line d (an address, or a double's
// value) op K of the numbers a and b (an integer of the machine's range, NaN, +-Infinity, -0, or a double: a number line's
// address - DBLTAG); __fv(K, a, b) is a value. A boxed double is an 8-word heap block whose second line is its number line.
// F0 ... F13: the scratch lines (in an FPU instruction the constants 100 ... 113: FSCR + i, at FPU + 4 i; F0 arith's, F1 numscan's,
// F2 ... numstr's); DIGS: a digit buffer
// the number in scratch line F0 as a value: an integer of the machine's range, a special, or a new boxed double. (A scratch line
// is an FPU operand only as that constant: a routine names its lines, it can't be handed one)
function fbox() {
  var v = __fv(__FV_FNORM__, __F0__, 0); var r = 0;
  if (v != __F0__) { return v; }
  r = __alloc(0, __A_DBL__); __mcpy(r, __FPU__, 4);
  return r;
}
// a and b compared: -1, 0, 1, or 2 (unordered: NaN). Arrays and objects as their strings; two strings by their characters,
// otherwise as numbers
function dcmp(a, b) {
  a = prim(a); b = prim(b);
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) { return scmp(a, b); }
  return __fv(__FV_FCMP__, tonum(a), tonum(b));
}
// a string as a number (JavaScript's Number(s)): a decimal literal or Infinity, with blanks around it ("" is 0); else NaN
function strnum(s) {
  var n = peek(s - 1); var i = skipbl(s, 0, n); var e = n; var r = 0;
  while (e > i) { if (isblank(peek(s + e - 1))) { e = e - 1; } else { n = 0 - 1; e = 0 - e; } }
  if (e < 0) { e = 0 - e; }
  if (i == e) { return 0; }
  r = numscan(s, i, e);
  if (peek(__NEND__) != e) { return __NAN__; }
  return r;
}
// the index of the first character of s from i on that isn't blank (n: s's length)
function skipbl(s, i, n) {
  var go = 1;
  while (go) { go = 0; if (i < n) { if (isblank(peek(s + i))) { i++; go = 1; } } }
  return i;
}
// the number the decimal literal at s + i reads as (up to e: a sign, digits, a fraction, an exponent, or Infinity); NEND := the
// index after it (i: none). The first 17 significant digits count (exact while their integer is below 2^53), scaled by a power
// of ten (one rounding up to 10^22)
function numscan(s, i, e) {
  var i0 = i; var neg = 0; var c = 0; var nd = 0; var ex = 0; var any = 0; var es = 1; var ev = 0; var go = 1; var dot = 0;
  c = peek(s + i);
  if (i < e) { if (c == 45) { neg = 1; i++; } else if (c == 43) { i++; } }
  if (i + 8 <= e) {
    if (__mcmp(s + i, __BSTRV0__, 8) == 8) { poke(__NEND__, i + 8); if (neg) { return __NINF__; } return __INF__; }
  }
  __fl(__FL_FLD__, __F1__, 0, 0);
  while (go) {
    go = 0;
    if (i < e) {
      c = peek(s + i);
      if ((c >= 48) * (c <= 57)) {
        any = 1; go = 1; i++;
        if (nd < 17) {
          if (nd + (c != 48)) { __fl(__FL_FMUL__, __F1__, __F1__, 10); __fl(__FL_FADD__, __F1__, __F1__, c - 48); nd++; }
          ex = ex - dot;
        } else { ex = ex + 1 - dot; }
      } else if ((c == 46) * (dot == 0)) { dot = 1; go = 1; i++; }
    }
  }
  if (any == 0) { poke(__NEND__, i0); return __NAN__; }
  if (i < e) {
    c = peek(s + i);
    if ((c == 101) + (c == 69)) {
      c = i + 1; go = 0;
      if (c < e) { if (peek(s + c) == 45) { es = 0 - 1; c++; } else if (peek(s + c) == 43) { c++; } }
      while (c < e) { if ((peek(s + c) >= 48) * (peek(s + c) <= 57)) { if (ev < 10000) { ev = ev * 10 + peek(s + c) - 48; } c++; go = 1; } else { e = 0 - e; } }
      if (e < 0) { e = 0 - e; }
      if (go) { i = c; ex = ex + es * ev; }
    }
  }
  poke(__NEND__, i);
  if (ex > 22) { __fl(__FL_FP10__, __F2__, 0, 22); __fl(__FL_FMUL__, __F1__, __F1__, __F2__); ex = ex - 22; }
  if (ex > 0) { __fl(__FL_FP10__, __F2__, 0, ex); __fl(__FL_FMUL__, __F1__, __F1__, __F2__); }
  if (ex < 0 - 22) { __fl(__FL_FP10__, __F2__, 0, 22); __fl(__FL_FDIV__, __F1__, __F1__, __F2__); ex = ex + 22; }
  if (ex < 0) { __fl(__FL_FP10__, __F2__, 0, 0 - ex); __fl(__FL_FDIV__, __F1__, __F1__, __F2__); }
  if (neg) { __fl(__FL_FMUL__, __F0__, __F1__, 0 - 1); } else { __fl(__FL_FLD__, __F0__, __F1__, 0); }
  return fbox();
}
// a number literal (NUMLIT, the first time it is read): its string's number
function numlit(s, d) { return numscan(s, 0, peek(s - 1)); }

// ---------------- a double as a string (JavaScript's Number::toString): the shortest digits that read back as the number, the
// closest of those (ties to even). Each candidate is tested exactly with the FPU (the two-product's low part makes M * 5^n
// exact; a test is an exact comparison): an integer below 2^53 is its own digits; a fraction's candidates are the integers
// nearest |v| * 10^n (n = 0 ... 22), an integer's from 2^53 on c * 10^m (m = 0 ... 22), the shortest found by halving (a
// shorter candidate reads back only if every longer one does). Outside those (below about 1e-6, or past 1e22 with many digits)
// 17 digits, rounded once
function numstr(v) {
  var neg = __fv(__FV_FCMP__, v, 0) < 0; var E = 0; var q = 0; var k = 0; var lo = 0; var hi = 0; var mid = 0; var nd = 0; var n = 0;
  __fl(__FL_FABS__, __F2__, v, 0);
  E = __fv(__FV_FEXPO__, __F2__, 0); q = E - 52;
  __fl(__FL_FSCALE__, __F3__, __F2__, 0 - q); __fl(__FL_FSCALE__, __F11__, 1, 52);         // M (|v| = M * 2^q); 2^52
  __fl(__FL_FFLOOR__, __F4__, __F2__, 0);
  if (E < 53) { if (__fv(__FV_FCMP__, __F4__, __F2__) == 0) { __fl(__FL_FCDIG__, __F7__, __F2__, 0); nd = limbdig(); return numfmt(neg, nd, nd); } }
  k = __fv(__FV_FLOG10__, __F2__, 0);
  if (E < 53) {                                                  // a fraction: p digits at scale n = p - 1 - k
    lo = k + 1; if (lo < 1) { lo = 1; } hi = 23 + k; if (hi > 17) { hi = 17; }
    if (lo > hi) { return numapx(neg, k); }
    if (hi < 17) { if (__fv(__FV_FCOK__, __F2__, hi - 1 - k) == 0) { return numapx(neg, k); } }
    while (lo < hi) { mid = (lo + hi) / 2; if (__fv(__FV_FCOK__, __F2__, mid - 1 - k)) { hi = mid; } else { lo = mid + 1; } }
    n = lo - 1 - k; __fl(__FL_FCDIG__, __F7__, __F2__, n); nd = limbdig();
    return numfmt(neg, nd, nd - n);
  }
  lo = 1; hi = 17;                                               // an integer from 2^53: c * 10^m, m = k - p + 1
  if (lo < k - 21) { lo = k - 21; }
  if (lo > hi) { return numapx(neg, k); }
  if (nearok(q, k - hi + 1) == 0) { return numapx(neg, k); }
  while (lo < hi) { mid = (lo + hi) / 2; if (nearok(q, k - mid + 1)) { hi = mid; } else { lo = mid + 1; } }
  n = k - lo + 1; nearok(q, n); nd = putdig(peek(__CLO__));
  return numfmt(neg, nd, nd + n);
}
// a fraction's candidate at scale n (0 ... 22): c, the integer nearest M * 2^q * 10^n (ties even), as F7 + CLO (a small integer);
// -> 1 if c * 10^-n reads back as the number (F2 = |v|, F3 = M, F11 = 2^52): |c * 2^(t + 1) - 2 M 5^n| < 5^n, t = -(q + n)
function cand(q, n) {
  var s = q + n; var t = 0 - s; var clo = 0; var r = 0;
  __fl(__FL_FP10__, __F4__, 0, n); __fl(__FL_FSCALE__, __F4__, __F4__, 0 - n);              // 5^n
  __fl(__FL_FMUL__, __F5__, __F3__, __F4__); __fl(__FL_FTPLO__, __F6__, __F3__, __F4__);      // M * 5^n = Nh + Nl
  __fl(__FL_FSCALE__, __F7__, __F5__, s); __fl(__FL_FSCALE__, __F8__, __F6__, s);            // X = xh + xl
  if (s >= 0) { poke(__CLO__, __fv(__FV_FINT__, __F8__, 0)); return 1; }                    // an integer: c is X
  if (__fv(__FV_FCMP__, __F7__, __F11__) >= 0) { clo = rhe(); }                            // xh an integer: round xl (F8)
  else {
    __fl(__FL_FFLOOR__, __F9__, __F7__, 0); __fl(__FL_FSUB__, __F10__, __F7__, __F9__);       // f, xh - f
    __fl(__FL_FSCALE__, __F12__, 1, 0 - 1); __fl(__FL_FSUB__, __F10__, __F12__, __F10__);     // 0.5 - (xh - f)
    r = __fv(__FV_FCMP__, __F8__, __F10__);
    if (r == 0) { __fl(__FL_FMOD__, __F13__, __F9__, 2); r = 2 * (__fv(__FV_FCMP__, __F13__, 0) != 0) - 1; }    // a tie: the even one
    if (r > 0) { __fl(__FL_FADD__, __F7__, __F9__, 1); } else { __fl(__FL_FLD__, __F7__, __F9__, 0); }
  }
  poke(__CLO__, clo);
  __fl(__FL_FSCALE__, __F9__, __F7__, t + 1); __fl(__FL_FSCALE__, __F10__, __F5__, 1); __fl(__FL_FSUB__, __F9__, __F9__, __F10__);
  if (clo) { __fl(__FL_FSCALE__, __F10__, clo, t + 1); __fl(__FL_FADD__, __F9__, __F9__, __F10__); }
  __fl(__FL_FSCALE__, __F10__, __F6__, 1); __fl(__FL_FSUB__, __F9__, __F9__, __F10__);     // D = (c - X) * 2^(t + 1)
  if (__fv(__FV_FCMP__, __F9__, 0) < 0) {                                                 // c below: at a power of two the gap is half
    if (__fv(__FV_FCMP__, __F3__, __F11__) == 0) { if (q > 0 - 1074) { __fl(__FL_FSCALE__, __F4__, __F4__, 0 - 1); } }
  }
  __fl(__FL_FABS__, __F9__, __F9__, 0); r = __fv(__FV_FCMP__, __F9__, __F4__);
  __fl(__FL_FMOD__, __F13__, __F3__, 2);
  return (r == 0 - 1) + (r == 0) * (__fv(__FV_FCMP__, __F13__, 0) == 0);
}
// an integer's (from 2^53: F2, M = F3, q > 0) closest c with c * 10^m inside its rounding interval (gaps 2^q, below a power of
// two 2^(q - 1)), as F7 + CLO; -> 0 if there is none. ch = round(v / 10^m) is a double; the exact remainder corrects it
function nearok(q, m) {
  var d0 = 0; var d = 0; var j = 0; var bd = 0; var found = 0; var r = 0; var p2 = __fv(__FV_FCMP__, __F3__, __F11__) == 0; var me = 0; var co = 0;
  __fl(__FL_FMOD__, __F13__, __F3__, 2); me = __fv(__FV_FCMP__, __F13__, 0) == 0;          // M even
  __fl(__FL_FP10__, __F4__, 0, m);
  __fl(__FL_FDIV__, __F7__, __F2__, __F4__); __fl(__FL_FROUND__, __F7__, __F7__, 0);                  // ch
  __fl(__FL_FMOD__, __F13__, __F7__, 2); co = __fv(__FV_FCMP__, __F13__, 0) != 0;                    // ch odd
  __fl(__FL_FMUL__, __F5__, __F7__, __F4__); __fl(__FL_FTPLO__, __F6__, __F7__, __F4__);
  __fl(__FL_FSUB__, __F8__, __F2__, __F5__); __fl(__FL_FSUB__, __F8__, __F8__, __F6__);              // base = v - ch * 10^m
  __fl(__FL_FDIV__, __F9__, __F8__, __F4__); __fl(__FL_FROUND__, __F9__, __F9__, 0); d0 = __fv(__FV_FINT__, __F9__, 0);
  j = 0 - 1;
  while (j < 2) {
    d = d0 + j;
    __fl(__FL_FMUL__, __F10__, d, __F4__); __fl(__FL_FSUB__, __F10__, __F8__, __F10__);              // D = v - (ch + d) * 10^m
    __fl(__FL_FSCALE__, __F12__, 1, q - 1 - p2 * (__fv(__FV_FCMP__, __F10__, 0) > 0));             // the half gap on its side
    __fl(__FL_FABS__, __F10__, __F10__, 0); r = __fv(__FV_FCMP__, __F10__, __F12__);
    if ((r == 0 - 1) + (r == 0) * me) {
      if (found == 0) { found = 1; bd = d; __fl(__FL_FLD__, __F9__, __F10__, 0); }
      else {
        r = __fv(__FV_FCMP__, __F10__, __F9__);
        if (r == 0 - 1) { bd = d; __fl(__FL_FLD__, __F9__, __F10__, 0); }
        if (r == 0) { if ((co + bd) % 2 != 0) { bd = d; } }                                       // a tie: the even c
      }
    }
    j++;
  }
  poke(__CLO__, bd);
  return found;
}
// 17 digits, rounded once (the numbers outside the exact search)
function numapx(neg, k) {
  var n = 16 - k; var nd = 0;
  __fl(__FL_FLD__, __F7__, __F2__, 0);
  if (n > 300) { __fl(__FL_FP10__, __F4__, 0, 300); __fl(__FL_FMUL__, __F7__, __F7__, __F4__); n = n - 300; }
  if (n > 0) { __fl(__FL_FP10__, __F4__, 0, n); __fl(__FL_FMUL__, __F7__, __F7__, __F4__); }
  else { __fl(__FL_FP10__, __F4__, 0, 0 - n); __fl(__FL_FDIV__, __F7__, __F7__, __F4__); }
  __fl(__FL_FROUND__, __F7__, __F7__, 0);
  nd = putdig(0);
  return numfmt(neg, nd, nd - (16 - k));
}
// F8 rounded half to even (a small integer)
function rhe() {
  var f = 0; var r = 0;
  __fl(__FL_FFLOOR__, __F12__, __F8__, 0); __fl(__FL_FSUB__, __F13__, __F8__, __F12__); __fl(__FL_FSCALE__, __F10__, 1, 0 - 1);
  r = __fv(__FV_FCMP__, __F13__, __F10__); f = __fv(__FV_FINT__, __F12__, 0);
  if (r > 0) { return f + 1; }
  if (r == 0) { if (f % 2 != 0) { return f + 1; } }
  return f;
}
// the decimal digits of FCDIG's limbs in F7 (c = l0 + l1 1e5 + l2 1e10 + l3 1e15) at DIGS (characters) -> their count
function limbdig() {
  var j = 3; var n = 0; var v = 0; var go = 0; var d = 0;
  while (j >= 0) {
    v = peek(__FPU__ + 28 + j);
    if (go) { __mfill(__DIGS__ + n, 48, 5); d = __kind(v, __K_NLEN__); __nput(__DIGS__ + n + 5 - d, v); n = n + 5; }
    else if ((v != 0) + (j == 0)) { d = __kind(v, __K_NLEN__); __nput(__DIGS__ + n, v); n = n + d; go = 1; }
    j = j - 1;
  }
  return n;
}
// the decimal digits of the integer in F7, plus clo (a small integer), at DIGS (characters) -> their count
function putdig(clo) {
  var n = __fv(__FV_FLOG10__, __F7__, 0) + 1; var j = 0; var c = clo; var d = 0;
  while (j < n) { poke(__DIGS__ + j, 48 + __fv(__FV_FDIGIT__, __F7__, n - 1 - j)); j++; }
  j = n - 1;
  while (c != 0) {
    if (j < 0) { __mcpy(__DIGS__ + 1, __DIGS__, n); poke(__DIGS__, 48 + c); n++; c = 0; }       // a carry past the first digit
    else {
      d = peek(__DIGS__ + j) - 48 + c; c = 0;
      while (d < 0) { d = d + 10; c = c - 1; }
      while (d > 9) { d = d - 10; c = c + 1; }
      poke(__DIGS__ + j, 48 + d); j = j - 1;
    }
  }
  return n;
}
// DIGS' nd digits (trailing zeros dropped) with the decimal point at pt (0.d1 d2 ... * 10^pt), as JavaScript writes them: fixed
// for -6 < pt <= 21, else d1.d2...e+-x
function numfmt(neg, nd, pt) {
  var len = 0; var r = 0; var p = 0; var ex = pt - 1; var ae = ex;
  while ((nd > 1) * (peek(__DIGS__ + nd - 1) == 48)) { nd = nd - 1; }
  if (ae < 0) { ae = 0 - ae; }
  if ((pt >= nd) * (pt <= 21)) { len = pt; }
  else if ((pt > 0) * (pt <= 21)) { len = nd + 1; }
  else if ((pt > 0 - 6) * (pt <= 0)) { len = nd + 2 - pt; }
  else { len = nd + (nd > 1) + 2 + __kind(ae, __K_NLEN__); }
  r = newstr(len + neg); p = r;
  if (neg) { poke(p, 45); p++; }
  if ((pt >= nd) * (pt <= 21)) { __mcpy(p, __DIGS__, nd); __mfill(p + nd, 48, pt - nd); }
  else if ((pt > 0) * (pt <= 21)) { __mcpy(p, __DIGS__, pt); poke(p + pt, 46); __mcpy(p + pt + 1, __DIGS__ + pt, nd - pt); }
  else if ((pt > 0 - 6) * (pt <= 0)) { poke(p, 48); poke(p + 1, 46); __mfill(p + 2, 48, 0 - pt); __mcpy(p + 2 - pt, __DIGS__, nd); }
  else {
    poke(p, peek(__DIGS__)); p++;
    if (nd > 1) { poke(p, 46); __mcpy(p + 1, __DIGS__ + 1, nd - 1); p = p + nd; }
    poke(p, 101); if (ex < 0) { poke(p + 1, 45); } else { poke(p + 1, 43); }
    __nput(p + 2, ae);
  }
  return r;
}
function dlt(a, b) { return jsb(dcmp(a, b) == 0 - 1); }
function dgt(a, b) { return jsb(dcmp(a, b) == 1); }
function dle(a, b) { var c = dcmp(a, b); return jsb((c == 0 - 1) + (c == 0)); }
function dge(a, b) { var c = dcmp(a, b); return jsb((c == 0) + (c == 1)); }
// a === b, raw: strings by their characters, NaN equal to nothing, -0 equal to 0
function deqr(a, b) {
  var n = 0;
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) {
    if (a == b) { return 1; }
    n = peek(a - 1);
    if (peek(b - 1) != n) { return 0; }
    return __mcmp(a, b, n) == n;
  }
  if (__kind(a, __K_NUM__) * __kind(b, __K_NUM__)) { return __fv(__FV_FCMP__, a, b) == 0; }
  return a == b;
}
function deq(a, b) { return jsb(deqr(a, b)); }
function dne(a, b) { return jsb(deqr(a, b) == 0); }
// a == b, raw: null and undefined equal each other only; two objects by identity; otherwise primitives (an object's
// string), two strings by their characters, anything else as numbers
function leqr(a, b) {
  if ((a == __NULL__) + (a == __UNDEF__)) { return (b == __NULL__) + (b == __UNDEF__); }
  if ((b == __NULL__) + (b == __UNDEF__)) { return 0; }
  if (__kind(a, __K_AO__) * __kind(b, __K_AO__)) { return a == b; }
  a = prim(a); b = prim(b);
  if (__kind(a, __K_STR__) * __kind(b, __K_STR__)) { return deqr(a, b); }
  return dcmp(a, b) == 0;
}
function dleq(a, b) { return jsb(leqr(a, b)); }
function dlne(a, b) { return jsb(leqr(a, b) == 0); }
// JLT ... JNE in user code on anything but two integers: the jump is decided here. The frame is at TRAPOFF and returns to
// the instruction after the jump; a jump taken rewrites the return word to its target (A, from the instruction itself)
function jcmp(a, b) {
  var f = __fp(); var r = 2 * (peek(f) % 8192); var w0 = peek(r - 2); var op = w0 / 8192; var c = 0; var t = 0;
  if (op == __OP_JEQ__) { t = deqr(a, b); }
  else if (op == __OP_JNE__) { t = deqr(a, b) == 0; }
  else if (op == __OP_JLEQ__) { t = leqr(a, b); }
  else if (op == __OP_JLNE__) { t = leqr(a, b) == 0; }
  else {
    c = dcmp(a, b);
    if (op == __OP_JLT__) { t = c == 0 - 1; }
    if (op == __OP_JGT__) { t = c == 1; }
    if (op == __OP_JLE__) { t = (c == 0 - 1) + (c == 0); }
    if (op == __OP_JGE__) { t = (c == 0) + (c == 1); }
    if (op == __OP_JNLT__) { t = c != 0 - 1; }
    if (op == __OP_JNGT__) { t = c != 1; }
    if (op == __OP_JNLE__) { t = (c != 0 - 1) * (c != 0); }
    if (op == __OP_JNGE__) { t = (c != 0) * (c != 1); }
  }
  if (t) { poke(f, peek(f) - r / 2 + w0 % 8192); }      // (a return word holds the address / 2, as a jump's target)
  return 0;
}
// s[k]: a one-character string, or undefined past the end
function charat(s, k) {
  var r = 0;
  if (k < 0) { return __UNDEF__; }
  if (k >= peek(s - 1)) { return __UNDEF__; }
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
// x[k] = v outside the length (SETX stores inside it): the array grows to k + 1, any gap filled with undefined
function aset(x, k, v) {
  var n = peek(x - 1); var p = 0;
  if (k < 0) { return 0; }
  if (k < n) { p = peek(x); p[k] = v; return 0; }
  if (k >= peek(x - 2)) { grow(x, k + 1); }
  p = peek(x);
  __mfill(p + n, __UNDEF__, k - n);
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
  if (__kind(x, __K_ARR__) == 0) { return __UNDEF__; }
  if (n == 0) { return __UNDEF__; }
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
  if (__kind(sep, __K_AO__)) { sep = tostr(sep); }
  if (sep != 0) { ls = clen(sep); }
  while (i < n) {
    e = peek(peek(t) + i);
    if (__kind(e, __K_AO__) + __kind(e, __K_SPECIAL__) + __kind(e, __K_DBL__)) {
      if (t == x) { t = newarr(n, n); __mcpy(peek(t), peek(x), n); }
      if ((e == __NULL__) + (e == __UNDEF__)) { e = __S_EMPTY__; } else { e = tostr(e); }
      poke(peek(t) + i, e);
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
// (a key other than a string or an integer is its string: o[[1]] is o["1"], o[true] o["true"]; an array's or a string's
// index given as a string is that number: a["0"] is a[0])
function xkey(x, k) {
  if (__kind(k, __K_AO__) + __kind(k, __K_SPECIAL__) + __kind(k, __K_DBL__)) { k = tostr(k); }
  if (__kind(k, __K_STR__)) {
    if (__kind(x, __K_STR__) + __kind(x, __K_ARR__)) { k = strnum(k); }
    else if (__kind(x, __K_OBJ__)) { k = canint(k); }
  }
  return k;
}
// a string that is an integer's canonical form ("7", "-3"; not "07", "+3" or "-0") of the machine's range: that integer
// (an object's key "1" is its key 1); anything else as it is
function canint(s) {
  var n = peek(s - 1); var i = 0; var c = 0; var neg = 0; var v = 0;
  if (n == 0) { return s; }
  if (peek(s) == 45) { neg = 1; i = 1; }
  if ((i == n) + (n - i > 6)) { return s; }
  if ((peek(s + i) == 48) * ((n - i > 1) + neg)) { return s; }
  while (i < n) {
    c = peek(s + i);
    if ((c < 48) + (c > 57) + (v > 26214)) { return s; }
    v = v * 10 + c - 48; i++;
  }
  if (neg) { v = 0 - v; }
  if (__kind(v, __K_SMI__)) { return v; }
  return s;
}
function getx(x, k) {
  k = xkey(x, k);
  if (__kind(x, __K_STR__)) { return charat(x, k); }
  if (__kind(x, __K_ARR__)) {
    if (__kind(k, __K_SMI__)) { if ((k >= 0) * (k < peek(x - 1))) { return peek(peek(x) + k); } }
    return __UNDEF__;
  }
  if (__kind(x, __K_OBJ__)) { return pget(x, okey(x, k, 0) + __STRTAG__); }
  return __UNDEF__;
}
function setx(x, k, v) {
  k = xkey(x, k);
  if (__kind(x, __K_ARR__)) { if (__kind(k, __K_SMI__)) { aset(x, k, v); } return 0; }
  if (__kind(x, __K_OBJ__)) { pset(x, okey(x, k, 1) + __STRTAG__, v); }
  return 0;
}
// for (k in o): an array of o's keys as strings, an object's (its integer keys ascending, then its names in insertion order),
// an array's or a string's indexes. The keys are counted first, so the array is made before anything can move the chunks.
// (The loop's index is this frame's argument, o: keys leaves it 0, cc_ref.forof_end)
function keys(o) { var r = keyarr(o); o = 0; return r; }
function keyarr(o) {
  var r = 0; var n = 0; var m = 0; var i = 0; var j = 0; var t = 0; var p = 0; var go = 0;
  if (__kind(o, __K_OBJ__)) {
    n = okeyn(o, 0, 0); m = okeyn(o, 1, 0);
    r = newarr(n + m, n + m);
    okeyn(o, 0, peek(r)); okeyn(o, 1, peek(r) + n);
    p = peek(r); i = 1;
    while (i < n) {                                     // the integer keys ascending (insertion sort; nothing allocates)
      t = p[i]; j = i - 1; go = 1;
      while (go) { go = 0; if (j >= 0) { if (p[j] > t) { p[j + 1] = p[j]; j = j - 1; go = 1; } } }
      p[j + 1] = t; i++;
    }
    i = 0;
    while (i < n) { t = tostr(peek(peek(r) + i)); p = peek(r); p[i] = t; i++; }
    return r;
  }
  n = 0;
  if (__kind(o, __K_ARR__) + __kind(o, __K_STR__)) { n = peek(o - 1); }
  r = newarr(n, n); __mfill(peek(r), 0, n);
  while (i < n) { t = tostr(i); p = peek(r); p[i] = t; i++; }
  return r;
}
// o's keys of kind pass (0 integers, 1 names) -> their count; d: where to write them (0: count only)
function okeyn(o, pass, d) {
  var c = o + __OBJTAG__; var k = 0; var n = 0; var go = 1;
  while (go) {
    k = peek(c);
    if (k == 0) { go = 0; }
    else if (k < 0) { c = k + __OBJTAG__; }
    else {
      if (__kind(k - __STRTAG__, __K_STR__) == pass) { if (d) { poke(d + n, k - __STRTAG__); } n++; }
      c = c + 2;
    }
  }
  return n;
}
// o's value for key (undefined if it has none)
function pget(o, key) {
  var c = o + __OBJTAG__; var k = 0;
  while (1) {
    k = peek(c);
    if (k == key) { return peek(c + 1); }
    if (k == 0) { return __UNDEF__; }
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
function eqv(a, b) { return deqr(a, b); }    // a === b (strings by their characters)
// the first index i >= from (step 1) or <= from (step -1) where t occurs in s (a string) or equals an element (===); -1.
// Forwards, MFEQ finds the next element that is the same word as t, a line per execution: t's equal elements are the ones
// that are the same word unless t is a string or a number compared by value (a double, 0 and -0, NaN)
function find(x, t, from, step) {
  var n = peek(x - 1); var m = 0; var p = 0;
  if (__kind(x, __K_ARR__)) {
    p = peek(x);
    if ((__kind(t, __K_STR__) + __kind(t, __K_DBL__) + (t == 0) + (t == __MZERO__) + (t == __NAN__)) == 0) {
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
function includes(x, t) {
  if (t == __NAN__) { if (__kind(x, __K_ARR__)) { return jsb(__mfeq(peek(x), t, peek(x - 1)) < peek(x - 1)); } }   // (SameValueZero)
  return jsb(find(x, t, 0, 1) >= 0);
}
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
// x.splice(s, d, items...): the d elements from s (s < 0 counts from the end) removed and returned in a new array, the n
// items (at p, in the frame of splice0 ... splice8, one per argument count) put in their place
function splicen(x, s, d, p, n) {
  var len = 0; var r = 0; var q = 0; var i = 0;
  if (__kind(x, __K_ARR__) == 0) { return __UNDEF__; }
  len = peek(x - 1);
  if (__kind(s, __K_SMI__) == 0) { s = 0; }
  if (__kind(d, __K_SMI__) == 0) { d = 0; }
  s = cidx(s, len); if (d < 0) { d = 0; } if (d > len - s) { d = len - s; }
  r = newarr(d, d); __mcpy(peek(r), peek(x) + s, d);
  if (len - d + n > peek(x - 2)) { grow(x, len - d + n); }
  q = peek(x);
  if (n < d) { __mcpy(q + s + n, q + s + d, len - s - d); }
  i = len - 1;
  if (n > d) { while (i >= s + d) { q[i + n - d] = q[i]; i = i - 1; } }
  i = 0;
  while (i < n) { q[s + i] = peek(p + i); i++; }
  poke(x - 1, len - d + n);
  return r;
}
function splice0(x) { return splicen(x, 0, 0, 0, 0); }
function splice1(x, s) { return splicen(x, s, peek(x - 1), 0, 0); }
function splice2(x, s, d) { return splicen(x, s, d, 0, 0); }
function splice3(x, s, d, a) { return splicen(x, s, d, __fp() + 4, 1); }
function splice4(x, s, d, a, b) { return splicen(x, s, d, __fp() + 4, 2); }
function splice5(x, s, d, a, b, c) { return splicen(x, s, d, __fp() + 4, 3); }
function splice6(x, s, d, a, b, c, e) { return splicen(x, s, d, __fp() + 4, 4); }
function splice7(x, s, d, a, b, c, e, f) { return splicen(x, s, d, __fp() + 4, 5); }
function splice8(x, s, d, a, b, c, e, f, g) { return splicen(x, s, d, __fp() + 4, 6); }
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
  if (__kind(x, __K_ARR__) == 0) { return __UNDEF__; }
  if (n == 0) { return __UNDEF__; }
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
function charat1(s, k) { var r = charat(s, k); if (r == __UNDEF__) { r = __S_EMPTY__; } return r; }
function charcode(s, k) {
  if (__kind(s, __K_STR__) == 0) { return __NAN__; } if (k < 0) { return __NAN__; } if (k >= peek(s - 1)) { return __NAN__; }
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
  if (__kind(s, __K_STR__) * __kind(t, __K_STR__) == 0) { return __FALSE__; } if (peek(t - 1) > peek(s - 1)) { return __FALSE__; }
  return jsb(__mcmp(s, t, peek(t - 1)) == peek(t - 1));
}
function endswith(s, t) {
  var k = peek(s - 1) - peek(t - 1);
  if (__kind(s, __K_STR__) * __kind(t, __K_STR__) == 0) { return __FALSE__; } if (k < 0) { return __FALSE__; }
  return jsb(__mcmp(s + k, t, peek(t - 1)) == peek(t - 1));
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
function tostring(d, v) { return tostr(v); }
function tostring0(v) { return tostr(v); }
// Number(x): x as a number (tonum); parseInt(s): the decimal integer s's string starts with (after blanks, a sign), NaN if none;
// parseFloat(s): the decimal literal it starts with
function number(d, x) { return tonum(x); }
function parseint(d, s) {
  var n = 0; var i = 0; var j = 0; var c = 0; var go = 1; var any = 0;
  s = tostr(s); n = peek(s - 1); i = skipbl(s, 0, n); j = i;
  if (j < n) { c = peek(s + j); if ((c == 45) + (c == 43)) { j++; } }
  while (go) { go = 0; if (j < n) { c = peek(s + j); if ((c >= 48) * (c <= 57)) { j++; go = 1; any = 1; } } }
  if (any == 0) { return __NAN__; }
  return numscan(s, i, j);
}
function parsefloat(d, s) {
  var n = 0; var i = 0; var r = 0;
  s = tostr(s); n = peek(s - 1); i = skipbl(s, 0, n);
  r = numscan(s, i, n);
  if (peek(__NEND__) == i) { return __NAN__; }
  return r;
}

// ---------------- console.log of an array or object (PRINT traps into pval): Node's one-line form [ 1, 'a', [ 2 ] ],
// { k: 1, 'a b': [] }; below depth 2 [Array] / [Object]. fl: PRINT's flags, its separator * 2 + boolean; no separator: a
// piece of a + chain, printed as its string
// PRINT of an array or an object (cc_ref.TRAPS): pstub's TENTER made this frame at the PRINT's fp + TRAPOFF; its flags (A) and
// value (operand B) are decoded from the PRINT instruction, at the return address - 2
function ptrap() {
  var f = __fp(); var r = 2 * (peek(f) % 8192); var cf = f - __TRAPOFF__; var w1 = peek(r - 1); var c = (w1 % 1024 + 1024) % 1024;
  var b = (w1 - c) / 1024 + 512; var v = b - 896;
  if (b >= 1016) { v = b - 1016 + __SPV0__; }
  if (b < 256) { v = peek(__DB__ + b); }
  else if (b < 768) { v = peek(cf + b - 256); }
  pval(v, peek(r - 2) % 8192);
  return 0;
}
// PRINT's trap for an array or an object (fl: 2 * the separator + 8 if it is a piece of a + chain, which prints as a string)
function pval(v, fl) {
  var sp = (fl / 2) % 4;
  if (fl / 8 + (sp == 0)) { prn(tostr(v)); } else { ins(v, 0); }
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
  if (__kind(v, __K_DBL__)) { prn(numstr(v)); return 0; }
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
// ---------------- the network (net/device.py has the protocol). netw(p) sends payload p as NET's word 2 p + s, s a sequence
// bit the lib alternates (the cell NETSEQ), so on the page consecutive words always differ; p = 4 arg + op (op 0 URL bytes,
// 1 GET, 2 READ). NET returns part 0's answer, and leaves every part's bytes in RBUF0 … (-1: none). URL bytes go two per
// word; RLEFT counts the buffer's bytes not read yet (0: refill). fetch(url) / read() are called like parseInt (cc_ref
// GLOBALS): d is a dummy.
function netw(p) { var s = 1 - peek(__NETSEQ__); poke(__NETSEQ__, s); return __net(2 * p + s); }
function fetch(d, u) {
  var p = 0; var c = 0; var c2 = 0; var r = 0;
  if (__kind(u, __K_STR__) == 0) { u = tostr(u); }
  poke(__RLEFT__, 0);
  p = u; c = peek(p);
  while (c) {
    c2 = peek(p + 1);
    if (netw(4 * (c + 256 * c2)) < 0) { return 0 - 1; }     // (a URL word answers 0; -1: no gateway, give up)
    if (c2) { p = p + 2; c = peek(p); } else { c = 0; }
  }
  r = netw(1);
  if (r < 1) { return 0 - 1; }
  return r - 1;
}
function read(d) {
  var r = peek(__RLEFT__); var b = 0;
  if (r) {
    b = peek(__RBUF0__ + __NBUF__ - r);
    if (b < 0) { return 0 - 1; }                 // (the body ended in this buffer: -1 from now on)
    poke(__RLEFT__, r - 1); return b;
  }
  if (netw(2) < 0) { return 0 - 1; }
  r = peek(__RBUF0__);
  if (r < 0) { return 0 - 1; }
  poke(__RLEFT__, __NBUF__ - 1); return r;
}
