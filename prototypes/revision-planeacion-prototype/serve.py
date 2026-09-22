"""PROTOTYPE: isolated rendering of the planning review route; no database."""
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = Path(__file__).with_name('index.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)
HTTPServer(('127.0.0.1', 8876), Handler).serve_forever()
