#!/usr/bin/env python3
"""Upstream stub: OpenAI-compatible endpoint that answers 429 for the first
FAIL_BUDGET requests, then 200 forever. Every arrival is logged with a
monotonic timestamp so retry waves can be measured from OUTSIDE Chimera.

Usage: stub429.py <port> <fail_budget> <logfile> [status]
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
FAIL_BUDGET = int(sys.argv[2])
LOGFILE = sys.argv[3]
FAIL_STATUS = int(sys.argv[4]) if len(sys.argv) > 4 else 429
RETRY_AFTER = sys.argv[5] if len(sys.argv) > 5 else "1"

T0 = time.monotonic()
_lock = threading.Lock()
_n = 0
_failed = 0
logf = open(LOGFILE, "a", buffering=1)


def _body(status, model):
    if status == 200:
        return {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "STUB-OK-" + model},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }
    if status == 401:
        return {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}}
    return {"error": {"message": f"stub rate limit ({status})", "type": "rate_limit_error", "code": "rate_limit_exceeded"}}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        global _n, _failed
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            model = json.loads(raw).get("model", "?")
        except Exception:
            model = "?"
        with _lock:
            _n += 1
            n = _n
            if _failed < FAIL_BUDGET:
                _failed += 1
                status = FAIL_STATUS
            else:
                status = 200
            logf.write(
                json.dumps(
                    {
                        "n": n,
                        "t": round(time.monotonic() - T0, 4),
                        "status": status,
                        "model": model,
                        "path": self.path,
                        "key": (self.headers.get("authorization") or "")[-6:],
                    }
                )
                + "\n"
            )
        payload = json.dumps(_body(status, model)).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        if status == 429:
            self.send_header("retry-after", RETRY_AFTER)
        self.send_header("connection", "keep-alive")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    print(f"stub listening on {PORT} fail_budget={FAIL_BUDGET} status={FAIL_STATUS} -> {LOGFILE}", flush=True)
    srv.serve_forever()
