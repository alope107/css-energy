import http.server, socketserver, sys, os, time
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'www'); LOG=[]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(s,*a): pass
    def do_GET(s):
        p=s.path.split('?')[0]
        if p=='/api':   # "third party": text/plain + CORS, body framed as CSS; value from v.txt
            v=open(os.path.join(HERE,'v.txt')).read().strip(); LOG.append(v)
            open(os.path.join(HERE,'apilog.txt'),'a').write(f'{time.time():.2f} {v}\n')
            b=f'.v{{width:{v}px}}'.encode(); ct='text/plain'
        else:
            f=os.path.join(ROOT,p.lstrip('/'))
            if not os.path.isfile(f): s.send_response(404); s.end_headers(); return
            b=open(f,'rb').read(); ct='application/xhtml+xml' if f.endswith('.xhtml') else 'text/html'
        s.send_response(200); s.send_header('Content-Type',ct); s.send_header('Access-Control-Allow-Origin','*')
        s.send_header('Cache-Control','no-store'); s.end_headers(); s.wfile.write(b)
class T(socketserver.ThreadingMixIn,http.server.HTTPServer): daemon_threads=True; allow_reuse_address=True
T(('127.0.0.1',int(sys.argv[1])),H).serve_forever()
