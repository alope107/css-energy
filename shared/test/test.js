// node shared/test/test.js — unit tests of the shared harness code (no browser; ~0.1 s). Exits 1 on a failure.
const assert = require('assert');
const path = require('path');
const R = path.join(__dirname, '..', '..');
const T = require('../js/trace.js');
const { pick, summarize } = require('../js/ab.js');
const Br = require('../js/browser.js');
const F = require('../js/freeze.js');
let n = 0, bad = 0;
const t = (name, f) => { n++; try { f(); } catch (e) { bad++; console.log(`FAIL ${name}: ${e.message}`); } };

// ---- trace.js
t('median is the upper median, 0 when empty', () => { assert.strictEqual(T.median([3, 1, 2, 4]), 3); assert.strictEqual(T.median([5]), 5); assert.strictEqual(T.median([]), 0); });
t('quantile', () => { assert.strictEqual(T.quantile([1, 2, 3, 4], 0.25), 2); assert.ok(Number.isNaN(T.quantile([], 0.5))); });
t('bigmed keeps passes over max(floor, 30% of the largest)', () => {
  assert.strictEqual(T.bigmed([0.5, 0.6, 10, 11, 12], 1), 11);
  assert.strictEqual(T.bigmed([0.2, 0.3], 1), 0);                 // nothing over the floor
  assert.strictEqual(T.bigmed([], 0.5), 0);
});
const X = (name, ts, dur, tid = 1) => ({ ph: 'X', name, ts, dur, tid });
const ev = [X('ThreadControllerImpl::RunTask', 0, 100000), X('UpdateLayoutTree', 10000, 30000), X('Inner', 20000, 10000),
  X('UpdateLayoutTree', 60000, 20000), { ph: 'I', name: 'UpdateLayoutTree', ts: 1 }, X('Other', 0, 500000, 2)];
t('durations: complete events only, in ms', () => assert.deepStrictEqual(T.durations(ev, 'UpdateLayoutTree'), [30, 20]));
t('aggregate: n, total, max per name; filter', () => {
  const a = T.aggregate(ev, e => e.tid === 1);
  assert.deepStrictEqual(a.UpdateLayoutTree, { n: 2, t: 50, max: 30 }); assert.ok(!a.Other);
});
t('selfTime: main thread by RunTask + Layout, nested durations subtracted, first-seen order', () => {
  const rows = T.selfTime(ev);
  assert.deepStrictEqual(rows.map(r => r[0]), ['ThreadControllerImpl::RunTask', 'UpdateLayoutTree', 'Inner']);
  const m = Object.fromEntries(rows.map(r => [r[0], r]));
  assert.deepStrictEqual(m.UpdateLayoutTree, ['UpdateLayoutTree', 50, 40, 2]);
  assert.deepStrictEqual(m['ThreadControllerImpl::RunTask'], ['ThreadControllerImpl::RunTask', 100, 50, 1]);
  assert.deepStrictEqual(m.Inner, ['Inner', 10, 10, 1]);
});
t('selfTime falls back to the busiest thread without RunTask', () => assert.strictEqual(T.selfTime([X('A', 0, 10, 7)])[0][0], 'A'));

// ---- ab.js
t('pick: JSON field first', () => assert.strictEqual(pick('load ms 300\n{"label":"x","haltMs":8512}\n', 'haltMs'), 8512));
t('pick: "name value" in text', () => assert.strictEqual(pick('out/a.html  med 6.39 bigmed 6.98 fps 55.3', 'bigmed'), 6.98));
t('pick: a name inside another is not matched', () => assert.strictEqual(pick('bigmed 6.98 med 5.1', 'med'), 5.1));
t('pick: name: value, name=value, exponents, negatives', () => {
  assert.strictEqual(pick('fps: 60', 'fps'), 60); assert.strictEqual(pick('x=-1.5e-3', 'x'), -0.0015);
});
t('pick: NaN when absent', () => assert.ok(Number.isNaN(pick('nothing here', 'bigmed'))));
t('summarize: ratio median and IQR', () => {
  const [a, b] = summarize(['a', 'b'], [[10, 10, 10, 10], [20, 22, 18, 21]], [[1, 1, 1, 1], [2, 2.2, 1.8, 2.1]]);
  assert.strictEqual(a.ratio, 1); assert.strictEqual(b.ratio, 2.1); assert.strictEqual(b.q25, 2); assert.strictEqual(b.q75, 2.2); assert.strictEqual(b.min, 18);
});

// ---- browser.js: the profiles must keep each project's documented flags
t('profile flags', () => {
  assert.deepStrictEqual(Br.PROFILES.physics.args, ['--no-sandbox']);
  assert.deepStrictEqual(Br.PROFILES.fontcpu.args, ['--no-sandbox', '--no-proxy-server', '--disable-gpu']);
  assert.throws(() => Br.profile('nope'));
});
t('fileUrl resolves against the cwd', () => assert.strictEqual(Br.fileUrl('a b.html'), require('url').pathToFileURL(path.resolve('a b.html')).href));
t('envArgs', () => { process.env.__T = '--a --b'; assert.deepStrictEqual(Br.envArgs('__T'), ['--a', '--b']); delete process.env.__T; assert.deepStrictEqual(Br.envArgs('__T'), []); });

// ---- freeze.js
t('wobble and constant declarations', () => {
  assert.strictEqual(F.wobble('X3', '12.5'), '--X3:calc(12.5 + 0.0000001 * sin(var(--now2) * 50));');
  assert.strictEqual(F.constant('SC3', '50'), '--SC3:50;');
  assert.ok(F.CLOCK_CSS.includes('@property --now2') && F.CLOCK_CSS.includes('@keyframes clk2'));
});

// ---- css-physics tools/lib/physics.js
const P = require(path.join(R, 'css-physics', 'tools', 'lib', 'physics.js'));
t('projector matches the tools\' inline proj()', () => {
  const ar = { x: 50, y: 30, width: 900, height: 600 };
  const [PERSP, TILT, TY, DIST, VW] = [1500, -28, 95, -260, 900], sc = ar.width / VW;
  const old = ([x, y, z], yaw = 0.25) => { const c = Math.cos(yaw), s = Math.sin(yaw), ct = Math.cos(TILT * Math.PI / 180), st_ = Math.sin(TILT * Math.PI / 180);
    const x1 = x * c + z * s, z1 = -x * s + z * c, y3 = y * ct - z1 * st_ + TY, z3 = y * st_ + z1 * ct - DIST, k = PERSP / (PERSP - z3); return [ar.x + ar.width / 2 + x1 * k * sc, ar.y + ar.height / 2 + y3 * k * sc]; };
  const proj = P.projector(ar);
  for (const pt of [[0, 0, 0], [70, -145, 10], [-60, -145, 0], [300, -20, -150]]) assert.deepStrictEqual(proj(pt), old(pt));
  assert.deepStrictEqual(proj([10, 20, 30], 1.1), old([10, 20, 30], 1.1));
});
t('bodyInfo', () => { assert.deepStrictEqual(P.bodyInfo('x<!--BODYINFO [{"k":"sph","r":20}]-->y'), [{ k: 'sph', r: 20 }]); assert.strictEqual(P.bodyInfo('none'), null); });
t('registerNames', () => assert.deepStrictEqual(P.registerNames('@keyframes q0{from{--X0:1}to{--X0:2}}@keyframes q1{from{--SC0:0}}'), ['X0', 'SC0']));

// ---- js-minus-js tools/page.js
const J = require(path.join(R, 'js-minus-js', 'tools', 'page.js'));
t('console grid', () => {
  const codes = [...'Fizz'].map(c => c.charCodeAt(0)).concat([0, 0, 0, 0], [...'12'].map(c => c.charCodeAt(0)), Array(6).fill(32), Array(112).fill(0));
  assert.deepStrictEqual(J.gridRows(codes).slice(0, 3), ['Fizz', '12', '']);
  assert.strictEqual(J.gridText(codes), 'Fizz\n12');
  assert.strictEqual(J.gridText([7, 65], 1, 2), ' A');      // non-printable shows as a space
});

console.log(`${n - bad}/${n} pass`);
process.exit(bad ? 1 : 0);
