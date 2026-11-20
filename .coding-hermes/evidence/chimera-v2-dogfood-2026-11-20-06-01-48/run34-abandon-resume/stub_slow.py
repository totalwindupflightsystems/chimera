#!/usr/bin/env python3
"""Upstream stub for the abandon/resume arm (run 34).

OpenAI-compatible /v1/chat/completions that SLEEPS a fixed number of seconds
before answering 200, and logs every arrival with its own monotonic timestamp
plus a marker taken from the request body. The marker is what lets an observer
attribute upstream work to a specific client request AFTER that client has
gone away -- i.e. measure whether Chimera keeps spending provider tokens on a
request whose user aborted.

Usage: stub_slow.py <port> <delay_s> <logfile>
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
DELAY = float(sys.argv[2])
LOGFILE = sys.argv[3]

T0 = time.monotonic()
_lock = threading.Lock()
_n = 0
logf = open(LOGFILE, "a", buffering=1)


def _marker(payload):
    """First 24 chars of the LAST user message: unique per client prompt."""
    try:
        msgs = payload.get("messages") or []
        for m in reversed(msgs):
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip().replace("\n", " ")[:24]
        return "?"
    except Exception:
        return "!"


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except Exception:
            pass

    def do_POST(self):
        global _n
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        model = payload.get("model", "?")
        marker = _marker(payload)
        with _lock:
            _n += 1
            idx = _n
        t_in = time.monotonic() - T0
        logf.write(
            json.dumps(
                {
                    "arrival": idx,
                    "t_in": round(t_in, 4),
                    "model": model,
                    "marker": marker,
                    "delay_s": DELAY,
                }
            )
            + "\n"
        )
        time.sleep(DELAY)
        t_out = time.monotonic() - T0
        logf.write(
            json.dumps({"served": idx, "t_out": round(t_out, 4), "marker": marker}) + "\n"
        )
        self._send(
            200,
            {
                "id": f"chatcmpl-stub-{idx}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "STUB-OK-%s" % marker,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    logf.write(json.dumps({"stub_start": PORT, "delay_s": DELAY}) + "\n")
    srv.serve_forever()
