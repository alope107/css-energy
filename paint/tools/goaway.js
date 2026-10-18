// goaway.js — reads under connection churn: 480 random cells, then reloads, each checked after the retry (~3 min).
//
//   node tools/goaway.js [loads] [base]       (default 5 loads; base defaults to a local serve.js)
//
// Locally it serves site/ over HTTP/2 with `--goaway 10000`, as Cloudflare ends every connection after 10,000
// requests (GOAWAY=N: after N, to force connection ends inside every load), with a throwaway certificate trusted by
// SPKI (needs openssl). A base URL (https://…) runs it against a
// deployment instead. Per load it prints the cells the first pass lost, with the error of the probe that should
// have decoded, and the cells still wrong after the retry row. Exits non-zero if any cell is wrong after a retry.
const fs = require('fs'), os = require('os'), path = require('path'), net = require('net');
const { spawn, execSync } = require('child_process');
const { PAINT, B, profileDir, sleep } = require('./lib.js');

const HIT = 17;                                              // build.py: a probe that decodes is (v + HIT) x 1
const N = 480, LOADS = +(process.argv[2] || 5), BASE = process.argv[3];
let rnd = 7;
const rand = n => { rnd ^= rnd << 13; rnd >>>= 0; rnd ^= rnd >>> 17; rnd ^= rnd << 5; rnd >>>= 0; return rnd % n; };
const want = [...Array(N)].map(() => rand(16));

async function serveH2() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'paint-cert-'));
  const [cert, key] = [path.join(dir, 'cert.pem'), path.join(dir, 'key.pem')];
  execSync(`openssl req -x509 -newkey rsa:2048 -nodes -keyout ${key} -out ${cert} -days 2 -subj /CN=localhost ` +
    `-addext subjectAltName=DNS:localhost`, { stdio: 'ignore' });
  const spki = execSync(`openssl x509 -in ${cert} -pubkey -noout | openssl pkey -pubin -outform der | ` +
    `openssl dgst -sha256 -binary | base64`).toString().trim();
  const port = await new Promise(ok => { const s = net.createServer().listen(0, () => { const p = s.address().port; s.close(() => ok(p)); }); });
  const proc = spawn(process.execPath, [path.join(PAINT, 'serve.js'), path.join(PAINT, 'site'), String(port),
    '--cert', cert, '--key', key, '--goaway', String(process.env.GOAWAY || 10000)], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((ok, bad) => { proc.stdout.once('data', ok); proc.once('exit', c => bad(new Error(`serve.js exited (${c})`))); });
  return { base: `https://localhost:${port}`, args: [`--ignore-certificate-errors-spki-list=${spki}`],
    stop: () => { proc.kill(); fs.rmSync(dir, { recursive: true, force: true }); } };
}

(async () => {
  const srv = BASE ? { base: BASE.replace(/\/$/, ''), args: [], stop() {} } : await serveH2();
  const prof = await profileDir();
  let bad = 0;
  try {
    const ctx = await prof.ctx({ viewport: { width: 700, height: 760 }, args: [...B.args, ...srv.args] });
    const pg = ctx.pages()[0] || await ctx.newPage();

    // Write every cell from one document: a mask-image per cell registers its dictionary.
    await pg.goto(srv.base + '/c/0/x');
    let pending = N;
    const settle = r => { if (/\/d\//.test(r.url())) pending--; };
    pg.on('requestfinished', settle); pg.on('requestfailed', settle);
    await pg.evaluate(w => { document.body.innerHTML = w.map((v, k) =>
      `<i style="position:absolute;width:1px;height:1px;mask-image:url(/c/${k}/d/${v}.png)"></i>`).join(''); }, want);
    while (pending > 0) await sleep(250);
    pg.off('requestfinished', settle); pg.off('requestfailed', settle);
    await sleep(10000);                                      // 480 registrations take a few seconds to commit

    const cdp = await ctx.newCDPSession(pg);
    await cdp.send('Network.enable');
    for (let load = 0; load < LOADS; load++) {
      const kind = new Map(), fails = new Map(); let last = Date.now(), retries = 0;
      const on = (ev, f) => cdp.on('Network.' + ev, e => { last = Date.now(); f(e); });
      on('requestWillBeSent', e => { const u = e.request.url;
        if (/\/r\/2\//.test(u)) { kind.set(e.requestId, u); retries++; } else if (/\/r\//.test(u)) kind.set(e.requestId, u); });
      on('loadingFailed', e => { if (kind.has(e.requestId)) fails.set(kind.get(e.requestId), e.errorText); });
      on('loadingFinished', () => {});
      const t0 = Date.now();
      await pg.goto(srv.base + '/', { waitUntil: 'commit' });
      await sleep(5000);
      while (Date.now() - last < 8000 && Date.now() - t0 < 300000) await sleep(500);   // quiet: first pass and retry done
      // .v2 is the first pass's read (stages 1 and 2), .w the final one; a read is (value + HIT) px wide (build.py)
      const [rd, w] = await pg.evaluate(() => ['.v2', '.w'].map(s =>
        [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect().width)));
      const lost = [...Array(N).keys()].filter(k => rd[k] !== want[k] + HIT);
      const wrong = [...Array(N).keys()].filter(k => w[k] !== want[k] + HIT);
      bad += wrong.length;
      const why = {}; for (const k of lost) { const e = fails.get(`${srv.base}/c/${k}/r/${want[k]}.png`) || 'no CDP event';
        why[e] = (why[e] || 0) + 1; }
      console.log(`${wrong.length ? 'FAIL' : 'ok  '} load ${load}: ${((Date.now() - t0) / 1000).toFixed(0)} s, first pass lost ` +
        `${lost.length} ${JSON.stringify(why)}, retry probes ${retries}, wrong after retry ${wrong.length}` +
        (wrong.length ? ` (cells ${wrong.slice(0, 8).join(' ')})` : ''));
      for (const ev of ['requestWillBeSent', 'loadingFailed', 'loadingFinished']) cdp.removeAllListeners('Network.' + ev);
    }
    await ctx.close();
  } finally { srv.stop(); prof.remove(); }
  console.log(bad ? `${bad} cell read(s) wrong after the retry` : 'every load read every cell');
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
