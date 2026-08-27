#!/usr/bin/env python3
"""Run AulaLista with the standard-library WSGI server for local use."""

import argparse
import os
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    # The local node must be reachable by phones on the same LAN. Operators
    # can still pass --host 127.0.0.1 when they intentionally want loopback.
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")
    from aulalista.wsgi import application

    server = make_server(
        args.host,
        args.port,
        application,
        server_class=ThreadingWSGIServer,
        handler_class=WSGIRequestHandler,
    )
    print(f"AulaLista WSGI en http://{args.host}:{args.port}/health/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
