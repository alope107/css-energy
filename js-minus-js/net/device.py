"""device.py — the network gateway's protocol, word by word: what the NET instruction returns (the model's side).

NET pops a word x and pushes the gateway's answer. Only x mod 4096 reaches the gateway (net/server.js); answers are
10-bit signed (-512 … 511). The runtime library (compiler/lib_src.js) builds fetch(url) and read() from it:

  256 + b   append byte b (1 … 255) to the URL                                    -> 0
  512       GET the URL, forget it, keep the body: the HTTP status (> 511 reads 511), -1 if the request failed
  768       the body's next byte, -1 past its end (and before any fetch)

The tests' gateway (Device) serves files from tests/net/ instead of the network: a URL is a path under it (one leading
`/` is dropped), 200 if the file exists, else 404; any other URL (`http:`…, `..`) fails with -1.
net/server.js answers the same words on the page, and net/shim.js gives Node (the oracle) fetch / read that agree.
"""
import os

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'net')
URLB, GO, READ = 256, 512, 768


def clamp(v): return max(-512, min(511, v))


class Device:
    def __init__(self, root=ROOT):
        self.root, self.url, self.body, self.pos = root, [], b'', 0

    def get(self, url):
        p = url[1:] if url.startswith('/') else url
        if ':' in p or '..' in p.split('/') or not p: return -1, b''
        f = os.path.join(self.root, p)
        if not os.path.isfile(f): return 404, b''
        return 200, open(f, 'rb').read()

    def __call__(self, x):
        p = x % 4096
        if URLB < p < GO: self.url.append(p - URLB); return 0
        if p == GO:
            st, self.body = self.get(bytes(self.url).decode('latin-1')); self.url, self.pos = [], 0
            return clamp(st)
        if p == READ:
            if self.pos >= len(self.body): return -1
            self.pos += 1; return self.body[self.pos - 1]
        return 0
