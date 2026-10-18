// lib.js — harness helpers for paint/tools (harness only: the pages never run script).
//
// Dictionaries need a real HTTP origin (localhost is a secure context) and a persistent profile (the
// tests restart the browser), so the tools start serve.js themselves and launch a persistent context.
// Launcher: shared/js/browser.js, profile `physics` (npm `playwright`, CHROME=/path, `--no-sandbox`).
const fs = require('fs'), os = require('os'), path = require('path'), net = require('net');
const { spawn } = require('child_process');
const B = require('../../shared/js/browser.js').profile('physics');

const PAINT = path.join(__dirname, '..');

const freePort = () => new Promise((ok, bad) => {
  const s = net.createServer().listen(0, 'localhost', () => { const { port } = s.address(); s.close(() => ok(port)); });
  s.on('error', bad);
});

// serve(siteDir, ...extra serve.js flags) -> { base, stop() }
async function serve(site, ...flags) {
  const port = await freePort();
  const proc = spawn(process.execPath, [path.join(PAINT, 'serve.js'), site, String(port), ...flags],
    { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((ok, bad) => {
    proc.stdout.once('data', ok);
    proc.once('exit', c => bad(new Error(`serve.js exited (${c})`)));
  });
  return { base: `http://localhost:${port}`, stop: () => proc.kill() };
}

// A persistent profile in a fresh temp dir; ctx() opens (or reopens, after close) a browser on it.
async function profileDir() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'paint-'));
  const ctx = async (opts = {}) => B.chromium.launchPersistentContext(dir, {
    executablePath: await B.executablePath(), args: B.args, headless: true, ...opts });
  return { dir, ctx, remove: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

module.exports = { PAINT, B, serve, profileDir, sleep };
