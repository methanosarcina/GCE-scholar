"""Serve the fixed-ORCID catalog locally; refresh data with collect.py."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from collect import ROOT
from build import build_site

if __name__ == '__main__':
    site = ROOT / '_site'
    build_site(ROOT, site)
    print('Scholar Gallery: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), partial(SimpleHTTPRequestHandler, directory=str(site))).serve_forever()
