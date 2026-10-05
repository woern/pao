"""Start the web app: python3 -m paoweb [tournament-name] [--port N] [--lan] [--no-browser]

With no name, the browser opens on a page that lists the tournaments in
this folder and lets you create a new one."""

import argparse
import os
import socket
import sys
import threading
import webbrowser

from paolib import store
from . import pages
from .server import App, serve

# How many consecutive ports to try when the requested one is taken.
PORT_TRIES = 20
# "Address already in use" on macOS/Linux, Linux, and Windows.
BUSY_ERRNOS = (48, 98, 10048)


def lan_address():
    """Best guess at this machine's address on the local network."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
        probe.close()
        return address
    except OSError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m paoweb", description=__doc__)
    parser.add_argument("name", nargs="?", default=None,
                        help="tournament to open; <name>.p is created if missing. Omit to choose in the browser")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lan", action="store_true",
                        help="also accept connections from other devices on the local network")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.add_argument("--quiet", action="store_true", help="do not log every request")
    args = parser.parse_args(argv)

    try:
        app = App(store.clean_name(args.name) if args.name else None)
    except store.StoreError as exc:
        print("[ERROR]", exc)
        return 1
    pages.register(app)

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    server = None
    for port in range(args.port, args.port + PORT_TRIES):
        try:
            server = serve(app, host=host, port=port, quiet=args.quiet)
            break
        except OSError as exc:
            if exc.errno not in BUSY_ERRNOS:
                raise
            print("Port %d is busy (another copy of the app, perhaps?); trying %d." % (port, port + 1))
    if server is None:
        print("[ERROR] Ports %d-%d are all busy. Close the other program, or start with --port."
              % (args.port, args.port + PORT_TRIES - 1))
        return 1

    url = "http://127.0.0.1:%d/" % port
    if args.lan:
        address = lan_address()
        if address:
            app.lan_url = "http://%s:%d/" % (address, port)

    if app.tournament is not None:
        print("%s %s (%d teams, %d rounds)" % ("Created" if app.created else "Opened", app.path,
                                               len(app.tournament["teams"]),
                                               max((len(t["games"]) for t in app.tournament["teams"].values()), default=0)))
    else:
        print("Tournament files live in", os.getcwd())
    print("Open", url, ("or %s from another device" % app.lan_url) if app.lan_url else "")
    print("Press Ctrl-C to stop.")

    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
