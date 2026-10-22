// runid.js [profile|-] [script|VAR]... — print what a check depends on outside the repo: the Node and Python versions,
// for a browser profile (browser.js) the Playwright package version and the Chromium executable and version it
// launches (for `firefox` and `webkit`, the browser css-physics/tools/lib/physics.js launches with BROWSER=…), then the value of each environment variable named, or read by name in a script given (process.env.X,
// envArgs('X'), os.environ['X'], os.environ.get('X')). shared/make/checks.mk keeps this output in a file it
// rewrites only when it changes, so a check's result goes out of date when any of it does (harness only).
const path = require('path'), fs = require('fs'), { execFileSync } = require('child_process');
const { profile, PROFILES, IMAGE_CHROME } = require('./browser.js');
const [name = '-', ...rest] = process.argv.slice(2);
const READ = /process\.env\.([A-Z_][A-Z0-9_]*)|envArgs\('([A-Z_][A-Z0-9_]*)'|environ(?:\.get\(|\[)'([A-Z_][A-Z0-9_]*)'/g;
const vars = [...new Set(rest.flatMap(a => fs.existsSync(a) && fs.statSync(a).isFile()
  ? [...fs.readFileSync(a, 'utf8').matchAll(READ)].map(m => m[1] || m[2] || m[3]) : [a]))].sort();
const run = (f, a) => { try { return execFileSync(f, a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { return 'none'; } };

(async () => {
  const out = [`node ${process.version}`, `python ${run('python3', ['-VV']).replace(/\n/g, ' ')}`];
  if (name === 'firefox') {           // as physics.js picks it: FIREFOX, Playwright's own, else the image's newest
    const from = { paths: [process.cwd(), path.join(__dirname, '..', '..', 'css-physics')] };
    const pw = require(require.resolve('playwright', from));
    let exe = process.env.FIREFOX || pw.firefox.executablePath();
    if (!fs.existsSync(exe)) exe = (fs.existsSync('/ms-playwright') ? fs.readdirSync('/ms-playwright') : []).filter(d => /^firefox-\d+$/.test(d))
      .sort((a, b) => b.split('-')[1] - a.split('-')[1]).map(d => `/ms-playwright/${d}/firefox/firefox`).find(f => fs.existsSync(f)) || 'none';
    out.push(`playwright ${require(require.resolve('playwright/package.json', from)).version}`, `browser ${exe} ${run(exe, ['--version'])}`);
  } else if (name === 'webkit') {     // as physics.js picks it: WEBKIT, Playwright's own, else the image's newest
    const from = { paths: [process.cwd(), path.join(__dirname, '..', '..', 'css-physics')] };
    const pw = require(require.resolve('playwright', from));
    let exe = process.env.WEBKIT || pw.webkit.executablePath();
    if (!fs.existsSync(exe)) exe = (fs.existsSync('/ms-playwright') ? fs.readdirSync('/ms-playwright') : []).filter(d => /^webkit-\d+$/.test(d))
      .sort((a, b) => b.split('-')[1] - a.split('-')[1]).map(d => `/ms-playwright/${d}/pw_run.sh`).find(f => fs.existsSync(f)) || 'none';
    const mb = path.join(path.dirname(exe), 'minibrowser-wpe', 'MiniBrowser');   // pw_run.sh has no --version (Linux builds)
    out.push(`playwright ${require(require.resolve('playwright/package.json', from)).version}`, `browser ${exe} ${run(fs.existsSync(mb) ? mb : exe, ['--version'])}`);
  } else if (name !== '-') {
    const B = profile(name), P = PROFILES[name];
    const pkg = require.resolve(`${P.pkg}/package.json`, { paths: [process.cwd(), path.join(__dirname, '..', '..', P.home)] });
    let exe = await B.executablePath();
    if (!exe) { exe = B.chromium.executablePath(); if (!fs.existsSync(exe)) exe = IMAGE_CHROME; }    // as launch() falls back
    out.push(`${P.pkg} ${require(pkg).version}`, `browser ${fs.realpathSync(exe)} ${run(exe, ['--version'])}`);
  }
  for (const v of vars) out.push(`${v}=${process.env[v] ?? ''}`);
  console.log(out.join('\n'));
})();
