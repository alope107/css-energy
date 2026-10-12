// build.js — bootstrap: run jsc.js under Node to compile jsc.js itself into ROM words, lay out the
// memory image (compiler data, demo source, user data, user code buffer, stack, output), then run
// the whole thing on a bytecode simulator as a check. Usage: node build.js demo.js image.json
const fs = require("fs"), vm = require("vm");

const ROM = 4096, RAM = 3072, MEM = ROM + RAM, OUT_ROWS = 16, OUT_COLS = 8, OUT_SIZE = OUT_ROWS * OUT_COLS;
const OUT_BASE = MEM - OUT_SIZE;
const [demoPath, outPath] = process.argv.slice(2);
const jscSource = fs.readFileSync(__dirname + "/jsc.js", "utf8");
const demoSource = fs.readFileSync(demoPath, "utf8");

// string literals become char-code arrays so the compiler's own s[i] comparisons work under Node
const nodeSource = jscSource.replace(/"([^"\\]*)"/g, (_, s) => "[" + [...s].map(c => c.charCodeAt(0)).concat([0]).join(",") + "]");

const ram = new Int32Array(MEM);
class Done extends Error {}
function makeEnv(src) {
  const env = {
    src: [...src].map(c => c.charCodeAt(0)).concat([0]), srcLen: src.length, codeBase: 0, dataPtr: ROM, printFn: 0, putsFn: 0,
    alloc: n => new Array(n).fill(0), putc: c => process.stdout.write(String.fromCharCode(c)),
    peek: a => ram[a], poke: (a, v) => { ram[a] = v; },
    exec: () => { throw new Done(); }, halt: () => { throw new Error("halt"); },
  };
  return env;
}

// ---- self-compile (or, with --direct, compile the demo straight into ROM to test the VM alone)
const direct = process.argv.includes('--direct');
const libSource = jscSource.slice(jscSource.indexOf('// --lib-start'), jscSource.indexOf('// --lib-end'));
const env = makeEnv(direct ? libSource + '\n' + demoSource : jscSource);
try { vm.runInNewContext(nodeSource, env); } catch (e) { if (!(e instanceof Done)) throw e; }
const romLen = env.cp, dataEnd = env.dataPtr;
if (romLen > ROM) throw new Error("ROM overflow " + romLen);
const names = {};
for (let i = 0; i < env.nsym; i++) {
  const name = env.src.slice(env.symStart[i], env.symStart[i] + env.symLen[i]).map(c => String.fromCharCode(c)).join("");
  if (env.symScope[i] === 0) names[name] = { kind: env.symKind[i], addr: env.symAddr[i] };
}
const g = n => { if (!names[n]) throw new Error("no symbol " + n); return names[n].addr; };

// ---- memory layout after the compiler's own data
const SRC_BASE = dataEnd;
const USER_DATA = SRC_BASE + demoSource.length + 8;
const CODE_BASE = USER_DATA + 256;
const STACK_BASE = CODE_BASE + 500;
if (STACK_BASE + 300 > OUT_BASE) throw new Error("layout does not fit: dataEnd=" + dataEnd);
for (let i = 0; i < demoSource.length; i++) ram[SRC_BASE + i] = demoSource.charCodeAt(i);
if (!direct) { ram[g("src")] = SRC_BASE; ram[g("srcLen")] = demoSource.length; ram[g("codeBase")] = CODE_BASE;
ram[g("dataPtr")] = USER_DATA; ram[g("printFn")] = g("print"); ram[g("putsFn")] = g("puts"); }
const image = { rom: Array.from(ram.slice(0, romLen)), ram: Array.from(ram.slice(ROM, MEM)), ramSize: RAM, sp0: STACK_BASE, outBase: OUT_BASE, rows: OUT_ROWS, cols: OUT_COLS,
                srcBase: SRC_BASE, srcLen: demoSource.length, codeBase: CODE_BASE, userData: USER_DATA };

// ---- simulator: exactly the CSS machine's semantics
function run(image, maxSteps = 5e6) {
  const mem = new Int32Array(MEM); mem.set(image.rom, 0); mem.set(image.ram, ROM);
  let pc = 0, sp = image.sp0, fp = image.sp0, optr = 0, steps = 0, out = [];
  const M = a => mem[a], W = (a, v) => { mem[a] = v; };
  const tdiv = (a, b) => b === 0 ? 0 : Math.trunc(a / b), tmod = (a, b) => b === 0 ? 0 : a % b;
  for (;;) {
    if (++steps > maxSteps) throw new Error("step limit");
    const w = mem[pc], op = Math.floor(w / 8192), imm = w % 8192, simm = imm >= 4096 ? imm - 8192 : imm;
    let a, b; pc++;
    switch (op) {
      case 0: break;
      case 1: W(sp++, imm); break;
      case 2: W(sp++, M(imm)); break;
      case 3: W(imm, M(--sp)); break;
      case 4: W(sp++, M(fp + simm)); break;
      case 5: W(fp + simm, M(--sp)); break;
      case 6: a = M(sp - 1); W(sp - 1, M(a)); break;
      case 7: b = M(--sp); a = M(--sp); W(a, b); break;
      case 8: case 9: case 10: case 11: case 12: case 13: case 14: case 15: case 16: case 17: case 18: case 19: case 20: {
        b = M(--sp); a = M(sp - 1);
        const r = [a + b, a - b, a * b, tdiv(a, b), tmod(a, b), +(a < b), +(a > b), +(a <= b), +(a >= b), +(a === b), +(a !== b), +(a !== 0 && b !== 0), +(a !== 0 || b !== 0)][op - 8];
        W(sp - 1, r); break; }
      case 21: W(sp - 1, +(M(sp - 1) === 0)); break;
      case 22: W(sp - 1, -M(sp - 1)); break;
      case 23: pc = imm; break;
      case 24: if (M(--sp) === 0) pc = imm; break;
      case 25: if (M(--sp) !== 0) pc = imm; break;
      case 26: W(sp++, pc); pc = imm; break;
      case 27: W(sp, fp); fp = sp; sp = sp + 1 + imm; break;
      case 28: { const v = M(sp - 1), oldfp = M(fp), ret = M(fp - 1), nsp = fp - 1 - imm; W(nsp, v); sp = nsp + 1; fp = oldfp; pc = ret; break; }
      case 29: sp--; break;
      case 30: W(sp, M(sp - 1)); sp++; break;
      case 31: { const c = M(--sp); if (c === 10) optr = (Math.floor(optr / OUT_COLS) + 1) * OUT_COLS % OUT_SIZE; else { W(OUT_BASE + optr, c); optr = (optr + 1) % OUT_SIZE; } out.push(c); break; }
      case 32: return { steps, out: String.fromCharCode(...out), mem };
      case 33: pc = M(--sp); break;
      case 34: W(sp - 1, M(sp - 1) * 8192); break;
      case 35: W(imm, M(imm) + 1); break;
      case 36: W(fp + simm, M(fp + simm) + 1); break;
      case 37: W(sp - 1, M(M(imm) + M(sp - 1))); break;
      case 38: W(sp - 1, M(M(fp + simm) + M(sp - 1))); break;
      default: throw new Error("bad op " + op + " at " + (pc - 1));
    }
  }
}
const r = run(image);
// profile: steps per ROM function (by address range, from the symbol table)
if (process.argv.includes("--profile")) {
  const funcs = Object.entries(names).filter(([, s]) => s.kind === 3).map(([n, s]) => [n, s.addr]).sort((a, b) => a[1] - b[1]);
  const hist = {}; const mem = new Int32Array(MEM); mem.set(image.rom, 0); mem.set(image.ram, ROM);
  let pc = 0, sp = image.sp0, fp = image.sp0, optr = 0, steps = 0;
  const which = a => { let f = "top"; for (const [n, ad] of funcs) { if (ad <= a) f = n; } return a >= ROM ? "user" : f; };
  // re-run with a lightweight copy of the loop
  const tdiv = (a, b) => b === 0 ? 0 : Math.trunc(a / b), tmod = (a, b) => b === 0 ? 0 : a % b;
  const M = a => mem[a], W = (a, v) => { mem[a] = v; };
  for (;;) {
    const w = mem[pc], op = Math.floor(w / 8192), imm = w % 8192, simm = imm >= 4096 ? imm - 8192 : imm;
    hist[which(pc)] = (hist[which(pc)] || 0) + 1; steps++;
    let a, b2; pc++;
    switch (op) {
      case 0: break; case 1: W(sp++, imm); break; case 2: W(sp++, M(imm)); break; case 3: W(imm, M(--sp)); break;
      case 4: W(sp++, M(fp + simm)); break; case 5: W(fp + simm, M(--sp)); break; case 6: a = M(sp - 1); W(sp - 1, M(a)); break;
      case 7: b2 = M(--sp); a = M(--sp); W(a, b2); break;
      case 8: case 9: case 10: case 11: case 12: case 13: case 14: case 15: case 16: case 17: case 18: case 19: case 20: {
        b2 = M(--sp); a = M(sp - 1);
        W(sp - 1, [a + b2, a - b2, a * b2, tdiv(a, b2), tmod(a, b2), +(a < b2), +(a > b2), +(a <= b2), +(a >= b2), +(a === b2), +(a !== b2), +(a !== 0 && b2 !== 0), +(a !== 0 || b2 !== 0)][op - 8]); break; }
      case 21: W(sp - 1, +(M(sp - 1) === 0)); break; case 22: W(sp - 1, -M(sp - 1)); break; case 23: pc = imm; break;
      case 24: if (M(--sp) === 0) pc = imm; break; case 25: if (M(--sp) !== 0) pc = imm; break; case 26: W(sp++, pc); pc = imm; break;
      case 27: W(sp, fp); fp = sp; sp = sp + 1 + imm; break;
      case 28: { const v = M(sp - 1), oldfp = M(fp), ret = M(fp - 1), nsp = fp - 1 - imm; W(nsp, v); sp = nsp + 1; fp = oldfp; pc = ret; break; }
      case 29: sp--; break; case 30: W(sp, M(sp - 1)); sp++; break; case 31: --sp; break; case 33: pc = M(--sp); break; case 34: W(sp - 1, M(sp - 1) * 8192); break;
      case 35: W(imm, M(imm) + 1); break; case 36: W(fp + simm, M(fp + simm) + 1); break; case 37: W(sp - 1, M(M(imm) + M(sp - 1))); break; case 38: W(sp - 1, M(M(fp + simm) + M(sp - 1))); break;
      case 32: pc = -1; break;
    }
    if (pc < 0) break;
  }
  console.log(Object.entries(hist).sort((a, b) => b[1] - a[1]).map(([n, c]) => `${n}:${c}`).join("  "));
}
console.log(`ROM ${romLen} words, compiler data ${dataEnd - ROM} words, src at ${SRC_BASE}, user data ${USER_DATA}, code ${CODE_BASE}, stack ${STACK_BASE}`);
console.log(`simulated: ${r.steps} steps, output:\n${r.out}`);
image.steps = r.steps; image.expected = r.out; image.source = demoSource; image.direct = direct; image.romWords = romLen;
fs.writeFileSync(outPath, JSON.stringify(image));
