import sys, json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=['--no-proxy-server'])
    pg = b.new_page()
    pg.goto('http://127.0.0.1:9471/parent.xhtml', wait_until='networkidle'); pg.wait_for_timeout(500)
    print('browser', b.version)
    print('parent', pg.evaluate("[document.contentType, document.compatMode, document.documentElement.namespaceURI]"))
    for fid in ['oq','os','iq','dq']:
        r = pg.evaluate("""id => { const e=document.getElementById(id);
          let d; try { d = e.contentDocument; } catch(x) { return 'no access: '+x.message; }
          if (!d) return 'no contentDocument (opaque origin?)';
          const m=d.getElementById('m'); const cs=m&&d.defaultView.getComputedStyle(m);
          return {mode:d.compatMode, type:d.contentType, w:cs&&cs.width, t:cs&&cs.getPropertyValue('--t')}; }""", fid)
        print(fid, r)
    b.close()
