#!/usr/bin/env python3
"""Static preview server for the Nexo Tesis download page.

The page (descargar-nexo-tesis.html) is fully self-contained: the ZIP is
embedded as a data URI, there are no external scripts, no fetch() calls and no
localhost URLs. So the preview only needs a plain static file server.

Design notes for the Arena preview proxy:
* binds 0.0.0.0 (not 127.0.0.1);
* does NOT validate the Host header, so the *.e2b.app proxy host is accepted;
* deliberately does NOT send X-Frame-Options, because the preview is shown in
  an iframe;
* sends CORS:* and nosniff, and no-store so a stale build never sticks.
"""
from __future__ import annotations

import argparse
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    server_version = 'NexoPreview/1.0'
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.zip': 'application/zip', '.json': 'application/json'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def guess_type(self, path):
        if str(path).endswith('.html'):
            return 'text/html; charset=utf-8'
        return super().guess_type(path)

    def _index_fallback(self):
        """Serve the standalone page at / even when no index.html copy exists.

        Earlier the preview broke because index.html and serve.py were scratch
        files that did not survive a workspace restore. Routing / to the
        committed page removes that dependency.
        """
        if self.path.split('?', 1)[0] in ('/', '/index.html') and \
                not (ROOT / 'index.html').is_file():
            self.path = '/descargar-nexo-tesis.html'

    def do_GET(self):
        self._index_fallback()
        return super().do_GET()

    def do_HEAD(self):
        self._index_fallback()
        return super().do_HEAD()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # Intentionally NO X-Frame-Options: the preview renders inside an iframe.
        super().end_headers()

    def log_message(self, fmt, *args):
        print('[preview] ' + (fmt % args), flush=True)


def main():
    parser = argparse.ArgumentParser(description='Nexo Tesis download preview')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--bind', default='0.0.0.0')
    args = parser.parse_args()
    mimetypes.add_type('application/zip', '.zip')
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.daemon_threads = True
    print('Sirviendo ' + str(ROOT) + ' en http://' + args.bind + ':' +
          str(args.port) + '/', flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
