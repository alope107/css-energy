// Trap-rate model closer to a buildable font: ALU-heavy ops (MUL DIV MOD SHL13) and PUTC/HALT trap;
// constants = compiler static data never written (source text excluded: it is runtime input).
const fs = require('fs'); const image = JSON.parse(fs.readFileSync('image.json'));
let src = fs.readFileSync('trace.js','utf8').replace(/\/\/ pass 0[\s\S]*$/,'module.exports={run};');
fs.writeFileSync('/tmp/tr3.js', src); process.argv[2] = 'image.json';
const { run } = require('/tmp/tr3.js');
const ROM = 4096, written = new Uint8Array(ROM + image.ramSize);
run(() => {}, a => { written[a] = 1; }, () => {});
const isConst = a => a < ROM || (!written[a] && !(a >= image.srcBase && a < image.srcBase + image.srcLen));
function sim(N, policy, trapOps) {
  const lines = new Map(); let order = []; let traps = 0, steps = 0, rl = 0; const runs = [];
  let need = false, wbPending = 0;
  const access = (a, write) => {
    if (isConst(a)) return;
    if (lines.has(a)) { if (write) lines.set(a, true); if (policy === 'lru') { order.splice(order.indexOf(a), 1); order.push(a); } return; }
    if (!write) need = true;                       // read miss: trap (fill after)
    lines.set(a, write); order.push(a);
    if (lines.size > N) { const v = order.shift(); if (lines.get(v)) wbPending++; lines.delete(v); }
  };
  let last = -1;
  run(a => access(a, false), a => access(a, true), (pc, op) => {
    if (last >= 0) { steps++; rl++;
      if (need || trapOps.has(last) || wbPending > 0) { runs.push(rl); rl = 0; traps++; wbPending = Math.max(0, wbPending - 1); } }
    need = false; last = op; });
  runs.push(rl + 1);
  const s = [...runs].sort((x, y) => x - y);
  return `${(steps / runs.length).toFixed(1)} (median ${s[s.length >> 1]})`;
}
const T = new Set([10, 11, 12, 34, 31, 32]);
for (const N of [8, 16, 32, 64]) console.log(`N=${N}  LRU ${sim(N, 'lru', T)}   FIFO ${sim(N, 'fifo', T)}`);
