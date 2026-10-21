"""device.py — the network gateway's protocol, word by word: what the NET instruction returns (the model's side).

NET pops a word x and gets the gateway's answers, one per modem part (P = layout.json net_parts). Part j's answer d
unpacks into bytes 2j, 2j + 1 of the runtime cells RBUF0 … RBUF(2P-1): byte k is (d >> 8k) & 255 if d >> 16 > k, else
-1; part 0's whole answer replaces x on the stack (cc_ref.netw; machine/gen_css.py; net/server.js answers the same on
the page). x = 2 p + s: s is a sequence bit the lib alternates, p = 4 arg + op (the op low: a GET or a READ makes the
modems short, which the page relays out every word; only URL words make them tall):

  op 0, arg = b0 + 256 b1   append URL byte b0 (1 … 255), then b1 unless it is 0               -> 0 (every part)
  op 1                      GET the URL, forget it, keep the body: part 0 answers the HTTP status + 1 (> 511
                            reads 511; 0 if the request failed), the other parts 0
  op 2                      the body's next 2 P bytes: part j answers bytes 2j and 2j + 1 as b0 + 256 b1 + 65536 n,
                            n of them there (0 … 2; 0 past the body's end, and before any GET)

Answers are below 2^18 (and 196,607 at most, under 10^6: the page reads them through var()). The lib's fetch / read
(compiler/lib_src.js) are made of these. The tests' gateway serves files from tests/net/ instead of the network: a URL
is a path under it (one leading `/` is dropped), 200 if the file exists, else 404; any other URL (`http:`…, `..`) fails.
net/shim.js gives Node (the oracle) fetch / read that agree.
"""
import os, json

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'net')
PARTS = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler', 'layout.json')))['net_parts']
URL, GET, READ = 0, 1, 2


def payload(x): return (x >> 1) % (1 << 18)


class Device:
    def __init__(self, root=ROOT, parts=PARTS):
        self.root, self.parts, self.url, self.body, self.pos = root, parts, [], b'', 0

    def get(self, url):
        p = url[1:] if url.startswith('/') else url
        if ':' in p or '..' in p.split('/') or not p: return -1, b''
        f = os.path.join(self.root, p)
        if not os.path.isfile(f): return 404, b''
        return 200, open(f, 'rb').read()

    def __call__(self, x):
        """the answers to word x, one per part"""
        p = payload(x); op, arg = p & 3, p >> 2; z = [0] * self.parts
        if op == URL:
            self.url += [b for b in (arg & 255, arg >> 8) if b]
            return z
        if op == GET:
            st, self.body = self.get(bytes(self.url).decode('latin-1')); self.url, self.pos = [], 0
            return [min(511, st) + 1 if st >= 0 else 0] + z[1:]
        if op == READ:
            out = []
            for j in range(self.parts):
                bs = self.body[self.pos + 2 * j:min(len(self.body), self.pos + 2 * j + 2)]
                out.append((bs[0] if bs else 0) + 256 * (bs[1] if len(bs) > 1 else 0) + 65536 * len(bs))
            self.pos = min(len(self.body), self.pos + 2 * self.parts)
            return out
        return z
