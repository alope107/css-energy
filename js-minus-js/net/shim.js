// shim.js — fetch(url) and read() for programs run under Node (the oracle), synchronous and agreeing with
// net/device.py: a URL is a path under tests/net/ (one leading `/` dropped), 200 if the file exists, else 404; any
// other URL fails with -1. read() returns the body's next byte, -1 past its end.
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..', 'tests', 'net');
module.exports = (root = ROOT) => {
  let body = Buffer.alloc(0), pos = 0;
  const get = url => {
    const p = url.startsWith('/') ? url.slice(1) : url;
    if (!p || p.includes(':') || p.split('/').includes('..')) return [-1, Buffer.alloc(0)];
    const f = path.join(root, p);
    return fs.existsSync(f) && fs.statSync(f).isFile() ? [200, fs.readFileSync(f)] : [404, Buffer.alloc(0)];
  };
  return {
    fetch: url => { let st; [st, body] = get(String(url)); pos = 0; return Math.max(-512, Math.min(511, st)); },
    read: () => (pos < body.length ? body[pos++] : -1),
  };
};
