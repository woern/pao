"""A small HTTP server on the standard library.

There is deliberately no framework here so that tournament day needs
nothing installed beyond Python. Requests are matched against a route table
of (method, regex, handler); handlers get a Request and return a Response.
All edits to the tournament happen under one lock and are saved at once.
"""

import json
import mimetypes
import os
import re
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from paolib import model, store

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Request:
    def __init__(self, method, path, query, body, headers):
        self.method = method
        self.path = path
        self.query = query          # {name: [values]}
        self.form = {}              # {name: [values]} for urlencoded bodies
        self.json = None
        self.headers = headers
        self.args = ()              # regex groups from the route

        ctype = headers.get("Content-Type", "")
        if body and ctype.startswith("application/x-www-form-urlencoded"):
            self.form = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
        elif body and ctype.startswith("application/json"):
            self.json = json.loads(body.decode("utf-8"))

    def get(self, name, default=""):
        """First value of a form field, falling back to the query string."""
        values = self.form.get(name) or self.query.get(name)
        return values[0] if values else default

    def getlist(self, name):
        return self.form.get(name) or self.query.get(name) or []


class Response:
    def __init__(self, body=b"", status=HTTPStatus.OK, content_type="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.status = status
        self.headers = [("Content-Type", content_type)] + list(headers or [])


def html(body, status=HTTPStatus.OK):
    return Response(body, status)


def redirect(url, msg=None, err=None):
    params = {}
    if msg:
        params["msg"] = msg
    if err:
        params["err"] = err
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    return Response(b"", HTTPStatus.SEE_OTHER, headers=[("Location", url)])


def json_response(data, status=HTTPStatus.OK):
    return Response(json.dumps(data), status, "application/json")


class App:
    """Holds the open tournament and dispatches requests to the pages."""

    # Paths that work before a tournament is open.
    OPEN_PATHS = ("/open",)

    def __init__(self, name=None):
        self.name = None
        self.tournament = None
        self.created = False
        self.lan_url = ""
        self.quiet = False
        self.lock = threading.RLock()
        self.routes = []
        if name:
            self.open(name)

    def open(self, name):
        """Open (or create) a tournament by name. Returns True if it was created."""
        with self.lock:
            self.tournament, self.created = store.open_or_create(name)
            self.name = name
        return self.created

    @property
    def path(self):
        return os.path.abspath(store.tournament_path(self.name)) if self.name else ""

    def route(self, method, pattern):
        regex = re.compile("^" + pattern + "$")

        def register(handler):
            self.routes.append((method, regex, handler))
            return handler
        return register

    def save(self):
        store.save(self.tournament)

    def reload(self):
        with self.lock:
            self.tournament = store.load(self.name)

    def dispatch(self, request):
        if request.path.startswith("/static/"):
            return self.static(request.path[len("/static/"):])

        if self.tournament is None and request.path not in self.OPEN_PATHS:
            return redirect("/open")

        for method, regex, handler in self.routes:
            match = regex.match(request.path)
            if match and method == request.method:
                request.args = tuple(int(g) if g.isdigit() else g for g in match.groups())
                with self.lock:
                    try:
                        return handler(self, request)
                    except (model.ModelError, store.StoreError) as exc:
                        if request.method == "POST" and request.json is None:
                            return redirect(request.headers.get("Referer") or "/", err=str(exc))
                        if request.json is not None:
                            return json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return html("<h1>Error</h1><p>%s</p>" % exc, HTTPStatus.BAD_REQUEST)

        return html("<h1>Not found</h1><p>%s</p>" % request.path, HTTPStatus.NOT_FOUND)

    def static(self, name):
        path = os.path.normpath(os.path.join(STATIC_DIR, name))
        if not path.startswith(STATIC_DIR) or not os.path.isfile(path):
            return Response(b"not found", HTTPStatus.NOT_FOUND, "text/plain")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            return Response(handle.read(), HTTPStatus.OK, ctype, [("Cache-Control", "no-cache")])


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "pao/0.4"

        def _handle(self):
            parsed = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            request = Request(self.command, parsed.path, urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                              body, self.headers)
            try:
                response = app.dispatch(request)
            except Exception as exc:  # keep the server alive on a bug
                import traceback
                traceback.print_exc()
                response = html("<h1>Something went wrong</h1><pre>%s</pre>" % exc,
                                HTTPStatus.INTERNAL_SERVER_ERROR)

            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        do_GET = do_POST = do_HEAD = _handle

        def log_message(self, fmt, *args):
            if app.quiet:
                return
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    return Handler


def serve(app, host="127.0.0.1", port=8000, quiet=False):
    app.quiet = quiet
    server = ThreadingHTTPServer((host, port), make_handler(app))
    server.daemon_threads = True
    return server
