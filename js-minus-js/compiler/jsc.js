// jsc.js — a compiler for a small subset of JavaScript, written in that subset, targeting the CSS stack VM.
//
// Subset: var, function (params, recursion), if/else, while, for(;;), return, integers, string
// literals (as NUL-terminated char arrays), array literals (static), a[i] read/write, + - * / %,
// comparisons, && || ! (no short circuit), calls, console.log(number | "string").
// Environment globals (set by whoever runs it): src (char array / address), srcLen, codeBase,
// dataPtr, and the addresses of print and puts. Builtins: putc, peek, poke, alloc, exec, halt.
//
// Word = op * 8192 + imm.  Opcodes:
var OP_NOP = 0; var OP_PUSHI = 1; var OP_LOADG = 2; var OP_STOREG = 3; var OP_LOADL = 4; var OP_STOREL = 5;
var OP_LOADI = 6; var OP_STOREI = 7; var OP_ADD = 8; var OP_SUB = 9; var OP_MUL = 10; var OP_DIV = 11;
var OP_MOD = 12; var OP_LT = 13; var OP_GT = 14; var OP_LE = 15; var OP_GE = 16; var OP_EQ = 17; var OP_NE = 18;
var OP_AND = 19; var OP_OR = 20; var OP_NOT = 21; var OP_NEG = 22; var OP_JMP = 23; var OP_JZ = 24;
var OP_JNZ = 25; var OP_CALL = 26; var OP_ENTER = 27; var OP_RET = 28; var OP_POP = 29; var OP_DUP = 30;
var OP_PUTC = 31; var OP_HALT = 32; var OP_JMPI = 33; var OP_SHL13 = 34; var OP_INCG = 35; var OP_INCL = 36; var OP_IDX = 37; var OP_IDXL = 38; var OP_PRINT = 39;

var src; var srcLen; var codeBase; var dataPtr; var printFn; var putsFn;

// ---------------- tokenizer
var T_EOF = 0; var T_NUM = 1; var T_ID = 2; var T_STR = 3; var T_P = 4;
var pos = 0; var tok = 0; var tokVal = 0; var tokStart = 0; var tokLen = 0;

// character classes: 1 alpha, 3 digit (odd = identifier char), 4 space
var ctype = [0,0,0,0,0,0,0,0,0,4,4,0,0,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,3,3,3,3,3,3,3,3,3,3,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,1,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0];
var tokHash = 0;
var H_VAR = 1845; var H_IF = 3357; var H_ELSE = 3765; var H_WHILE = 289; var H_FOR = 3285; var H_RETURN = 8147; var H_FUNCTION = 4077; var H_PUTC = 4313; var H_PEEK = 4862; var H_POKE = 6461; var H_ALLOC = 3971; var H_EXEC = 6670; var H_HALT = 455; var H_CONSOLE = 4188; var H_PRINT = 1452; var H_PUTS = 4329; var H_PRN = 4793; var H_FP = 527; var H_OP = 806;

function next() {
  var c = src[pos]; var t = ctype[c]; var d = 0;
  while (t == 4) { pos++; c = src[pos]; t = ctype[c]; }
  if (c == 47) {
    while (c == 47 && src[pos + 1] == 47) {         // // comment
      while (c != 10 && c != 0) { pos++; c = src[pos]; }
      t = ctype[c];
      while (t == 4) { pos++; c = src[pos]; t = ctype[c]; }
    }
  }
  if (c == 0) { tok = T_EOF; return 0; }
  if (t == 3) {
    tokVal = 0;
    while (t == 3) { tokVal = tokVal * 10 + (c - 48); pos++; c = src[pos]; t = ctype[c]; }
    tok = T_NUM; return 0;
  }
  if (t == 1) {
    tokStart = pos; tokHash = 0;
    while (t % 2) { tokHash = (tokHash * 31 + c) % 8191; pos++; c = src[pos]; t = ctype[c]; }
    tokLen = pos - tokStart; tok = T_ID; return 0;
  }
  if (c == 34) {                       // "string"
    pos++; tokStart = pos;
    while (src[pos] != 34) { pos++; }
    tokLen = pos - tokStart; pos++; tok = T_STR; return 0;
  }
  tok = T_P; tokVal = c; pos++;
  d = src[pos];
  if (d == 61) {                                                                                 // == != <= >=  -> 1 2 3 4
    if (c == 61) { tokVal = 1; pos++; } else if (c == 33) { tokVal = 2; pos++; } else if (c == 60) { tokVal = 3; pos++; } else if (c == 62) { tokVal = 4; pos++; }
  }
  else if (d == c) {                                                                             // && || ++ --  -> 5 6 7 8
    if (c == 38) { tokVal = 5; pos++; } else if (c == 124) { tokVal = 6; pos++; } else if (c == 43) { tokVal = 7; pos++; } else if (c == 45) { tokVal = 8; pos++; }
  }
  return 0;
}

// does the current identifier token equal the NUL-terminated string s?
function isKw(h) { return tok == T_ID && tokHash == h; }
function isP(c) { return tok == T_P && tokVal == c; }
function expectP(c) { if (!isP(c)) { fail(1000 + c); } next(); return 0; }
function fail(code) { putc(69); putc(82); putc(82); putc(32); printNum(code); putc(32); printNum(pos); halt(); return 0; }

// ---------------- symbols
var MAXSYM = 256;
var symStart = alloc(256); var symLen = alloc(256); var symKind = alloc(256); var symAddr = alloc(256);
var symScope = alloc(256); var nsym = 0;
var K_GLOBAL = 1; var K_LOCAL = 2; var K_FUNC = 3;
var curFunc = 0;      // 0 at top level, else 1
var nlocals = 0;      // locals allocated in the current function
var nparams = 0;

function symEq(i, start, len) {
  if (symLen[i] != len) { return 0; }
  var k = 0;
  while (k < len) { if (src[symStart[i] + k] != src[start + k]) { return 0; } k++; }
  return 1;
}
function lookup(start, len) {
  var i = nsym - 1;
  while (i >= 0) { if (symEq(i, start, len) && (symScope[i] == 0 || symScope[i] == curFunc)) { return i; } i = i - 1; }
  return -1;
}
function declare(start, len, kind, addr) {
  if (nsym >= MAXSYM) { fail(2); }
  symStart[nsym] = start; symLen[nsym] = len; symKind[nsym] = kind; symAddr[nsym] = addr;
  symScope[nsym] = curFunc; nsym++;
  return nsym - 1;
}

// ---------------- code emission (into RAM at codeBase)
var cp = 0;
function emit(op, imm) { if (imm < 0) { imm = imm + 8192; } poke(codeBase + cp, op * 8192 + imm); cp++; return cp - 1; }
function patch(at, op, imm) { if (imm < 0) { imm = imm + 8192; } poke(codeBase + at, op * 8192 + imm); return 0; }
function here() { return codeBase + cp; }

// forward references to functions: fixups by name, patched at the end
var fixAt = alloc(512); var fixStart = alloc(512); var fixLen = alloc(512); var nfix = 0;
function emitCall(sym) {
  if (symAddr[sym] >= 0) { emit(OP_CALL, symAddr[sym]); }
  else { emitFix(symStart[sym], symLen[sym]); }
  return 0;
}
function emitFix(start, len) {
  if (nfix >= 512) { fail(11); }
  fixAt[nfix] = cp; fixStart[nfix] = start; fixLen[nfix] = len; nfix++; emit(OP_CALL, 0);
  return 0;
}

// ---------------- expressions
function parsePrimary() {
  var i = 0; var n = 0; var start = 0; var addr = 0; var s = 0; var h = 0;
  if (tok == T_NUM) {
    n = tokVal; next();
    if (n < 8192) { emit(OP_PUSHI, n); } else { emit(OP_PUSHI, (n - n % 8192) / 8192); emit(OP_SHL13, 0); emit(OP_PUSHI, n % 8192); emit(OP_ADD, 0); }
    return 0;
  }
  if (tok == T_STR) {                            // static NUL-terminated char array
    addr = dataPtr; i = 0;
    while (i < tokLen) {
      s = src[tokStart + i];
      if (s == 92) { i++; s = src[tokStart + i]; if (s == 110) { s = 10; } }   // \n
      poke(dataPtr, s); dataPtr++; i++;
    }
    poke(dataPtr, 0); dataPtr++;
    next(); emit(OP_PUSHI, addr); return 0;
  }
  if (isP(91)) {                                  // [1, 2, 3] static array of numbers
    next(); addr = dataPtr;
    while (!isP(93)) {
      n = 1; if (isP(45)) { next(); n = -1; }
      poke(dataPtr, n * tokVal); dataPtr++; next();
      if (isP(44)) { next(); }
    }
    next(); emit(OP_PUSHI, addr); return 0;
  }
  if (isP(40)) { next(); parseExpr(); expectP(41); return 0; }
  if (isP(33)) { next(); parseUnary(); emit(OP_NOT, 0); return 0; }
  if (isP(45)) { next(); parseUnary(); emit(OP_NEG, 0); return 0; }
  if (tok != T_ID) { fail(3); }
  start = tokStart; n = tokLen; h = tokHash; next();
  // builtins (identifier hash first, the string compare only confirms)
  if (isP(40)) {
    if (h == H_PUTC) { if (identIs(start, n, "putc")) { next(); parseExpr(); expectP(41); emit(OP_PUTC, 0); emit(OP_PUSHI, 0); return 0; } }
    if (h == H_PRN) { if (identIs(start, n, "prn")) { next(); parseExpr(); expectP(41); emit(OP_PRINT, 0); emit(OP_PUSHI, 0); return 0; } }   // the machine's PRINT (no separator)
    if (h == H_PEEK) { if (identIs(start, n, "peek")) { next(); parseExpr(); expectP(41); emit(OP_LOADI, 0); return 0; } }
    if (h == H_POKE) { if (identIs(start, n, "poke")) { next(); parseExpr(); expectP(44); parseExpr(); expectP(41); emit(OP_STOREI, 0); emit(OP_PUSHI, 0); return 0; } }
    if (h == H_ALLOC) { if (identIs(start, n, "alloc")) { next(); addr = dataPtr; dataPtr = dataPtr + tokVal; next(); expectP(41); emit(OP_PUSHI, addr); return 0; } }
    if (h == H_EXEC) { if (identIs(start, n, "exec")) { next(); parseExpr(); expectP(41); emit(OP_JMPI, 0); emit(OP_PUSHI, 0); return 0; } }
    if (h == H_HALT) { if (identIs(start, n, "halt")) { next(); expectP(41); emit(OP_HALT, 0); emit(OP_PUSHI, 0); return 0; } }
    // __fp(): the word at fp (in a function: its caller's fp). __op(W, e, ...): the operands, then the instruction word W itself
    if (h == H_FP) { if (identIs(start, n, "__fp")) { next(); expectP(41); emit(OP_LOADL, 0); return 0; } }
    if (h == H_OP) { if (identIs(start, n, "__op")) { next(); addr = tokVal; next(); while (isP(44)) { next(); parseExpr(); } expectP(41); poke(codeBase + cp, addr); cp++; return 0; } }
  }
  if (h == H_CONSOLE) {                         // console.log(x) -> print or puts
    expectP(46); next();                        // .log
    expectP(40);
    if (tok == T_STR) { parseExpr(); if (putsFn) { emit(OP_CALL, putsFn); } else { emitCall(findSym("puts")); } }
    else { parseExpr(); if (printFn) { emit(OP_CALL, printFn); } else { emitCall(findSym("print")); } }
    expectP(41); return 0;
  }
  i = lookup(start, n);
  if (i < 0 && !isP(40)) { fail(4); }
  if (isP(40)) {                                // call (a name not yet defined is a forward call, fixed up at the end)
    next(); addr = 0;
    while (!isP(41)) { parseExpr(); addr++; if (isP(44)) { next(); } }
    next();
    if (i < 0) { emitFix(start, n); } else { emitCall(i); }
    return 0;
  }
  if (isP(91)) {                                // a[e]: index through the variable holding the array's address
    next(); parseExpr(); expectP(93);
    if (symKind[i] == K_LOCAL) { emit(OP_IDXL, symAddr[i]); } else { emit(OP_IDX, symAddr[i]); }
    return 0;
  }
  if (symKind[i] == K_LOCAL) { emit(OP_LOADL, symAddr[i]); } else { emit(OP_LOADG, symAddr[i]); }
  return 0;
}
function findSym(s) {                        // symbol whose name equals the literal s (used when no patched address exists)
  var i = 0; var k = 0; var ok = 0;
  while (i < nsym) {
    ok = 1; k = 0;
    while (k < symLen[i]) { if (s[k] != src[symStart[i] + k]) { ok = 0; } k++; }
    if (ok && s[k] == 0 && symKind[i] == K_FUNC) { return i; }
    i++;
  }
  fail(10); return 0;
}
function identIs(start, len, s) {
  var i = 0;
  while (i < len) { if (s[i] != src[start + i]) { return 0; } i++; }
  return s[i] == 0;
}
function parseUnary() { return parsePrimary(); }
// binary operators: precedence table indexed by tokVal (0 = not a binary operator) and the opcode to emit
var binPrec = alloc(64); var binOp = alloc(64);
function setBin(c, p, op) { binPrec[c] = p; binOp[c] = op; return 0; }
setBin(42, 6, OP_MUL); setBin(47, 6, OP_DIV); setBin(37, 6, OP_MOD);
setBin(43, 5, OP_ADD); setBin(45, 5, OP_SUB);
setBin(60, 4, OP_LT); setBin(62, 4, OP_GT); setBin(3, 4, OP_LE); setBin(4, 4, OP_GE);
setBin(1, 3, OP_EQ); setBin(2, 3, OP_NE);
setBin(5, 2, OP_AND); setBin(6, 1, OP_OR);
function parseBin(minPrec) {
  var p = 0; var c = 0;
  parseUnary();
  p = 0; if (tok == T_P) { p = binPrec[tokVal]; }
  while (p >= minPrec && p > 0) {
    c = tokVal; next();
    parseBin(p + 1);
    emit(binOp[c], 0);
    p = 0; if (tok == T_P) { p = binPrec[tokVal]; }
  }
  return 0;
}
function parseExpr() { return parseBin(1); }

// ---------------- statements
function storeSym(i) { if (symKind[i] == K_LOCAL) { emit(OP_STOREL, symAddr[i]); } else { emit(OP_STOREG, symAddr[i]); } return 0; }

function parseAssignOrCall() {              // NAME = e | NAME[e] = e | NAME++ | NAME-- | call
  var start = tokStart; var n = tokLen; var i = 0; var save = pos; var saveTok = tok; var saveVal = tokVal;
  next();
  if (isP(61)) {
    next(); i = lookup(start, n); if (i < 0) { fail(5); }
    parseExpr(); storeSym(i); return 0;
  }
  if (isP(7)) {                            // i++
    i = lookup(start, n); if (i < 0) { fail(6); }
    if (symKind[i] == K_LOCAL) { emit(OP_INCL, symAddr[i]); } else { emit(OP_INCG, symAddr[i]); }
    next(); return 0;
  }
  if (isP(8)) {                            // i--
    i = lookup(start, n); if (i < 0) { fail(6); }
    if (symKind[i] == K_LOCAL) { emit(OP_LOADL, symAddr[i]); } else { emit(OP_LOADG, symAddr[i]); }
    emit(OP_PUSHI, 1); emit(OP_SUB, 0);
    next(); storeSym(i); return 0;
  }
  if (isP(91)) {                             // a[e] = e
    i = lookup(start, n); if (i < 0) { fail(7); }
    if (symKind[i] == K_LOCAL) { emit(OP_LOADL, symAddr[i]); } else { emit(OP_LOADG, symAddr[i]); }
    next(); parseExpr(); expectP(93); emit(OP_ADD, 0);
    expectP(61); parseExpr(); emit(OP_STOREI, 0); return 0;
  }
  // otherwise an expression statement: rewind and parse as expression, drop the value
  pos = save; tok = saveTok; tokVal = saveVal; tokStart = start; tokLen = n;
  parseExpr();
  if (peek(codeBase + cp - 1) == OP_PUSHI * 8192) { cp = cp - 1; } else { emit(OP_POP, 0); }   // a builtin's dummy 0, dropped
  return 0;
}

function parseBlock() { expectP(123); while (!isP(125)) { parseStatement(); } next(); return 0; }

function parseStatement() {
  var i = 0; var j = 0; var a = 0; var b = 0; var c = 0;
  if (tok != T_ID) { if (isP(123)) { parseBlock(); return 0; } fail(8); }
  if (tokHash == H_VAR) {
    next(); i = declareVar(); if (isP(61)) { next(); parseExpr(); storeSym(i); } expectP(59); return 0;
  }
  if (tokHash == H_IF) {
    next(); expectP(40); parseExpr(); expectP(41);
    a = emit(OP_JZ, 0); parseBlock();
    if (isKw(H_ELSE)) {
      next(); b = emit(OP_JMP, 0); patch(a, OP_JZ, here());
      if (isKw(H_IF)) { parseStatement(); } else { parseBlock(); }
      patch(b, OP_JMP, here());
    } else { patch(a, OP_JZ, here()); }
    return 0;
  }
  if (tokHash == H_WHILE) {
    next(); a = here(); expectP(40); parseExpr(); expectP(41);
    b = emit(OP_JZ, 0); parseBlock(); emit(OP_JMP, a); patch(b, OP_JZ, here()); return 0;
  }
  if (tokHash == H_FOR) {                          // for (init; cond; step) body
    next(); expectP(40);
    if (isKw(H_VAR)) { next(); i = declareVar(); if (isP(61)) { next(); parseExpr(); storeSym(i); } } else if (!isP(59)) { parseAssignOrCall(); }
    expectP(59);
    a = here();                               // L1: cond
    if (isP(59)) { emit(OP_PUSHI, 1); } else { parseExpr(); }
    expectP(59);
    b = emit(OP_JZ, 0);                       // -> END
    c = emit(OP_JMP, 0);                      // -> BODY
    j = here();                               // L2: step; JMP L1
    if (!isP(41)) { parseAssignOrCall(); }
    expectP(41);
    emit(OP_JMP, a);
    patch(c, OP_JMP, here());                 // BODY: block; JMP L2
    parseBlock();
    emit(OP_JMP, j);
    patch(b, OP_JZ, here());
    return 0;
  }
  if (tokHash == H_RETURN) {
    next();
    if (isP(59)) { emit(OP_PUSHI, 0); } else { parseExpr(); }
    expectP(59); emit(OP_RET, nparams); return 0;
  }
  parseAssignOrCall(); expectP(59); return 0;
}

function declareVar() {
  var i = 0;
  if (tok != T_ID) { fail(9); }
  if (curFunc) { nlocals++; i = declare(tokStart, tokLen, K_LOCAL, nlocals); }
  else { i = declare(tokStart, tokLen, K_GLOBAL, dataPtr); dataPtr++; }
  next(); return i;
}

var scopeCounter = 0;
function parseFunction() {                  // function NAME(params) block
  var i = 0; var enterAt = 0; var start = 0; var n = 0; var savedNsym = 0;
  next(); start = tokStart; n = tokLen;
  i = declare(start, n, K_FUNC, here()); next();
  savedNsym = nsym;
  scopeCounter++; curFunc = scopeCounter; nlocals = 0; nparams = 0;
  expectP(40);
  while (!isP(41)) { nparams++; if (isP(44)) { next(); } declare(tokStart, tokLen, K_LOCAL, 0); next(); }
  next();
  // params live below fp: param k of n sits at fp - 1 - n + k
  var k = 0; while (k < nparams) { symAddr[nsym - nparams + k] = 0 - 1 - nparams + k; k++; }
  enterAt = emit(OP_ENTER, 0);
  parseBlock();
  emit(OP_PUSHI, 0); emit(OP_RET, nparams);
  patch(enterAt, OP_ENTER, nlocals);
  curFunc = 0; nsym = savedNsym;
  return 0;
}

function compile() {                         // whole program: top-level code first, then a jump over the functions
  var i = 0; var j = 0; var over = 0;
  pos = 0; next();
  curFunc = 0;
  while (tok != T_EOF) {
    if (isKw(H_FUNCTION)) {
      over = emit(OP_JMP, 0); parseFunction(); patch(over, OP_JMP, here());
    } else { parseStatement(); }
  }
  emit(OP_HALT, 0);
  i = 0;
  while (i < nfix) {
    j = lookup(fixStart[i], fixLen[i]);
    if (j < 0) { fail(12); }
    patch(fixAt[i], OP_CALL, symAddr[j]); i++;
  }
  return 0;
}

// --lib-start   runtime library (compiled along with everything else; the compiler emits calls to these)
function printNum(n) {
  if (n < 0) { putc(45); n = 0 - n; }
  if (n >= 10) { printNum((n - n % 10) / 10); }
  putc(48 + n % 10);
  return 0;
}
function print(n) { printNum(n); putc(10); return 0; }
function puts(s) { var i = 0; while (s[i] != 0) { putc(s[i]); i++; } putc(10); return 0; }

// --lib-end
// ---------------- entry: compile the source in src, then run it
function main() {
  compile();
  exec(codeBase);
  return 0;
}
main();
