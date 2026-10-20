import sys, os, time
from playwright.sync_api import sync_playwright
D=os.path.dirname(os.path.abspath(__file__))
def setv(v): open(os.path.join(D,'v.txt'),'w').write(str(v))
with sync_playwright() as p:
    kw = {'executable_path': sys.argv[1]} if len(sys.argv) > 1 else {}
    b = p.chromium.launch(args=['--no-proxy-server','--no-sandbox','--headless=new'], **kw); print('browser', b.version)
    for url in ['http://127.0.0.1:9481/p.html', 'http://127.0.0.1:9481/p.xhtml']:
        setv(1234); pg = b.new_page(); pg.goto(url); t0 = time.time(); seen = []
        for v_next, at in [(57, 3.0), (2999, 7.0), (0, 11.0), (None, 15.0)]:
            while time.time() - t0 < at:
                r = pg.evaluate("""() => [document.contentType, document.querySelector('.slot').scrollLeft,
                    getComputedStyle(document.querySelector('.out')).getPropertyValue('--r')]""")
                if not seen or seen[-1][1:] != r: seen.append([round(time.time()-t0,1)] + r)
                pg.wait_for_timeout(100)
            if v_next is not None: setv(v_next)
        print(url)
        for s in seen: print('  ', s)
        print('   rendered:', pg.inner_text('body').strip() if False else pg.accessibility.snapshot()['children'][0]['name'] if pg.accessibility.snapshot().get('children') else '?')
        pg.close()
    b.close()
