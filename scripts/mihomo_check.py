"""Check MRS domain boundaries in real Mihomo with loopback-only traffic."""

import http.client
import http.server
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from pinned_tools import ROOT, download_tool


class ProbeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_CONNECT(self):
        self.send_response(200)
        self.end_headers()
        self.close_connection = False

    def do_GET(self):
        payload = self.server.route_label.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def log_message(self, *_args):
        pass


def verify_mrs_matching(output: Path, domains: list[str]) -> None:
    core = str(download_tool("mihomo"))
    cases = {}
    for domain in domains:
        cases.update({domain: "MATCH", f"www.{domain}": "MATCH",
                      f"not{domain}": "DIRECT", f"{domain}.example": "DIRECT"})
    servers = []
    process = None
    try:
        for label in ("DIRECT", "MATCH"):
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
            server.route_label = label
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        with tempfile.TemporaryDirectory(prefix="mrs-check-", dir=ROOT / ".cache") as directory:
            work = Path(directory)
            shutil.copyfile(output / "geosite_line.mrs", work / "line.mrs")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            config = {
                "mixed-port": port, "allow-lan": False, "bind-address": "127.0.0.1",
                "hosts": {domain: "127.0.0.1" for domain in cases},
                "proxies": [{"name": "matched", "type": "http", "server": "127.0.0.1",
                             "port": servers[1].server_port}],
                "rule-providers": {"line": {"type": "file", "path": "./line.mrs",
                                            "behavior": "domain", "format": "mrs"}},
                "rules": ["RULE-SET,line,matched", "MATCH,DIRECT"],
            }
            config_path = work / "config.json"
            config_path.write_text(json.dumps(config))
            with (work / "core.log").open("w+") as log:
                process = subprocess.Popen([core, "-d", str(work), "-f", str(config_path)],
                                           stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise ValueError(f"Mihomo did not start: {log.read()}")
                        time.sleep(0.1)
                for domain, expected in cases.items():
                    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        client.request("GET", f"http://{domain}:{servers[0].server_port}/probe")
                        response = client.getresponse()
                        actual = response.read().decode()
                        if response.status != 200 or actual != expected:
                            raise ValueError(f"MRS boundary mismatch for {domain}: {actual}")
                    finally:
                        client.close()
                process.terminate()
                process.wait(timeout=5)
                process = None
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        for server in servers:
            server.shutdown()
            server.server_close()
    print(f"Mihomo MRS matching verified: {len(cases)} loopback HTTP cases")
