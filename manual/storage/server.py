'''
Server to add needed headers
Emulates CloudFlare's _headers
Still serving static content, just specifying which headers needed based on path
'''

from http.server import HTTPServer, SimpleHTTPRequestHandler

class DczProberRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        if "references" in self.path:
            self.send_header("Use-As-Dictionary", 'match="/cells/probes/*"')
            self.send_header("Cache-Control", "public, max-age=31536000")
            self.send_header("Vary", "*")
        if "probes" in self.path:
            self.send_header("Content-Encoding", "dcz")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Vary", "accept-encoding, available-dictionary")
        super().end_headers()

if __name__ == "__main__":
    # TODO: dynamic port
    HTTPServer(('', 8888), DczProberRequestHandler).serve_forever()