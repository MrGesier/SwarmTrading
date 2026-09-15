"""Loopback-only server for the compiled UI with SPA navigation fallback."""
import json
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'frontend/dist'


class UIHandler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(DIST),**kwargs)

    def do_GET(self):
        route=urlsplit(self.path).path
        if route=='/local-health':
            body=json.dumps(dict(app='SwarmTrading',version='0.3.0',project_root=str(ROOT))).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if route in ['/','/intent','/research','/replay']:self.path='/index.html'
        return super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control','no-cache')
        super().end_headers()


if __name__=='__main__':
    if not (DIST/'index.html').is_file():raise SystemExit('Missing frontend build. Run npm run build in frontend.')
    ThreadingHTTPServer(('127.0.0.1',3000),UIHandler).serve_forever()
