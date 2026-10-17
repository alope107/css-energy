#!/usr/bin/env python3
"""Build the dictionary-RAM self-test site for Cloudflare Pages. No JavaScript in the pages.

Builds selftest/site/. Deploy that folder as-is (it includes _headers and _redirects).
Open the site in Chrome, wait a few seconds, reload once, then read the lights.

Tests
  A  dcz + Use-As-Dictionary pass through at all          (plain files, literal match)
  B  :placeholder substitution inside a header value      (plain files, match="/t1/:k/r/*")
  C  _headers apply to the REQUEST path of a 200 rewrite  (/t2/:k/... -> /shared/...)
     + namespaces stay separate (cell b was never written, its probe must not decode)
  D  Vary: * survives, so a reused write URL re-registers  (4-page click-through)

Each test is a row of probe images whose decoded widths are chosen so the row's total width
says which ones decoded. A container query turns that width into PASS / FAIL text.

usage: python3 build.py     (pip install zstandard)
"""
import os, struct, zlib, hashlib
import zstandard

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")


def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def png(w, h=1, text=b""):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    if text:
        out += chunk(b"tEXt", b"k\x00" + text)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def dcz(dictionary, data):
    zd = zstandard.ZstdCompressionDict(dictionary, dict_type=zstandard.DICT_TYPE_RAWCONTENT)
    return (b"\x5e\x2a\x4d\x18\x20\x00\x00\x00" + hashlib.sha256(dictionary).digest()
            + zstandard.ZstdCompressor(dict_data=zd).compress(data))


def put(path, data):
    path = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb" if isinstance(data, bytes) else "w").write(data)


def dictionary(tag):
    # a dictionary must be a valid image: the decoder cancels an invalid load before Chrome stores it
    return png(1, 1, b"selftest dictionary " + tag + b" " + hashlib.sha256(tag).hexdigest().encode())


# ---------------------------------------------------------------- data files
put("ctl.png", png(1))                                         # plain control image, 1px wide

dA = dictionary(b"A"); put("t0/d.png", dA); put("t0/r/p.png", dcz(dA, png(10)))

dB = dictionary(b"B"); put("t1/a/d.png", dB); put("t1/a/r/p.png", dcz(dB, png(10)))

dC = dictionary(b"C"); put("shared/d.png", dC)
put("shared/r10.png", dcz(dC, png(10)))                        # probed as cell a (written)
put("shared/r20.png", dcz(dC, png(20)))                        # probed as cell b (never written)

d0, d1 = dictionary(b"V0"), dictionary(b"V1")
put("v/d0.png", d0); put("v/d1.png", d1)
put("v/r/r0.png", dcz(d0, png(10))); put("v/r/r1.png", dcz(d1, png(20)))

DICT = """  Use-As-Dictionary: match="{m}"
  Cache-Control: public, max-age=31536000
  Vary: *
"""
PROBE = """  Content-Encoding: dcz
  Cache-Control: no-store
  Vary: accept-encoding, available-dictionary
"""
# No catch-all rules: Cloudflare joins repeated headers with commas, and
# "public, max-age=31536000, no-cache" would stop a dictionary registering.
put("_headers",
    "/t0/d.png\n" + DICT.format(m="/t0/r/*") +
    "/t0/r/*\n" + PROBE +
    "/t1/:k/d.png\n" + DICT.format(m="/t1/:k/r/*") +
    "/t1/:k/r/*\n" + PROBE +
    "/t2/:k/d.png\n" + DICT.format(m="/t2/:k/r/*") +
    "/t2/:k/r/*\n" + PROBE +
    "/v/d*\n" + DICT.format(m="/v/r/*") +
    "/v/r/*\n" + PROBE)
put("_redirects", "/t2/:k/d.png /shared/d.png 200\n/t2/:k/r/:f /shared/:f 200\n")

# ---------------------------------------------------------------- pages
CSS = """
:root{--bg:#f4f1ea;--ink:#1b1a17;--mute:#77716a;--line:#dcd6ca;--ok:#2f7a4f;--bad:#c8372d;--wait:#a8a39a}
@media (prefers-color-scheme:dark){:root{--bg:#121110;--ink:#ece7dc;--mute:#8c857a;--line:#2b2925;--ok:#5cc28a;--bad:#ff6b5e;--wait:#5b5853}}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font:14px/1.55 ui-monospace,"SF Mono",Menlo,Consolas,monospace;padding:32px 16px}
main{max-width:720px;margin:0 auto}
h1{font-size:13px;letter-spacing:.14em;text-transform:uppercase;margin:0 0 6px}
.lede{color:var(--mute);margin:0 0 24px}
.t{display:grid;grid-template-columns:96px 1fr;gap:4px 16px;padding:16px 0;border-top:1px solid var(--line);
  position:relative;anchor-scope:--row}
.t:last-of-type{border-bottom:1px solid var(--line)}
.t h2{grid-column:2;font-size:14px;margin:0}
.t p{grid-column:2;margin:0;color:var(--mute);font-size:13px}
/* probes: decoded widths add up; a failed or pending probe is 0 wide */
.row{position:absolute;left:0;top:0;display:flex;anchor-name:--row;opacity:0;pointer-events:none}
.row i{display:block;flex:none}
.light{grid-row:1/span 3;height:28px}
.v{position:absolute;left:0;top:16px;height:28px;width:anchor-size(--row width);container-type:inline-size}
.v b{position:absolute;left:0;top:0;width:96px;height:28px;box-sizing:border-box;border-radius:4px;
  display:grid;place-items:center;font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--bg);background:var(--wait)}
.v b::after{content:"WAIT"}
a{color:inherit}
ol{margin:24px 0 0;padding-left:20px;color:var(--mute);font-size:13px}
.w{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
"""


def test(tid, title, body, probes, outcomes):
    row = "".join(f'<i style="content:url({u})"></i>' for u in probes)
    css = "".join(f"@container (width:{w}px){{#{tid} .v b{{background:var(--{'ok' if ok else 'bad'})}}"
                  f"#{tid} .v b::after{{content:\"{label}\"}}}}" for w, (ok, label) in outcomes.items())
    return (f'<style>{css}</style><section class=t id={tid}><span class=row>{row}</span>'
            f'<div class=light><div class=v><b></b></div></div><h2>{title}</h2>{body}</section>')


index = f"""<!doctype html>
<html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Dictionary RAM Self-Test</title>
<!-- No JavaScript. See build.py for what each test means. -->
<style>{CSS}</style>
<main>
<h1>Dictionary RAM self-test</h1>
<p class=lede>Chrome only. Load this page, wait a few seconds, then <b>reload once</b>: the first load
writes the dictionaries, the reload reads them. WAIT means a probe never decoded.</p>
<i class=w style="mask-image:url(/t0/d.png)"></i>
<i class=w style="mask-image:url(/t1/a/d.png)"></i>
<i class=w style="mask-image:url(/t2/a/d.png)"></i>
{test("ta", "A · dcz decoding works on this host",
      "<p>A dictionary with a literal match pattern, and a probe compressed against it. NO DCZ is normal on the "
      "first load. Still NO DCZ after a reload means the host "
      "strips <code>Use-As-Dictionary</code> or <code>Content-Encoding: dcz</code> (e.g. Cloudflare's Shared "
      "dictionaries setting is not on passthrough). Nothing else can work.</p>",
      ["/ctl.png", "/t0/r/p.png"],
      {1: (False, "NO DCZ"), 11: (True, "PASS")})}
{test("tb", "B · placeholders in header values",
      "<p>The dictionary's match pattern is <code>/t1/:k/r/*</code>, filled in from its own path.</p>",
      ["/t1/a/r/p.png"],
      {10: (True, "PASS")})}
{test("tc", "C · headers follow the request path of a 200 rewrite",
      "<p>Dictionary and probes live in <code>/shared/</code> but are requested as <code>/t2/a/…</code> and "
      "<code>/t2/b/…</code>. PASS: cell a decodes, never-written cell b does not. LEAK: both decode, so the "
      "namespaces collapsed. FAIL/WAIT: the rewrite lost the headers; you would need one file per cell and value.</p>",
      ["/t2/a/r/r10.png", "/t2/b/r/r20.png"],
      {10: (True, "PASS"), 20: (False, "LEAK"), 30: (False, "LEAK")})}
<section class=t><div class=light></div><h2>D · Vary: * survives</h2>
<p>A reused write URL must still re-register a dictionary, which needs <code>Vary: *</code> to reach Chrome.
This one takes four pages: <a href="/chain/1">start the chain</a>, and click "next" on each, waiting a
second on each page.</p></section>
<ol><li>Run it on <code>*.pages.dev</code> and on your custom domain; compare.</li>
<li>Run it in a fresh profile (or Incognito) to rule out dictionaries left over from an earlier run.</li></ol>
</main></html>
"""
put("index.html", index)

chain = [("/v/d0.png", "writes value 0"), ("/v/d1.png", "writes value 1"),
         ("/v/d0.png", "writes value 0 again, through the same URL as page 1")]
for i, (u, what) in enumerate(chain, 1):
    put(f"chain/{i}.html", f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Dictionary RAM Self-Test · {i}/4</title>
<style>{CSS}</style><i class=w style="mask-image:url({u})"></i>
<main><h1>Test D · page {i} of 4</h1><p class=lede>This page {what}. Wait a second, then
<a href="/chain/{i + 1}">next →</a></p></main></html>""")
put("chain/4.html", f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Dictionary RAM Self-Test · 4/4</title>
<style>{CSS}</style><main><h1>Test D · result</h1>
<p class=lede>The stored value should be 0, written last by page 3.</p>
{test("td", "D · Vary: * survives",
      "<p>PASS: page 3's reused URL re-registered value 0. STALE: value 1 is still stored, so page 3's write "
      "came from Chrome's memory cache; the host dropped or changed <code>Vary: *</code>. "
      "Writes in your app must then never reuse a URL in one tab.</p>",
      ["/v/r/r0.png?d", "/v/r/r1.png?d"],
      {10: (True, "PASS"), 20: (False, "STALE"), 30: (False, "BOTH?")})}
<p><a href="/">← back to the tests</a></p></main></html>""")
print("built", OUT)
