"""Optional local proxy. GitHub Pages uses the public API directly."""
import functools
import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from collect import ROOT, search, figure

@functools.lru_cache(maxsize=2048)
def cached_figure(pmcid):
    return figure(pmcid)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith('/api/'):
            return super().do_GET()
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == '/api/search':
                query = params.get('query', [''])[0]
                if not query or len(query) > 1000:
                    raise ValueError('Invalid query')
                value = search(query, params.get('cursor', ['*'])[0])
            elif parsed.path == '/api/figure':
                value = cached_figure(params.get('pmcid', [''])[0])
            else:
                self.send_error(404)
                return
            self.reply(value, 200)
        except Exception as exc:
            self.reply({'error': str(exc)}, 502)

    def reply(self, value, status):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == '__main__':
    print('Scholar Gallery: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
