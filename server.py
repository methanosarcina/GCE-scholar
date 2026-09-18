"""Serve the fixed-ORCID catalog locally; refresh data with collect.py."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from collect import ROOT

if __name__ == '__main__':
    print('Scholar Gallery: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), partial(SimpleHTTPRequestHandler, directory=str(ROOT))).serve_forever()
