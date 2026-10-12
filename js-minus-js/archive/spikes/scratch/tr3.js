// trace.js image.json — replay the CSS VM's exact semantics (copied from build.js run()) and measure
// how far a HarfBuzz-hosted core could run between traps back to CSS.
//
// Model: the font holds the ROM (pc < 4096) plus an N-cell fully associative LRU cache of RAM, as glyph
// state. A read of a non-resident cell is a trap (CSS reads memory, feeds it back). A write allocates in
// the cache without a trap; evicting a dirty cell needs a CSS write, which rides along with the next trap
// (one write-back per trap; a backlog forces extra traps). PUTC and HALT always trap. Instruction fetches
// from RAM (the compiled user program) go through the same cache. Optionally, RAM cells that are never
// written during the whole run are baked into the font as constants ("ro").
const fs = require("fs");
const image = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const ROM = 4096, MEM = ROM + image.ramSize, OUT_COLS = image.cols, OUT_SIZE = image.rows * image.cols;

function run(onRead, onWrite, onStep) {
  const mem = new Int32Array(MEM); mem.set(image.rom, 0); mem.set(image.ram, ROM);
  let pc = 0, sp = image.sp0, fp = image.sp0, optr = 0;
  const M = a => (onRead(a), mem[a]), W = (a, v) => { onWrite(a); mem[a] = v; };
  const tdiv = (a, b) => b === 0 ? 0 : Math.trunc(a / b), tmod = (a, b) => b === 0 ? 0 : a % b;
  for (;;) {
    const w = M(pc), op = Math.floor(w / 8192), imm = w % 8192, simm = imm >= 4096 ? imm - 8192 : imm;
    onStep(pc, op);
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
        W(sp - 1, [a + b, a - b, a * b, tdiv(a, b), tmod(a, b), +(a < b), +(a > b), +(a <= b), +(a >= b), +(a === b), +(a !== b), +(a !== 0 && b !== 0), +(a !== 0 || b !== 0)][op - 8]); break; }
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
      case 31: { const c = M(--sp); if (c !== 10) { optr = (optr + 1) % OUT_SIZE; } break; }   // output cell write is CSS's job (always a trap)
      case 32: return;
      case 33: pc = M(--sp); break;
      case 34: W(sp - 1, M(sp - 1) * 8192); break;
      case 35: W(imm, M(imm) + 1); break;
      case 36: W(fp + simm, M(fp + simm) + 1); break;
      case 37: W(sp - 1, M(M(imm) + M(sp - 1))); break;
      case 38: W(sp - 1, M(M(fp + simm) + M(sp - 1))); break;
      default: throw new Error("bad op " + op);
    }
  }
}

module.exports={run};