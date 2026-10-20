// libbuild.js out.json consts.json — compile the runtime library (lib_src.js) into ROM with jsc itself, and end the ROM with
// a jump to the user code buffer instead of HALT. consts.json (written by rtlib.py, which runs this) fills in lib_src.js's
// __NAME__ constants.
const fs = require("fs"), vm = require("vm");
const jscSource = fs.readFileSync(__dirname + "/jsc.js", "utf8");
const nodeSource = jscSource.replace(/"([^"\\]*)"/g, (_, s) => "[" + [...s].map(c => c.charCodeAt(0)).concat([0]).join(",") + "]");
// startup (the ROM's first words, so the jumps over the function bodies don't run): copy the compiler's initialised globals
// (staged at INIT, count at INIT - 1) into the data area, then jump to the program
const L = JSON.parse(fs.readFileSync(__dirname + "/layout.json", "utf8"));   // the memory map (cc_ref.LAYOUT reads the same file)
const INIT = L.init;
const K = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const lib = `__init(); exec(${L.code_base});\n` + fs.readFileSync(__dirname + "/lib_src.js", "utf8").replace(/__([A-Z][A-Z0-9_]*)__/g, (m, n) => {
  if (!(n in K)) throw new Error(`lib_src.js: no constant ${m}`); return String(K[n]); }) +
  `function __init() { var n = peek(${INIT - 1}); var i = 0; while (i < n) { poke(${L.data_base} + i, peek(${INIT} + i)); i++; } return 0; }\n`;
const rom = new Int32Array(L.rom_size);
class Done extends Error {}
const env = { src: [...lib].map(c => c.charCodeAt(0)).concat([0]), srcLen: lib.length, codeBase: 0, dataPtr: L.data_base, printFn: 0, putsFn: 0,
  alloc: n => new Array(n).fill(0), putc: c => {}, peek: a => rom[a], poke: (a, v) => { if (a < L.rom_size) rom[a] = v; },
  exec: () => { throw new Done(); }, halt: () => { throw new Error("halt"); } };
const main = nodeSource.replace(/function main\(\) \{\s*compile\(\);\s*exec\(codeBase\);\s*return 0;\s*\}\s*main\(\);/, "compile(); exec(0);");
try { vm.runInNewContext(main, env); } catch (e) { if (!(e instanceof Done)) throw e; }
const names = {};
for (let i = 0; i < env.nsym; i++) {
  const n = env.src.slice(env.symStart[i], env.symStart[i] + env.symLen[i]).map(c => String.fromCharCode(c)).join("");
  if (env.symKind[i] === 3) names[n] = env.symAddr[i];
}
const CODE_BASE = L.code_base;
const len = env.cp; rom[len - 1] = 23 * 8192 + CODE_BASE;     // final HALT -> JMP user code
if (len > L.rom_size) throw new Error(`lib is ${len} words, ROM holds ${L.rom_size}`);
fs.writeFileSync(process.argv[2], JSON.stringify({ rom: Array.from(rom.slice(0, len)), addc: names.addc, fns: names, codeBase: CODE_BASE, init: INIT, romSize: L.rom_size, dataBase: L.data_base }));
console.log("lib ROM", len, "words;", Object.keys(names).length, "functions; last word", rom[len - 1]);
