// libbuild.js out.json — compile the runtime library (lib_src.js: addc) into ROM with jsc itself,
// and end the ROM with a jump to the user code buffer instead of HALT.
const fs = require("fs"), vm = require("vm");
const jscSource = fs.readFileSync(__dirname + "/jsc.js", "utf8");
const nodeSource = jscSource.replace(/"([^"\\]*)"/g, (_, s) => "[" + [...s].map(c => c.charCodeAt(0)).concat([0]).join(",") + "]");
// startup: copy the compiler's initialised globals/arrays (staged at INIT, count at INIT - 1) into the data area
const INIT = 5120;
const lib = fs.readFileSync(__dirname + "/lib_src.js", "utf8") +
  `function __init() { var n = peek(${INIT - 1}); var i = 0; while (i < n) { poke(4096 + i, peek(${INIT} + i)); i++; } return 0; }\n__init();\n`;
const rom = new Int32Array(4096);
class Done extends Error {}
const env = { src: [...lib].map(c => c.charCodeAt(0)).concat([0]), srcLen: lib.length, codeBase: 0, dataPtr: 4096, printFn: 0, putsFn: 0,
  alloc: n => new Array(n).fill(0), putc: c => {}, peek: a => rom[a], poke: (a, v) => { if (a < 4096) rom[a] = v; },
  exec: () => { throw new Done(); }, halt: () => { throw new Error("halt"); } };
const main = nodeSource.replace(/function main\(\) \{\s*compile\(\);\s*exec\(codeBase\);\s*return 0;\s*\}\s*main\(\);/, "compile(); exec(0);");
try { vm.runInNewContext(main, env); } catch (e) { if (!(e instanceof Done)) throw e; }
const names = {};
for (let i = 0; i < env.nsym; i++) {
  const n = env.src.slice(env.symStart[i], env.symStart[i] + env.symLen[i]).map(c => String.fromCharCode(c)).join("");
  if (env.symKind[i] === 3) names[n] = env.symAddr[i];
}
const CODE_BASE = +process.argv[3] || 4608;
const len = env.cp; rom[len - 1] = 23 * 8192 + CODE_BASE;     // final HALT -> JMP user code
fs.writeFileSync(process.argv[2], JSON.stringify({ rom: Array.from(rom.slice(0, len)), addc: names.addc, codeBase: CODE_BASE, init: INIT }));
console.log("lib ROM", len, "words; addc", names.addc, "last word", rom[len - 1]);
