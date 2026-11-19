import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from mininet.cli import CLI
from mininet.log import setLogLevel

from netlib import Lab

if os.geteuid() != 0:
    sys.exit("Run with sudo:  sudo python3 diag/controller.py")

setLogLevel("warning")
lab = Lab()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/topology":
            body = lab.topology()
        elif u.path == "/path":
            body = lab.path_info(q.get("src", [""])[0], q.get("dst", [""])[0])
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


lab.start()
server = HTTPServer(("0.0.0.0", 8080), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print("Network up. REST API on http://localhost:8080  (/topology, /path?src=&dst=)")
print("Leave this window open. Use another terminal for curl / ovs-ofctl.")
CLI(lab.net)
server.shutdown()
lab.stop()